"""
landmark_detector.py
--------------------
Runs TotalSegmentator on a NIfTI CT scan in a background QThread so the
UI never freezes.  When finished it emits a signal with a dict of the form:

    { "Liver": (z, y, x), "Kidney L": (z, y, x), ... }

where (z, y, x) are integer voxel coordinates into self.image_array
(shape = (depth, height, width)). These map directly onto VoxelMed's
crosshair/slider convention:

    sliders[0] (Axial)    -> z   (depth index)
    sliders[1] (Sagittal) -> x   (width index)
    sliders[2] (Coronal)  -> y   (height index)

IMPORTANT (Windows):
TotalSegmentator's python_api (calling totalsegmentator() as a function)
is known to be unreliable on Windows when invoked from inside a thread of
a larger application (PyQt5, in our case). Windows uses "spawn" instead
of "fork" to create subprocesses, and nnU-Net's internal multiprocessing
pools can fail with PermissionError: [WinError 5] Access is denied during
handle duplication between processes. This is a documented upstream issue.

The command-line tool (`TotalSegmentator -i ... -o ...`) does NOT have
this problem, because it runs as its own clean, independent OS process
from the very start. So instead of calling the Python API in-process, we
shell out to the CLI via subprocess.run() from inside the QThread. This
sidesteps the Windows spawn/fork issue entirely.

We also do NOT rely on shutil.which("TotalSegmentator") / system PATH to
find the executable, since a QThread inside a PyQt5 app does not always
inherit the same resolved PATH as an interactive terminal. Instead we
locate the executable directly next to sys.executable (the currently
running Python interpreter), which is always correct for a venv install.

Usage (wired up automatically by LandmarkNavMixin):
    detector = LandmarkDetector(nifti_path, image_array)
    detector.landmarks_ready.connect(callback)
    detector.progress_update.connect(status_label.setText)
    detector.error_occurred.connect(error_callback)
    detector.start()
"""

import os
import shutil
import subprocess
import sys
import tempfile
import numpy as np

from PyQt5.QtCore import QThread, pyqtSignal


# The clinically important organs we surface as navigation buttons.
# Keys   = display name shown in the sidebar
# Values = exact filename stem TotalSegmentator writes to its output folder
LANDMARK_MAP = {
    # ── Major organs ──────────────────────────────────────────────────
    "Liver":              "liver",
    "Spleen":             "spleen",
    "Kidney L":           "kidney_left",
    "Kidney R":           "kidney_right",
    "Pancreas":           "pancreas",
    "Gallbladder":        "gallbladder",
    "Stomach":            "stomach",
    "Urinary Bladder":    "urinary_bladder",
    "Duodenum":           "duodenum",
    "Small Bowel":        "small_bowel",
    "Colon":              "colon",
    "Esophagus":          "esophagus",
    "Adrenal Gland L":    "adrenal_gland_left",
    "Adrenal Gland R":    "adrenal_gland_right",

    # ── Vessels ───────────────────────────────────────────────────────
    "Aorta":              "aorta",
    "Inferior Vena Cava": "inferior_vena_cava",
    "Portal Vein":        "portal_vein_and_splenic_vein",
    "Iliac Artery L":     "iliac_artery_left",
    "Iliac Artery R":     "iliac_artery_right",

    # ── Heart & lungs ────────────────────────────────────────────────
    "Heart":              "heart",
    "Trachea":            "trachea",
    "Lung Upper L":       "lung_upper_lobe_left",
    "Lung Lower L":       "lung_lower_lobe_left",
    "Lung Upper R":       "lung_upper_lobe_right",
    "Lung Middle R":      "lung_middle_lobe_right",
    "Lung Lower R":       "lung_lower_lobe_right",

    # ── Vertebrae — exact names from TotalSegmentator map_to_binary.py
    # Note: capital L and T are required (vertebrae_L1 not vertebrae_l1)
    "Vertebra L1":        "vertebrae_L1",
    "Vertebra L2":        "vertebrae_L2",
    "Vertebra L3":        "vertebrae_L3",
    "Vertebra L4":        "vertebrae_L4",
    "Vertebra L5":        "vertebrae_L5",

    # ── Pelvis & hip ─────────────────────────────────────────────────
    "Hip L":              "hip_left",
    "Hip R":              "hip_right",
    "Sacrum":             "sacrum",

    # ── Other ─────────────────────────────────────────────────────────
    "Sternum":            "sternum",
}


class LandmarkDetector(QThread):
    """Background thread that runs TotalSegmentator (via CLI subprocess)
    and extracts organ centroids."""

    landmarks_ready  = pyqtSignal(dict)   # {name: (z, y, x)}
    progress_update  = pyqtSignal(str)    # status text
    error_occurred   = pyqtSignal(str)    # error text

    def __init__(self, nifti_path: str, image_array: np.ndarray, parent=None):
        super().__init__(parent)
        self.nifti_path  = nifti_path
        self.image_array = image_array

    # ------------------------------------------------------------------
    def run(self):
        try:
            exe = self._get_totalsegmentator_exe()
            landmarks = self._run_totalsegmentator_cli(exe)
            self.landmarks_ready.emit(landmarks)
        except FileNotFoundError as e:
            self.error_occurred.emit(
                "TotalSegmentator command-line tool not found.\n"
                "Run:  pip install TotalSegmentator\n\n"
                f"Details: {e}"
            )
        except Exception as e:
            self.error_occurred.emit(f"Landmark detection failed:\n{str(e)}")

    # ------------------------------------------------------------------
    def _get_totalsegmentator_exe(self) -> str:
        """
        Locate the TotalSegmentator CLI executable reliably.

        shutil.which("TotalSegmentator") looks at the PATH environment
        variable of the *current process*. When VoxelMed is launched with
        `python main.py` from an activated venv, this normally works -- but
        on some Windows setups the spawned QThread's environment can fail
        to resolve it even though it works fine when typed directly into
        PowerShell.

        sys.executable is always reliable: it's the exact path to the
        Python interpreter currently running this code. Since
        TotalSegmentator is installed as a console-script entry point in
        the same venv, its executable lives right next to sys.executable:
            Windows:    ...\\venv\\Scripts\\TotalSegmentator.exe
            Linux/Mac:  .../venv/bin/TotalSegmentator
        We check there FIRST, then fall back to a PATH-based lookup.
        """
        venv_scripts_dir = os.path.dirname(sys.executable)

        candidates = [
            os.path.join(venv_scripts_dir, "TotalSegmentator.exe"),  # Windows
            os.path.join(venv_scripts_dir, "TotalSegmentator"),      # Linux/Mac
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path

        found = shutil.which("TotalSegmentator")
        if found:
            return found

        raise FileNotFoundError(
            "'TotalSegmentator' executable not found.\n"
            f"Checked: {candidates}\n"
            "Make sure you installed it inside this venv: "
            "pip install TotalSegmentator"
        )

    # ------------------------------------------------------------------
    def _run_totalsegmentator_cli(self, exe_path: str) -> dict:
        import nibabel as nib
        from scipy import ndimage

        self.progress_update.emit("AI landmark detection started...")

        tmp_dir = tempfile.mkdtemp(prefix="voxelmed_seg_")
        roi_names = list(LANDMARK_MAP.values())

        # Build the CLI command using the resolved absolute executable path
        # (not just the bare "TotalSegmentator" name) so it's unambiguous
        # which install gets run.
        cmd = [
            exe_path,
            "-i", self.nifti_path,
            "-o", tmp_dir,
            "--fast",                 # 3mm model -> much faster on CPU
            "--nr_thr_resamp", "1",   # avoid extra worker processes (Windows)
            "--nr_thr_saving", "1",   # avoid extra worker processes (Windows)
            "--roi_subset", *roi_names,
        ]

        self.progress_update.emit(
            "Running TotalSegmentator (3-10 min on first run)..."
        )

        # Run as an independent OS process. This is the key fix: it gets
        # its own clean process from the start, so nnU-Net's internal
        # multiprocessing pools spawn correctly instead of failing with
        # PermissionError: [WinError 5] Access is denied, which can happen
        # when the python_api is called from inside a QThread on Windows.
        env = os.environ.copy()
        env["nnUNet_n_proc_DA"] = "1"
        env["OMP_NUM_THREADS"]  = "1"

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "TotalSegmentator CLI failed "
                f"(exit code {result.returncode}).\n\n"
                f"stderr (last 800 chars):\n{result.stderr[-800:]}"
            )

        self.progress_update.emit("Segmentation done. Extracting centroids...")

        landmarks = {}
        vol_shape = self.image_array.shape  # (D, H, W) = (z, y, x)

        for display_name, stem in LANDMARK_MAP.items():
            mask_path = os.path.join(tmp_dir, f"{stem}.nii.gz")
            if not os.path.exists(mask_path):
                continue  # organ not segmented / out of field of view

            mask_img = nib.load(mask_path)
            mask_arr = (mask_img.get_fdata() > 0.5).astype(np.uint8)

            if mask_arr.sum() == 0:
                continue

            # nibabel loads NIfTI in (x, y, z) order.
            # center_of_mass therefore returns (cx_nifti, cy_nifti, cz_nifti).
            # VoxelMed's image_array is loaded by SimpleITK which uses
            # (z, y, x) / (depth, height, width) convention — the opposite.
            # We must swap: nifti_dim0->vol_x, nifti_dim1->vol_y, nifti_dim2->vol_z
            # and then map to VoxelMed sliders:
            #   sliders[0] Axial    = vol_z  (depth)
            #   sliders[1] Sagittal = vol_x  (width)
            #   sliders[2] Coronal  = vol_y  (height)
            cx_nifti, cy_nifti, cz_nifti = ndimage.center_of_mass(mask_arr)

            z = int(np.clip(round(cz_nifti), 0, vol_shape[0] - 1))
            y = int(np.clip(round(cy_nifti), 0, vol_shape[1] - 1))
            x = int(np.clip(round(cx_nifti), 0, vol_shape[2] - 1))

            landmarks[display_name] = (z, y, x)

        self.progress_update.emit(
            f"Found {len(landmarks)} landmarks."
            if landmarks else
            "No landmarks found - is this an abdominal CT?"
        )
        return landmarks