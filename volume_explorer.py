"""
volume_explorer.py
-------------------
"3D Lab" — a standalone window with ONLY a big 3-D view plus tools to cut
into the volume and peel away layers/organs, so the user can see structures
that sit deeper inside the body.

Opened from the main toolbar ("3D Lab" action, wired up in ui.py). It is
given the data already loaded in the main viewer (image_array, spacing,
segmentation_mask, label_colormap) — it does not load its own files.

Tools provided:
    1. Box Crop          – an interactive vtkBoxWidget. Drag its handles to
                            cut away anything outside the box, "opening up"
                            the volume from any side.
    2. Orthogonal Clips  – three independent clipping planes (X / Y / Z)
                            with sliders, each with a "flip side" button —
                            the classic "slice the volume open" tool.
    3. Organ Layers      – if a per-organ segmentation mask is available
                            (produced by the AI Segmentation panel in the
                            main window), each organ gets its own
                            show/hide checkbox + opacity slider, so organs
                            can be individually removed/faded to expose
                            what's behind them.
    4. Tissue Layers     – always available fallback that works on raw
                            intensity even with no segmentation: classic
                            "Skin / Soft tissue / Bone" presets plus a
                            manual intensity-threshold slider, so low-density
                            outer layers (skin, fat) can be peeled back to
                            reveal denser inner structures (organs, bone).
    5. Reset             – restores all clips/crops/visibility to default.

This file is intentionally self-contained: it only needs the volume array
(+ optionally the mask/colormap) handed to it, so it can be opened, used,
and closed without disturbing the main MPR viewer underneath.
"""

import numpy as np
import vtkmodules.all as vtk
from vtkmodules.util import numpy_support

from PyQt5.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from volume_explorer_ui import VolumeExplorerUIMixin, TISSUE_PRESETS


# ---------------------------------------------------------------------------
# Background worker for running TotalSegmentator inside the 3D Lab
# ---------------------------------------------------------------------------
class SegWorker(QThread):
    """Runs TotalSegmentator CLI in a background thread, emits result."""
    finished = pyqtSignal(object, object)   # combined_mask, label_map
    error    = pyqtSignal(str)
    progress = pyqtSignal(str)

    import os as _os  # private alias used in run()

    def __init__(self, image_array, spacing=(1.0, 1.0, 1.0), parent=None):
        super().__init__(parent)
        self.image_array = image_array
        self.spacing     = spacing

    def run(self):
        import nibabel as nib
        import shutil
        import subprocess
        import sys
        import tempfile
        from scipy import ndimage

        try:
            tmp_dir = tempfile.mkdtemp(prefix="voxelmed3d_")
            venv_dir = self._os.path.dirname(sys.executable)
            exe = self._os.path.join(venv_dir, "TotalSegmentator.exe")
            if not self._os.path.isfile(exe):
                exe = self._os.path.join(venv_dir, "TotalSegmentator")
            if not self._os.path.isfile(exe):
                exe = shutil.which("TotalSegmentator")
            if not exe:
                raise FileNotFoundError(
                    "TotalSegmentator not found.\nInstall: pip install TotalSegmentator"
                )

            self.progress.emit("Saving input volume...")
            arr = self.image_array
            orig_shape = arr.shape
            pad_width = [(0, 1 if d % 2 != 0 else 0) for d in orig_shape]
            needs_pad = any(p[1] > 0 for p in pad_width)

            aff = np.eye(4)
            if needs_pad:
                padded = np.pad(arr, pad_width, mode='edge')
                nib.save(nib.Nifti1Image(padded, aff),
                         self._os.path.join(tmp_dir, "input.nii.gz"))
            else:
                nib.save(nib.Nifti1Image(arr, aff),
                         self._os.path.join(tmp_dir, "input.nii.gz"))
            input_path = self._os.path.join(tmp_dir, "input.nii.gz")

            self.progress.emit("Running TotalSegmentator (full)...")
            cmd = [
                exe, "-i", input_path, "-o", tmp_dir, "--fast",
                "--nr_thr_resamp", "1", "--nr_thr_saving", "1",
            ]
            env = self._os.environ.copy()
            env["nnUNet_n_proc_DA"] = "1"
            env["OMP_NUM_THREADS"] = "1"
            result = subprocess.run(
                cmd, capture_output=True, text=True, env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if self._os.name == "nt" else 0,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"TotalSegmentator CLI failed (exit {result.returncode}).\n"
                    f"stderr (last 800 chars):\n{result.stderr[-800:]}"
                )

            self.progress.emit("Loading results...")
            from landmark_detector import get_all_organs, LABEL_COLORMAP
            all_stems = sorted(set(get_all_organs().values()))
            combined = np.zeros(orig_shape, dtype=np.uint8)
            label_map = {}
            idx = 0
            for stem in all_stems:
                mp = self._os.path.join(tmp_dir, f"{stem}.nii.gz")
                if not self._os.path.isfile(mp):
                    continue
                m = (nib.load(mp).get_fdata() > 0.5).astype(np.uint8)
                if needs_pad:
                    dz, dy, dx = orig_shape
                    m = m[:dz, :dy, :dx]
                if m.shape != orig_shape:
                    factors = (orig_shape[0]/m.shape[0],
                               orig_shape[1]/m.shape[1],
                               orig_shape[2]/m.shape[2])
                    m = (ndimage.zoom(m.astype(np.float64), factors, order=0) > 0.5).astype(np.uint8)
                if m.sum() == 0:
                    continue
                idx += 1
                combined[m > 0] = idx
                label_map[idx] = LABEL_COLORMAP.get(idx, (200, 200, 200))

            shutil.rmtree(tmp_dir, ignore_errors=True)
            self.finished.emit(combined, label_map)

        except Exception as e:
            self.error.emit(str(e))


class VolumeExplorerWindow(VolumeExplorerUIMixin, QMainWindow):
    """Standalone '3D Lab' window: big VTK view + cutting/layer tools."""

    def __init__(self, image_array, spacing=(1.0, 1.0, 1.0),
                 segmentation_mask=None, label_colormap=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D Lab \u2014 Volume Explorer")
        self.resize(1300, 850)

        self.image_array       = image_array
        self.spacing            = spacing or (1.0, 1.0, 1.0)
        self.segmentation_mask  = segmentation_mask
        self.label_colormap     = label_colormap or {}

        # AI segmentation state
        self._seg_worker          = None
        self._ai_seg_available    = self.segmentation_mask is not None
        self._selected_organ_label = None
        self._organ_opacity       = 1.0
        self._rest_opacity        = 1.0
        self._organ_names_by_label = {}
        self._organ_name_list     = []
        self._closing             = False

        # Tissue-layer threshold state
        self.tissue_low, self.tissue_high = TISSUE_PRESETS["All tissue"]

        # VTK pipeline handles, built in _build_vtk_pipeline()
        self.vtk_image          = None
        self.volume_mapper      = None
        self.volume             = None
        self.volume_property    = None
        self.ctf                = None
        self.otf                = None
        self.box_widget         = None
        self.clip_planes        = {}
        self.clip_enabled       = {"x": False, "y": False, "z": False}
        self.clip_flipped       = {"x": False, "y": False, "z": False}

        # Cached per-voxel label volume aligned to image_array, or None
        self._label_volume = None

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_tool_panel())

        self.vtk_widget = QVTKRenderWindowInteractor(central)
        root_layout.addWidget(self.vtk_widget, stretch=1)

        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(1.0, 1.0, 1.0)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()

        self._build_vtk_pipeline()

        self.interactor.Initialize()

        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()

    # ======================================================================
    # VTK pipeline
    # ======================================================================
    def _build_vtk_pipeline(self):
        arr = self.image_array
        depth, height, width = arr.shape

        arr_f = arr.astype(np.float64)
        amin, amax = arr_f.min(), arr_f.max()
        if amax > amin:
            arr_u8 = ((arr_f - amin) / (amax - amin) * 255.0).astype(np.uint8)
        else:
            arr_u8 = np.zeros_like(arr_f, dtype=np.uint8)

        self.vtk_image = vtk.vtkImageData()
        self.vtk_image.SetDimensions(width, height, depth)
        sx, sy, sz = self.spacing if len(self.spacing) == 3 else (1.0, 1.0, 1.0)
        self.vtk_image.SetSpacing(sx, sy, sz)
        self.vtk_image.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)

        flipped = np.flip(arr_u8, axis=0)
        vtk_array = numpy_support.numpy_to_vtk(
            flipped.ravel(), deep=True, array_type=vtk.VTK_UNSIGNED_CHAR
        )
        self.vtk_image.GetPointData().SetScalars(vtk_array)

        if self.segmentation_mask is not None:
            self._label_volume = np.flip(self.segmentation_mask, axis=0)

        self.volume_mapper = vtk.vtkSmartVolumeMapper()
        self.volume_mapper.SetInputData(self.vtk_image)
        self.volume_mapper.SetBlendModeToComposite()

        self.volume_property = vtk.vtkVolumeProperty()
        self.volume_property.ShadeOn()
        self.volume_property.SetInterpolationTypeToLinear()

        self.ctf = vtk.vtkColorTransferFunction()
        self.ctf.AddRGBPoint(0,   0.0, 0.0, 0.0)
        self.ctf.AddRGBPoint(128, 0.8, 0.7, 0.6)
        self.ctf.AddRGBPoint(255, 1.0, 1.0, 1.0)
        self.volume_property.SetColor(self.ctf)

        self.otf = vtk.vtkPiecewiseFunction()
        self._rebuild_opacity_function()
        self.volume_property.SetScalarOpacity(self.otf)

        self.volume = vtk.vtkVolume()
        self.volume.SetMapper(self.volume_mapper)
        self.volume.SetProperty(self.volume_property)

        self.renderer.AddVolume(self.volume)

        # Box widget for interactive cropping
        self.box_widget = vtk.vtkBoxWidget()
        self.box_widget.SetInteractor(self.interactor)
        self.box_widget.SetPlaceFactor(1.0)
        self.box_widget.PlaceWidget(self.vtk_image.GetBounds())
        self.box_widget.InsideOutOn()
        self.box_widget.GetOutlineProperty().SetColor(1, 0.6, 0)
        self.box_widget.AddObserver("InteractionEvent", self._on_box_widget_interaction)
        self.box_widget.Off()

        self.crop_planes = vtk.vtkPlanes()
        self.volume_mapper.AddClippingPlane  # noqa

        bounds = self.vtk_image.GetBounds()
        self.clip_planes["x"] = vtk.vtkPlane()
        self.clip_planes["x"].SetOrigin((bounds[0] + bounds[1]) / 2.0, 0, 0)
        self.clip_planes["x"].SetNormal(1, 0, 0)

        self.clip_planes["y"] = vtk.vtkPlane()
        self.clip_planes["y"].SetOrigin(0, (bounds[2] + bounds[3]) / 2.0, 0)
        self.clip_planes["y"].SetNormal(0, 1, 0)

        self.clip_planes["z"] = vtk.vtkPlane()
        self.clip_planes["z"].SetOrigin(0, 0, (bounds[4] + bounds[5]) / 2.0)
        self.clip_planes["z"].SetNormal(0, 0, 1)

        self._bounds = bounds

    # ------------------------------------------------------------------
    # Opacity transfer function
    # ------------------------------------------------------------------
    def _rebuild_opacity_function(self):
        self.otf.RemoveAllPoints()
        low, high = self.tissue_low, self.tissue_high

        if low <= 0:
            self.otf.AddPoint(0, 0.0)
        else:
            self.otf.AddPoint(0, 0.0)
            self.otf.AddPoint(max(0, low - 1), 0.0)

        self.otf.AddPoint(max(0, low), 0.05 if low > 0 else 0.0)
        mid = (low + high) / 2.0
        self.otf.AddPoint(mid, 0.4)
        self.otf.AddPoint(min(255, high), 0.85)
        self.otf.AddPoint(255, 1.0)

        if self.vtk_widget is not None:
            self.vtk_widget.GetRenderWindow().Render()

    # ======================================================================
    # Box crop handlers
    # ======================================================================
    def _on_box_crop_toggled(self, state):
        enabled = state == Qt.Checked
        if enabled:
            self.box_widget.On()
            self._apply_box_clip()
        else:
            self.box_widget.Off()
            self.volume_mapper.RemoveAllClippingPlanes()
            self._reapply_orthogonal_clips()
        self.vtk_widget.GetRenderWindow().Render()

    def _on_box_widget_interaction(self, widget, event):
        self._apply_box_clip()

    def _apply_box_clip(self):
        planes = vtk.vtkPlanes()
        self.box_widget.GetPlanes(planes)
        self.volume_mapper.RemoveAllClippingPlanes()
        self.volume_mapper.SetClippingPlanes(planes)
        self._reapply_orthogonal_clips(keep_existing=True)
        self.vtk_widget.GetRenderWindow().Render()

    # ======================================================================
    # Orthogonal clip-plane handlers
    # ======================================================================
    def _on_clip_toggled(self, axis, state):
        self.clip_enabled[axis] = (state == Qt.Checked)
        self._reapply_orthogonal_clips()
        self.vtk_widget.GetRenderWindow().Render()

    def _on_clip_slider(self, axis, value):
        bounds = self._bounds
        if axis == "x":
            self.clip_planes["x"].SetOrigin(bounds[0] + value * self.spacing[0], 0, 0)
        elif axis == "y":
            self.clip_planes["y"].SetOrigin(0, bounds[2] + value * self.spacing[1], 0)
        else:
            self.clip_planes["z"].SetOrigin(0, 0, bounds[4] + value * self.spacing[2])
        self._reapply_orthogonal_clips()
        self.vtk_widget.GetRenderWindow().Render()

    def _on_clip_flip(self, axis):
        self.clip_flipped[axis] = not self.clip_flipped[axis]
        normals = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}
        nx, ny, nz = normals[axis]
        sign = -1 if self.clip_flipped[axis] else 1
        self.clip_planes[axis].SetNormal(nx * sign, ny * sign, nz * sign)
        self._reapply_orthogonal_clips()
        self.vtk_widget.GetRenderWindow().Render()

    def _reapply_orthogonal_clips(self, keep_existing=False):
        if not keep_existing:
            self.volume_mapper.RemoveAllClippingPlanes()
            if self.box_widget.GetEnabled():
                planes = vtk.vtkPlanes()
                self.box_widget.GetPlanes(planes)
                self.volume_mapper.SetClippingPlanes(planes)

        for axis, enabled in self.clip_enabled.items():
            if enabled:
                self.volume_mapper.AddClippingPlane(self.clip_planes[axis])

    # ======================================================================
    # Organ layer (two-slider) handler
    # ======================================================================
    def _apply_organ_layers(self):
        if self._label_volume is None or self.segmentation_mask is None:
            return

        arr = self.image_array.astype(np.float64)
        amin, amax = arr.min(), arr.max()
        if amax > amin:
            base_u8 = ((arr - amin) / (amax - amin) * 255.0)
        else:
            base_u8 = np.zeros_like(arr)

        scale = np.ones_like(base_u8, dtype=np.float64)

        if self._selected_organ_label is not None:
            sel = (self.segmentation_mask == self._selected_organ_label)
            scale[sel] = self._organ_opacity
            other = (self.segmentation_mask > 0) & (~sel)
            scale[other] = self._rest_opacity
        else:
            other = (self.segmentation_mask > 0)
            scale[other] = self._rest_opacity

        adjusted = np.clip(base_u8 * scale, 0, 255).astype(np.uint8)
        flipped = np.flip(adjusted, axis=0)

        # Build a fresh vtkImageData to force GPU re-upload
        depth, height, width = self.image_array.shape
        new_img = vtk.vtkImageData()
        new_img.SetDimensions(width, height, depth)
        sx, sy, sz = self.spacing if len(self.spacing) == 3 else (1.0, 1.0, 1.0)
        new_img.SetSpacing(sx, sy, sz)

        vtk_arr = numpy_support.numpy_to_vtk(
            flipped.ravel(), deep=True, array_type=vtk.VTK_UNSIGNED_CHAR
        )
        new_img.GetPointData().SetScalars(vtk_arr)

        self.volume_mapper.SetInputData(new_img)
        self.vtk_image = new_img

        self.vtk_widget.GetRenderWindow().Render()

    # ======================================================================
    # AI Segmentation handlers
    # ======================================================================
    def _on_ai_run(self):
        self._ai_run_btn.setEnabled(False)
        self._ai_run_btn.setText("Running\u2026")
        self._ai_progress.setText("Starting\u2026")
        self._ai_progress.setVisible(True)

        self._seg_worker = SegWorker(self.image_array, self.spacing, self)
        self._seg_worker.finished.connect(self._on_ai_seg_done)
        self._seg_worker.error.connect(self._on_ai_seg_error)
        self._seg_worker.progress.connect(self._ai_progress.setText)
        self._seg_worker.start()

    def _on_ai_seg_done(self, combined_mask, label_map):
        if self._closing:
            return
        self.segmentation_mask    = combined_mask
        self.label_colormap       = label_map
        self._label_volume        = np.flip(combined_mask, axis=0)
        self._ai_seg_available    = True
        self._selected_organ_label = None
        self._organ_opacity       = 1.0
        self._rest_opacity        = 1.0

        from landmark_detector import get_all_organs
        all_organs = get_all_organs()
        all_stems_sorted = sorted(set(all_organs.values()))
        stem_to_name = {v: k for k, v in all_organs.items()}
        self._organ_name_list = []
        self._organ_names_by_label = {}
        for label_val in sorted(label_map.keys()):
            stem = all_stems_sorted[label_val - 1]
            name = stem_to_name.get(stem, f"Region {label_val}")
            self._organ_names_by_label[label_val] = name
            self._organ_name_list.append(name)

        self._ai_organ_combo.blockSignals(True)
        self._ai_organ_combo.clear()
        self._ai_organ_combo.addItem("\u2014 None \u2014")
        for name in self._organ_name_list:
            self._ai_organ_combo.addItem(name)
        self._ai_organ_combo.blockSignals(False)

        self._ai_organ_slider.setValue(100)
        self._ai_rest_slider.setValue(100)

        self._ai_stack.setCurrentIndex(1)
        self._apply_organ_layers()

    def _on_ai_seg_error(self, msg):
        if self._closing:
            return
        self._ai_run_btn.setEnabled(True)
        self._ai_run_btn.setText("Run AI Segmentation")
        self._ai_progress.setText(f"Failed: {msg}")
        self._ai_progress.setStyleSheet("color: #ff6666; font-size: 10px;")

    def _on_ai_organ_selected(self, idx):
        if idx <= 0:
            self._selected_organ_label = None
        else:
            label_val = self._label_for_combo_index(idx)
            self._selected_organ_label = label_val
        self._apply_organ_layers()

    def _on_ai_organ_opacity(self, value):
        self._organ_opacity = value / 100.0
        self._apply_organ_layers()

    def _on_ai_rest_opacity(self, value):
        self._rest_opacity = value / 100.0
        self._apply_organ_layers()

    def _label_for_combo_index(self, combo_idx):
        if combo_idx <= 0:
            return None
        name = self._ai_organ_combo.itemText(combo_idx)
        for lv, nm in self._organ_names_by_label.items():
            if nm == name:
                return lv
        return None

    # ======================================================================
    # Tissue layer handlers
    # ======================================================================
    def _on_tissue_preset(self, name, checked):
        if not checked:
            return
        self.tissue_low, self.tissue_high = TISSUE_PRESETS[name]
        self.tissue_threshold_slider.blockSignals(True)
        self.tissue_threshold_slider.setValue(self.tissue_low)
        self.tissue_threshold_slider.blockSignals(False)
        self._rebuild_opacity_function()

    def _on_tissue_threshold_changed(self, value):
        self.tissue_low = value
        if self.tissue_low > self.tissue_high:
            self.tissue_high = 255
        self._rebuild_opacity_function()

    # ======================================================================
    # Public helpers
    # ======================================================================
    def set_organ_names(self, names_by_label):
        self._organ_names_by_label = dict(names_by_label)
        self._organ_name_list = list(names_by_label.values())

        if self._ai_seg_available:
            self._ai_organ_combo.blockSignals(True)
            self._ai_organ_combo.clear()
            self._ai_organ_combo.addItem("\u2014 None \u2014")
            for name in self._organ_name_list:
                self._ai_organ_combo.addItem(name)
            self._ai_organ_combo.blockSignals(False)

    def reset_all(self):
        self.box_crop_checkbox.setChecked(False)

        for axis in ["x", "y", "z"]:
            self.clip_checkboxes[axis].setChecked(False)
            self.clip_flipped[axis] = False
            depth, height, width = self.image_array.shape
            mid = {"x": width, "y": height, "z": depth}[axis] // 2
            self.clip_sliders[axis].setValue(mid)

        if self._ai_seg_available:
            self._ai_organ_combo.setCurrentIndex(0)
            self._ai_organ_slider.setValue(100)
            self._ai_rest_slider.setValue(100)
            self._selected_organ_label = None
            self._organ_opacity = 1.0
            self._rest_opacity = 1.0

        for btn in self.tissue_preset_group.buttons():
            if btn.text() == "All tissue":
                btn.setChecked(True)
        self.tissue_threshold_slider.setValue(0)

        self.volume_mapper.RemoveAllClippingPlanes()
        self._apply_organ_layers()
        self.vtk_widget.GetRenderWindow().Render()

    def closeEvent(self, event):
        self._closing = True
        if self._seg_worker and self._seg_worker.isRunning():
            self._seg_worker.quit()
            self._seg_worker.wait(2000)
        try:
            self.box_widget.Off()
            rw = self.interactor.GetRenderWindow()
            rw.Finalize()
            self.interactor.TerminateApp()
        except Exception:
            pass
        super().closeEvent(event)
