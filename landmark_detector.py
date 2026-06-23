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
    detector = LandmarkDetector(nifti_path, image_array, section="Abdomen")
    detector.landmarks_ready.connect(callback)
    detector.progress_update.connect(status_label.setText)
    detector.error_occurred.connect(error_callback)
    detector.start()
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import numpy as np

from PyQt5.QtCore import QThread, pyqtSignal

# Colormap for up to 20 simultaneous organ labels (BGR)
LABEL_COLORMAP = {
    1:  (255,   0,   0),
    2:  (  0, 255,   0),
    3:  (  0,   0, 255),
    4:  (255, 255,   0),
    5:  (255,   0, 255),
    6:  (  0, 255, 255),
    7:  (255, 128,   0),
    8:  (128,   0, 255),
    9:  (  0, 255, 128),
    10: (128, 128, 255),
    11: (255, 128, 128),
    12: (128, 255, 128),
    13: (128, 128,   0),
    14: (  0, 128, 128),
    15: (128,   0, 128),
    16: (255, 128,  64),
    17: ( 64, 128, 255),
    18: (192, 192, 192),
    19: (255,  64,  64),
    20: ( 64, 255,  64),
}


# ---------------------------------------------------------------------------
# JSON-based section / organ configuration
# ---------------------------------------------------------------------------

_CONFIG_CACHE = None


def _load_config():
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        config_path = os.path.join(os.path.dirname(__file__), "segmentation_config.json")
        with open(config_path, "r", encoding="utf-8") as f:
            _CONFIG_CACHE = json.load(f)
    return _CONFIG_CACHE


def get_sections():
    """Return list of section names in display order."""
    return list(_load_config().keys())


def get_section_description(section: str) -> str:
    """Return a short description for the section."""
    return section


def get_organs_for_section(section: str) -> dict:
    """Return {stem: stem} for a section (flat format)."""
    return dict(_load_config().get(section, {}))


def get_all_organs() -> dict:
    """Return combined {stem: stem} from every section (flat format)."""
    combined = {}
    for sec in _load_config().values():
        combined.update(sec)
    return combined


# ---------------------------------------------------------------------------
# LandmarkDetector — background thread
# ---------------------------------------------------------------------------


class LandmarkDetector(QThread):
    """Background thread that runs TotalSegmentator (via CLI subprocess)
    and extracts organ centroids + masks."""

    landmarks_ready  = pyqtSignal(dict)   # {name: (z, y, x)}
    masks_ready      = pyqtSignal(object, object, object)  # (combined_mask, label_map, landmarks)
    progress_update  = pyqtSignal(str)    # status text
    error_occurred   = pyqtSignal(str)    # error text

    def __init__(self, nifti_path: str, image_array: np.ndarray,
                 organ_map: dict = None, parent=None):
        super().__init__(parent)
        self.nifti_path  = nifti_path
        self.image_array = image_array
        self.organ_map   = organ_map  # {display_name: stem} or None = all

    # ------------------------------------------------------------------
    def run(self):
        try:
            exe = self._get_totalsegmentator_exe()
            combined_mask, label_map, landmarks = self._run_totalsegmentator_cli(exe)
            self.masks_ready.emit(combined_mask, label_map, landmarks)
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
        venv_scripts_dir = os.path.dirname(sys.executable)

        candidates = [
            os.path.join(venv_scripts_dir, "TotalSegmentator.exe"),
            os.path.join(venv_scripts_dir, "TotalSegmentator"),
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
    def _run_totalsegmentator_cli(self, exe_path: str):
        import nibabel as nib
        from scipy import ndimage

        self.progress_update.emit("AI landmark detection started...")

        # Determine which organs to segment
        if self.organ_map:
            organ_map = self.organ_map
            label = f"{len(organ_map)} selected organ(s)"
        else:
            organ_map = get_all_organs()
            label = "All sections"

        roi_names = list(organ_map.values())
        if not roi_names:
            self.progress_update.emit(f"No organs configured for {label}.")
            return np.zeros((1, 1, 1), dtype=np.uint8), {}, {}

        tmp_dir = tempfile.mkdtemp(prefix="voxelmed_seg_")

        # Check for odd dimensions and pad to even to avoid TotalSegmentator
        # off-by-one resampling bug.
        nii_img = nib.load(self.nifti_path)
        orig_shape = nii_img.get_fdata().shape[:3]
        pad_width = [(0, 1 if d % 2 != 0 else 0) for d in orig_shape]
        needs_pad = any(p[1] > 0 for p in pad_width)

        if needs_pad:
            self.progress_update.emit("Padding odd dimension(s) to even...")
            padded_data = np.pad(
                nii_img.get_fdata(), pad_width, mode='edge'
            )
            # Copy affine & header so orientation is preserved
            padded_img = nib.Nifti1Image(padded_data, nii_img.affine, nii_img.header)
            input_path = os.path.join(tmp_dir, "input_padded.nii.gz")
            nib.save(padded_img, input_path)
        else:
            input_path = self.nifti_path

        # Run FULL segmentation (no --roi_subset) to avoid internal cropping
        # bug in TotalSegmentator. We filter to only the desired organs after.
        cmd = [
            exe_path,
            "-i", input_path,
            "-o", tmp_dir,
            "--fast",
            "--nr_thr_resamp", "1",
            "--nr_thr_saving", "1",
        ]

        self.progress_update.emit(
            f"Running TotalSegmentator (full) for {label} "
            "(3-10 min on first run)..."
        )

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

        self.progress_update.emit("Segmentation done. Loading masks...")

        vol_shape = self.image_array.shape
        combined_mask = np.zeros(vol_shape, dtype=np.uint8)
        label_map     = {}
        landmarks     = {}

        # Only load the masks the user selected (filter from full output)
        for label_idx, (display_name, stem) in enumerate(organ_map.items()):
            mask_path = os.path.join(tmp_dir, f"{stem}.nii.gz")
            if not os.path.exists(mask_path):
                continue

            mask_img = nib.load(mask_path)
            mask_arr = (mask_img.get_fdata() > 0.5).astype(np.uint8)

            # Crop back to original dimensions if we padded
            if needs_pad:
                dz, dy, dx = orig_shape
                mask_arr = mask_arr[:dz, :dy, :dx]

            # Ensure mask shape matches vol_shape (TotalSegmentator can
            # occasionally produce off-by-one output dimensions)
            if mask_arr.shape != vol_shape:
                factors = (
                    vol_shape[0] / mask_arr.shape[0],
                    vol_shape[1] / mask_arr.shape[1],
                    vol_shape[2] / mask_arr.shape[2],
                )
                mask_arr = (ndimage.zoom(mask_arr.astype(np.float64), factors, order=0) > 0.5).astype(np.uint8)

            if mask_arr.sum() == 0:
                continue

            label_val = label_idx + 1
            combined_mask[mask_arr > 0] = label_val
            label_map[label_val] = LABEL_COLORMAP.get(label_val, (200, 200, 200))

            cx_nifti, cy_nifti, cz_nifti = ndimage.center_of_mass(mask_arr)
            z = int(np.clip(round(cz_nifti), 0, vol_shape[0] - 1))
            y = int(np.clip(round(cy_nifti), 0, vol_shape[1] - 1))
            x = int(np.clip(round(cx_nifti), 0, vol_shape[2] - 1))
            landmarks[display_name] = (z, y, x)

        self.progress_update.emit(
            f"Found {len(landmarks)} organ(s)."
            if landmarks else
            "No organs found."
        )
        return combined_mask, label_map, landmarks
