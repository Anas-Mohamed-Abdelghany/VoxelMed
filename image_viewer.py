"""
image_viewer.py
---------------
ImageViewer: the main QMainWindow, assembled from focused mixin classes.
Each mixin lives in its own file and handles one concern:

  ImageProcessingMixin  – load, display, crosshairs, brightness/contrast
  SegmentationMixin     – brush / eraser drawing on the mask
  VTKRendererMixin      – 3-D volume rendering
  UIBuilderMixin        – toolbar, view sections, left sidebar, file I/O
"""

import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QSlider,
    QLabel, QComboBox, QVBoxLayout, QStackedLayout,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtkmodules.all as vtk
from vtkmodules.util import numpy_support

from image_label      import ImageLabel
from image_processing import ImageProcessingMixin
from segmentation     import SegmentationMixin
from vtk_renderer     import VTKRendererMixin
from ui               import UIBuilderMixin
from landmark_nav     import LandmarkNavMixin


class ImageViewer(
    LandmarkNavMixin,
    ImageProcessingMixin,
    SegmentationMixin,
    VTKRendererMixin,
    UIBuilderMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Medical Imaging Project")
        self.setWindowIcon(QIcon("resources/unnamed.ico"))
        self.setGeometry(100, 100, 1600, 900)

        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        root_layout = QVBoxLayout(self.main_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.main_stack = QStackedLayout()
        root_layout.addLayout(self.main_stack)

        # ---- Page 0: MPR view grid ---------------------------------------
        self.mpr_widget = QWidget()
        self.layout = QGridLayout(self.mpr_widget)
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(50, 50, 50, 50)

        self.image_labels  = [ImageLabel(self) for _ in range(3)]
        self.sliders       = [QSlider(Qt.Horizontal) for _ in range(3)]
        self.images        = [None] * 3
        self.current_slice = [0] * 3
        self.image_size    = (800, 420)

        self.notification_label = QLabel("")
        self.notification_label.setStyleSheet("color: green; font-size: 14px;")
        self.notification_label.setAlignment(Qt.AlignCenter)

        # Build view panels (axial / sagittal / coronal)
        self.create_view_section(0, 0, 0)  # Axial      – top-left
        self.create_view_section(1, 0, 1)  # Sagittal   – top-right
        self.create_view_section(2, 1, 0)  # Coronal    – bottom-left

        self.create_toolbar()

        # 3-D rendering panel (bottom-right)
        self.vtk_widget = QVTKRenderWindowInteractor(self.mpr_widget)
        self.layout.addWidget(self.vtk_widget, 1, 1)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(1, 1, 1)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()

        self.layout.setColumnStretch(0, 1)
        self.layout.setColumnStretch(1, 1)

        self.main_stack.addWidget(self.mpr_widget)

        # ---- Page 1: 3D Lab (empty placeholder, VTK created on enter) ----
        self.lab_widget = QWidget()
        self._lab_layout = QVBoxLayout(self.lab_widget)
        self._lab_layout.setContentsMargins(0, 0, 0, 0)
        self.main_stack.addWidget(self.lab_widget)
        self.main_stack.setCurrentIndex(0)

        # ---- 3D Lab state (VTK handles created/destroyed dynamically) ----
        self._lab_active = False
        self.lab_vtk_widget = None
        self.lab_renderer = None
        self.lab_interactor = None
        self._lab_vtk_image = None
        self._lab_volume_mapper = None
        self._lab_volume = None
        self._lab_volume_property = None
        self._lab_ctf = None
        self._lab_otf = None
        self._lab_box_widget = None
        self._lab_clip_planes = {}
        self._lab_clip_enabled = {"x": False, "y": False, "z": False}
        self._lab_clip_flipped = {"x": False, "y": False, "z": False}
        self._lab_bounds = None
        self._lab_label_volume = None

        # Lab AI segmentation state
        self._lab_seg_worker = None
        self._lab_ai_seg_available = False
        self._lab_selected_organ_label = None
        self._lab_organ_opacity = 1.0
        self._lab_rest_opacity = 1.0
        self._lab_organ_names_by_label = {}
        self._lab_organ_name_list = []

        # Lab tissue threshold state
        self._lab_tissue_low = 0
        self._lab_tissue_high = 255

        # Segmentation
        self.segmentation_mask = None
        self.drawing_color     = (255, 0, 0)  # Red
        self.brush_thickness   = 2
        self.eraser_thickness  = 2

        self.interactor.Initialize()

        # Image state
        self.image_array      = None
        self.current_nifti_path = None

        # Crosshairs
        self.crosshair_positions = [(0, 0), (0, 0), (0, 0)]

        # Landmark navigation state (populated by LandmarkNavMixin)
        self.landmark_positions  = {}
        self.active_landmark     = None
        self._landmark_highlight = False
        self.label_colormap      = {}
        self._landmark_thread    = None
        self._selected_organs    = set()
        self._organ_checkboxes   = {}
        self._active_section     = None
        self._landmark_buttons_container = None

        # Abdomen detection – segmentation tools only work on abdominal CT scans
        self.is_abdomen = False

        # Per-view brightness / contrast / offsets / rotation
        self.brightness      = [0, 0, 0]
        self.contrast        = [1, 1, 1]
        self.h_offset        = [0, 0, 0]
        self.v_offset        = [0, 0, 0]
        self.rotation_angles = [0, 180, 180]

        # Voxel spacing and caliper measurements
        self.spacing         = (1.0, 1.0, 1.0)
        self.caliper_lines   = [None, None, None]

        # Tool selector (also used by SegmentationMixin)
        self.segmentation_tools = QComboBox()
        self.segmentation_tools.addItems(["Move", "Brush", "Eraser", "Smart Brush", "Smart Caliper"])
        self.segmentation_tools.currentTextChanged.connect(self.update_current_tool)
        self.current_tool = "Move"

        # Build the left sidebar (must come after segmentation_tools is ready)
        self.create_left_sidebar()

    # ======================================================================
    # 3D Lab mode switching
    # ======================================================================
    def _enter_lab_mode(self):
        if self.image_array is None:
            self.notification_label.setText("Load an image first.")
            self.lab_btn.setChecked(False)
            return
        if self._lab_active:
            return
        self._lab_active = True

        # Create VTK widget dynamically (avoid conflict with MPR interactor)
        self.lab_vtk_widget = QVTKRenderWindowInteractor(self.lab_widget)
        self._lab_layout.addWidget(self.lab_vtk_widget)

        self.lab_renderer = vtk.vtkRenderer()
        self.lab_renderer.SetBackground(1.0, 1.0, 1.0)
        self.lab_vtk_widget.GetRenderWindow().AddRenderer(self.lab_renderer)
        self.lab_interactor = self.lab_vtk_widget.GetRenderWindow().GetInteractor()

        self._build_lab_vtk_pipeline()
        self.main_stack.setCurrentIndex(1)
        self.show_lab_page()
        self.lab_interactor.Initialize()
        self.lab_renderer.ResetCamera()

        # If a segmentation mask already exists, populate organ controls
        if self.segmentation_mask is not None and not self._lab_ai_seg_available:
            self._lab_ai_seg_available = True
            label_names = getattr(self, '_label_organ_names', {})
            unique_labels = sorted(set(self.segmentation_mask[self.segmentation_mask > 0]))
            self._lab_organ_name_list = []
            self._lab_organ_names_by_label = {}
            for label_val in unique_labels:
                name = label_names.get(label_val, f"Region {label_val}")
                self._lab_organ_names_by_label[label_val] = name
                self._lab_organ_name_list.append(name)
            self._lab_ai_organ_combo.blockSignals(True)
            self._lab_ai_organ_combo.clear()
            self._lab_ai_organ_combo.addItem("\u2014 None \u2014")
            for name in self._lab_organ_name_list:
                self._lab_ai_organ_combo.addItem(name)
            self._lab_ai_organ_combo.blockSignals(False)
            self._lab_ai_stack.setCurrentIndex(1)

        self.lab_vtk_widget.GetRenderWindow().Render()

    def _exit_lab_mode(self):
        self._lab_active = False
        self.main_stack.setCurrentIndex(0)
        self.lab_btn.setChecked(False)
        self.show_settings_page()

        # Destroy lab VTK widget to free OpenGL context
        if self.lab_vtk_widget is not None:
            try:
                self.lab_interactor.GetRenderWindow().Finalize()
                self.lab_interactor.TerminateApp()
            except Exception:
                pass
            self._lab_layout.removeWidget(self.lab_vtk_widget)
            self.lab_vtk_widget.setParent(None)
            self.lab_vtk_widget.deleteLater()
            self.lab_vtk_widget = None
            self.lab_renderer = None
            self.lab_interactor = None
            self._lab_vtk_image = None
            self._lab_volume_mapper = None
            self._lab_volume = None
            self._lab_volume_property = None
            self._lab_ctf = None
            self._lab_otf = None
            self._lab_box_widget = None
            self._lab_clip_planes = {}
            self._lab_clip_enabled = {"x": False, "y": False, "z": False}
            self._lab_clip_flipped = {"x": False, "y": False, "z": False}
            self._lab_bounds = None
            self._label_opacity_funcs = {}

    # ======================================================================
    # 3D Lab VTK pipeline
    # ======================================================================
    def _build_lab_vtk_pipeline(self):
        arr = self.image_array
        depth, height, width = arr.shape

        arr_f = arr.astype(np.float64)
        amin, amax = arr_f.min(), arr_f.max()
        if amax > amin:
            arr_u8 = ((arr_f - amin) / (amax - amin) * 255.0).astype(np.uint8)
        else:
            arr_u8 = np.zeros_like(arr_f, dtype=np.uint8)

        sx, sy, sz = self.spacing if len(self.spacing) == 3 else (1.0, 1.0, 1.0)

        # Build intensity volume
        self._lab_vtk_image = vtk.vtkImageData()
        self._lab_vtk_image.SetDimensions(width, height, depth)
        self._lab_vtk_image.SetSpacing(sx, sy, sz)
        self._lab_vtk_image.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)

        flipped = np.flip(arr_u8, axis=0)
        vtk_array = numpy_support.numpy_to_vtk(
            flipped.ravel(), deep=True, array_type=vtk.VTK_UNSIGNED_CHAR
        )
        self._lab_vtk_image.GetPointData().SetScalars(vtk_array)

        self._lab_volume_mapper = vtk.vtkSmartVolumeMapper()
        self._lab_volume_mapper.SetInputData(self._lab_vtk_image)
        self._lab_volume_mapper.SetBlendModeToComposite()

        self._lab_volume_property = vtk.vtkVolumeProperty()
        self._lab_volume_property.ShadeOn()
        self._lab_volume_property.SetInterpolationTypeToLinear()

        self._lab_ctf = vtk.vtkColorTransferFunction()
        self._lab_ctf.AddRGBPoint(0,   0.0, 0.0, 0.0)
        self._lab_ctf.AddRGBPoint(128, 0.8, 0.7, 0.6)
        self._lab_ctf.AddRGBPoint(255, 1.0, 1.0, 1.0)
        self._lab_volume_property.SetColor(self._lab_ctf)

        self._lab_otf = vtk.vtkPiecewiseFunction()
        self._lab_rebuild_opacity_function()
        self._lab_volume_property.SetScalarOpacity(self._lab_otf)

        # Set up label map for per-organ opacity control
        self._label_opacity_funcs = {}
        self._use_label_map = False
        if self.segmentation_mask is not None:
            self._lab_label_volume = np.flip(self.segmentation_mask, axis=0)
            label_vtk = vtk.vtkImageData()
            label_vtk.SetDimensions(width, height, depth)
            label_vtk.SetSpacing(sx, sy, sz)
            label_vtk.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)
            flipped_labels = np.flip(self.segmentation_mask, axis=0).astype(np.uint8)
            label_arr = numpy_support.numpy_to_vtk(
                flipped_labels.ravel(), deep=True, array_type=vtk.VTK_UNSIGNED_CHAR
            )
            label_vtk.GetPointData().SetScalars(label_arr)
            if hasattr(self._lab_volume_mapper, 'SetLabelMap'):
                self._lab_volume_mapper.SetLabelMap(label_vtk)
                unique_labels = sorted(set(self.segmentation_mask[self.segmentation_mask > 0]))
                for label_val in unique_labels:
                    func = vtk.vtkPiecewiseFunction()
                    func.AddPoint(0, 0.0)
                    func.AddPoint(1, 1.0)
                    func.AddPoint(255, 1.0)
                    self._lab_volume_property.SetLabelScalarOpacity(int(label_val), func)
                    self._label_opacity_funcs[int(label_val)] = func
                self._use_label_map = True
        else:
            self._lab_label_volume = None

        self._lab_volume = vtk.vtkVolume()
        self._lab_volume.SetMapper(self._lab_volume_mapper)
        self._lab_volume.SetProperty(self._lab_volume_property)

        self.lab_renderer.AddVolume(self._lab_volume)

        # Box widget for interactive cropping
        self._lab_box_widget = vtk.vtkBoxWidget()
        self._lab_box_widget.SetInteractor(self.lab_interactor)
        self._lab_box_widget.SetPlaceFactor(1.0)
        self._lab_box_widget.PlaceWidget(self._lab_vtk_image.GetBounds())
        self._lab_box_widget.InsideOutOn()
        self._lab_box_widget.GetOutlineProperty().SetColor(1, 0.6, 0)
        self._lab_box_widget.AddObserver("InteractionEvent", self._on_lab_box_widget_interaction)
        self._lab_box_widget.Off()

        bounds = self._lab_vtk_image.GetBounds()
        self._lab_clip_planes["x"] = vtk.vtkPlane()
        self._lab_clip_planes["x"].SetOrigin((bounds[0] + bounds[1]) / 2.0, 0, 0)
        self._lab_clip_planes["x"].SetNormal(1, 0, 0)

        self._lab_clip_planes["y"] = vtk.vtkPlane()
        self._lab_clip_planes["y"].SetOrigin(0, (bounds[2] + bounds[3]) / 2.0, 0)
        self._lab_clip_planes["y"].SetNormal(0, 1, 0)

        self._lab_clip_planes["z"] = vtk.vtkPlane()
        self._lab_clip_planes["z"].SetOrigin(0, 0, (bounds[4] + bounds[5]) / 2.0)
        self._lab_clip_planes["z"].SetNormal(0, 0, 1)

        self._lab_bounds = bounds

    def _lab_rebuild_opacity_function(self):
        if self._lab_otf is None:
            return
        self._lab_otf.RemoveAllPoints()
        low, high = self._lab_tissue_low, self._lab_tissue_high

        if low <= 0:
            self._lab_otf.AddPoint(0, 0.0)
        else:
            self._lab_otf.AddPoint(0, 0.0)
            self._lab_otf.AddPoint(max(0, low - 1), 0.0)

        self._lab_otf.AddPoint(max(0, low), 0.05 if low > 0 else 0.0)
        mid = (low + high) / 2.0
        self._lab_otf.AddPoint(mid, 0.4)
        self._lab_otf.AddPoint(min(255, high), 0.85)
        self._lab_otf.AddPoint(255, 1.0)

        if self.lab_vtk_widget is not None:
            self.lab_vtk_widget.GetRenderWindow().Render()

    def _lab_apply_organ_layers(self):
        if self._use_label_map and self._label_opacity_funcs:
            for label_val, func in self._label_opacity_funcs.items():
                if self._lab_selected_organ_label is not None and label_val == self._lab_selected_organ_label:
                    op = self._lab_organ_opacity
                else:
                    op = self._lab_rest_opacity
                func.RemoveAllPoints()
                func.AddPoint(0, 0.0)
                func.AddPoint(1, op)
                func.AddPoint(255, op)
        elif self._lab_label_volume is not None and self.segmentation_mask is not None:
            arr = self.image_array.astype(np.float64)
            amin, amax = arr.min(), arr.max()
            if amax > amin:
                base_u8 = ((arr - amin) / (amax - amin) * 255.0)
            else:
                base_u8 = np.zeros_like(arr)
            scale = np.ones_like(base_u8, dtype=np.float64)
            if self._lab_selected_organ_label is not None:
                sel = (self.segmentation_mask == self._lab_selected_organ_label)
                scale[sel] = self._lab_organ_opacity
                other = (self.segmentation_mask > 0) & (~sel)
                scale[other] = self._lab_rest_opacity
            else:
                other = (self.segmentation_mask > 0)
                scale[other] = self._lab_rest_opacity
            adjusted = np.clip(base_u8 * scale, 0, 255).astype(np.uint8)
            flipped = np.flip(adjusted, axis=0)
            depth, height, width = self.image_array.shape
            new_img = vtk.vtkImageData()
            new_img.SetDimensions(width, height, depth)
            sx, sy, sz = self.spacing if len(self.spacing) == 3 else (1.0, 1.0, 1.0)
            new_img.SetSpacing(sx, sy, sz)
            vtk_arr = numpy_support.numpy_to_vtk(
                flipped.ravel(), deep=True, array_type=vtk.VTK_UNSIGNED_CHAR
            )
            new_img.GetPointData().SetScalars(vtk_arr)
            self._lab_volume_mapper.SetInputData(new_img)
            self._lab_vtk_image = new_img
            if self._lab_otf is not None:
                self._lab_otf.RemoveAllPoints()
                self._lab_otf.AddPoint(0, 0.0)
                self._lab_otf.AddPoint(255, 1.0)

        if self.lab_vtk_widget is not None:
            self.lab_vtk_widget.GetRenderWindow().Render()

    # ======================================================================
    # 3D Lab box crop handlers
    # ======================================================================
    def _on_lab_box_crop_toggled(self, state):
        enabled = state == Qt.Checked
        if enabled:
            self._lab_box_widget.On()
            self._lab_apply_box_clip()
        else:
            self._lab_box_widget.Off()
            self._lab_volume_mapper.RemoveAllClippingPlanes()
            self._lab_reapply_orthogonal_clips()
        if self.lab_vtk_widget is not None:
            self.lab_vtk_widget.GetRenderWindow().Render()

    def _on_lab_box_widget_interaction(self, widget, event):
        self._lab_apply_box_clip()

    def _lab_apply_box_clip(self):
        planes = vtk.vtkPlanes()
        self._lab_box_widget.GetPlanes(planes)
        self._lab_volume_mapper.RemoveAllClippingPlanes()
        self._lab_volume_mapper.SetClippingPlanes(planes)
        self._lab_reapply_orthogonal_clips(keep_existing=True)
        if self.lab_vtk_widget is not None:
            self.lab_vtk_widget.GetRenderWindow().Render()

    # ======================================================================
    # 3D Lab orthogonal clip-plane handlers
    # ======================================================================
    def _on_lab_clip_toggled(self, axis, state):
        self._lab_clip_enabled[axis] = (state == Qt.Checked)
        self._lab_reapply_orthogonal_clips()
        if self.lab_vtk_widget is not None:
            self.lab_vtk_widget.GetRenderWindow().Render()

    def _on_lab_clip_slider(self, axis, value):
        bounds = self._lab_bounds
        sx, sy, sz = self.spacing if len(self.spacing) == 3 else (1.0, 1.0, 1.0)
        if axis == "x":
            self._lab_clip_planes["x"].SetOrigin(bounds[0] + value * sx, 0, 0)
        elif axis == "y":
            self._lab_clip_planes["y"].SetOrigin(0, bounds[2] + value * sy, 0)
        else:
            self._lab_clip_planes["z"].SetOrigin(0, 0, bounds[4] + value * sz)
        self._lab_reapply_orthogonal_clips()
        if self.lab_vtk_widget is not None:
            self.lab_vtk_widget.GetRenderWindow().Render()

    def _on_lab_clip_flip(self, axis):
        self._lab_clip_flipped[axis] = not self._lab_clip_flipped[axis]
        normals = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}
        nx, ny, nz = normals[axis]
        sign = -1 if self._lab_clip_flipped[axis] else 1
        self._lab_clip_planes[axis].SetNormal(nx * sign, ny * sign, nz * sign)
        self._lab_reapply_orthogonal_clips()
        if self.lab_vtk_widget is not None:
            self.lab_vtk_widget.GetRenderWindow().Render()

    def _lab_reapply_orthogonal_clips(self, keep_existing=False):
        if not keep_existing:
            self._lab_volume_mapper.RemoveAllClippingPlanes()
            if self._lab_box_widget.GetEnabled():
                planes = vtk.vtkPlanes()
                self._lab_box_widget.GetPlanes(planes)
                self._lab_volume_mapper.SetClippingPlanes(planes)

        for axis, enabled in self._lab_clip_enabled.items():
            if enabled:
                self._lab_volume_mapper.AddClippingPlane(self._lab_clip_planes[axis])

    # ======================================================================
    # 3D Lab AI segmentation handlers
    # ======================================================================
    def _on_lab_ai_run(self):
        from volume_explorer import SegWorker
        self._lab_ai_run_btn.setEnabled(False)
        self._lab_ai_run_btn.setText("Running\u2026")
        self._lab_ai_progress.setText("Starting\u2026")
        self._lab_ai_progress.setVisible(True)

        self._lab_seg_worker = SegWorker(self.image_array, self.spacing, self)
        self._lab_seg_worker.finished.connect(self._on_lab_ai_seg_done)
        self._lab_seg_worker.error.connect(self._on_lab_ai_seg_error)
        self._lab_seg_worker.progress.connect(self._lab_ai_progress.setText)
        self._lab_seg_worker.start()

    def _on_lab_ai_seg_done(self, combined_mask, label_map):
        self.segmentation_mask    = combined_mask
        self.label_colormap       = label_map
        self._lab_label_volume    = np.flip(combined_mask, axis=0)
        self._lab_ai_seg_available = True
        self._lab_selected_organ_label = None
        self._lab_organ_opacity   = 1.0
        self._lab_rest_opacity    = 1.0

        from landmark_detector import get_all_organs
        all_organs = get_all_organs()
        all_stems_sorted = sorted(set(all_organs.values()))
        stem_to_name = {v: k for k, v in all_organs.items()}
        self._lab_organ_name_list = []
        self._lab_organ_names_by_label = {}
        for label_val in sorted(label_map.keys()):
            stem = all_stems_sorted[label_val - 1]
            name = stem_to_name.get(stem, f"Region {label_val}")
            self._lab_organ_names_by_label[label_val] = name
            self._lab_organ_name_list.append(name)

        self._lab_ai_organ_combo.blockSignals(True)
        self._lab_ai_organ_combo.clear()
        self._lab_ai_organ_combo.addItem("\u2014 None \u2014")
        for name in self._lab_organ_name_list:
            self._lab_ai_organ_combo.addItem(name)
        self._lab_ai_organ_combo.blockSignals(False)

        self._lab_ai_organ_slider.setValue(100)
        self._lab_ai_rest_slider.setValue(100)

        self._lab_ai_stack.setCurrentIndex(1)
        self._lab_apply_organ_layers()

    def _on_lab_ai_seg_error(self, msg):
        self._lab_ai_run_btn.setEnabled(True)
        self._lab_ai_run_btn.setText("Run AI Segmentation")
        self._lab_ai_progress.setText(f"Failed: {msg}")
        self._lab_ai_progress.setStyleSheet("color: #ff6666; font-size: 10px;")

    def _on_lab_ai_organ_selected(self, idx):
        if idx <= 0:
            self._lab_selected_organ_label = None
        else:
            name = self._lab_ai_organ_combo.itemText(idx)
            for lv, nm in self._lab_organ_names_by_label.items():
                if nm == name:
                    self._lab_selected_organ_label = lv
                    break
        self._lab_apply_organ_layers()

    def _on_lab_ai_organ_opacity(self, value):
        self._lab_organ_opacity = value / 100.0
        self._lab_apply_organ_layers()

    def _on_lab_ai_rest_opacity(self, value):
        self._lab_rest_opacity = value / 100.0
        self._lab_apply_organ_layers()

    # ======================================================================
    # 3D Lab tissue layer handlers
    # ======================================================================
    def _on_lab_tissue_preset(self, name, checked):
        if not checked:
            return
        from volume_explorer_ui import TISSUE_PRESETS
        self._lab_tissue_low, self._lab_tissue_high = TISSUE_PRESETS[name]
        self._lab_tissue_threshold_slider.blockSignals(True)
        self._lab_tissue_threshold_slider.setValue(self._lab_tissue_low)
        self._lab_tissue_threshold_slider.blockSignals(False)
        self._lab_rebuild_opacity_function()

    def _on_lab_tissue_threshold_changed(self, value):
        self._lab_tissue_low = value
        if self._lab_tissue_low > self._lab_tissue_high:
            self._lab_tissue_high = 255
        self._lab_rebuild_opacity_function()

    # ======================================================================
    # 3D Lab reset
    # ======================================================================
    def _lab_reset_all(self):
        if hasattr(self, '_lab_box_crop_checkbox'):
            self._lab_box_crop_checkbox.setChecked(False)

        for axis in ["x", "y", "z"]:
            if hasattr(self, '_lab_clip_checkboxes'):
                self._lab_clip_checkboxes[axis].setChecked(False)
            self._lab_clip_flipped[axis] = False
            depth, height, width = self.image_array.shape
            mid = {"x": width, "y": height, "z": depth}[axis] // 2
            if hasattr(self, '_lab_clip_sliders'):
                self._lab_clip_sliders[axis].setValue(mid)

        if self._lab_ai_seg_available:
            if hasattr(self, '_lab_ai_organ_combo'):
                self._lab_ai_organ_combo.setCurrentIndex(0)
            if hasattr(self, '_lab_ai_organ_slider'):
                self._lab_ai_organ_slider.setValue(100)
            if hasattr(self, '_lab_ai_rest_slider'):
                self._lab_ai_rest_slider.setValue(100)
            self._lab_selected_organ_label = None
            self._lab_organ_opacity = 1.0
            self._lab_rest_opacity = 1.0

        if hasattr(self, '_lab_tissue_preset_group'):
            for btn in self._lab_tissue_preset_group.buttons():
                if btn.text() == "All tissue":
                    btn.setChecked(True)
        if hasattr(self, '_lab_tissue_threshold_slider'):
            self._lab_tissue_threshold_slider.setValue(0)

        if self._lab_volume_mapper:
            self._lab_volume_mapper.RemoveAllClippingPlanes()
        self._lab_apply_organ_layers()
        if self.lab_vtk_widget is not None:
            self.lab_vtk_widget.GetRenderWindow().Render()

    # ======================================================================
    # Clean shutdown — finalize MPR VTK before Qt tears down the window
    # ======================================================================
    def closeEvent(self, event):
        if self._lab_active:
            self._exit_lab_mode()
        try:
            rw = self.interactor.GetRenderWindow()
            rw.Finalize()
            self.interactor.TerminateApp()
        except Exception:
            pass
        super().closeEvent(event)
