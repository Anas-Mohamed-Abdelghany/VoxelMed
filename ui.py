"""
ui.py
-----
Mixin that builds the toolbar, main view sections, and left sidebar.
All widget construction lives here so ImageViewer.__init__ stays lean.
"""

import os
import tempfile
import SimpleITK as sitk
import nibabel as nib
import numpy as np

from PyQt5.QtWidgets import (
    QFrame, QGridLayout, QLabel, QSlider, QSizePolicy,
    QVBoxLayout, QHBoxLayout, QPushButton, QDockWidget, QWidget,
    QComboBox, QSpinBox, QToolBar, QAction, QFileDialog, QApplication,
    QScrollArea, QGroupBox, QCheckBox, QButtonGroup, QRadioButton,
    QStackedWidget,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon


class UIBuilderMixin:
    # ---------------------------------------------------------------- views
    def create_view_section(self, index, row, col):
        section_widget = QFrame()
        section_widget.setFrameShape(QFrame.StyledPanel)
        section_widget.setFrameShadow(QFrame.Raised)

        section_layout = QGridLayout(section_widget)
        section_layout.setSpacing(5)
        section_layout.setContentsMargins(4, 4, 4, 4)

        # Configure slice slider — placed in the sidebar settings panel
        slider = self.sliders[index]
        slider.setMinimum(0)
        slider.setMaximum(0)
        slider.setValue(0)
        slider.setTickPosition(QSlider.TicksBelow)
        slider.setTickInterval(1)
        slider.valueChanged.connect(
            lambda value, idx=index: self.update_image_slice(idx)
        )

        # Image label fills the section directly — no inner frame
        image_label = self.image_labels[index]
        image_label.setFixedSize(*self.image_size)
        image_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        image_label.setStyleSheet("background-color: black;")
        section_layout.addWidget(image_label, 0, 0, 1, 1)

        title_label = QLabel(self.get_section_title(index))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            "font-weight: bold; font-size: 12px; color: white;"
        )
        section_layout.addWidget(title_label, 1, 0, 1, 1)

        section_widget.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #444444;
                border-radius: 5px;
            }
            QPushButton, QSlider {
                color: black;
            }
        """)

        self.layout.addWidget(section_widget, row, col)


    def get_section_title(self, index):
        return ["Axial", "Sagittal", "Coronal"][index] if index < 3 else "Unknown"

    # --------------------------------------------------------------- toolbar
    def create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        open_action = QAction(QIcon.fromTheme("document-open"), "Open", self)
        open_action.triggered.connect(self.load_image)
        toolbar.addAction(open_action)

        save_action = QAction(QIcon.fromTheme("document-save"), "Save", self)
        save_action.triggered.connect(self.save_image)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        import_dicom_action = QAction(QIcon.fromTheme("folder-open"), "Import Multiple DICOM", self)
        import_dicom_action.triggered.connect(self.import_dicom)
        toolbar.addAction(import_dicom_action)

        save_nifti_action = QAction(QIcon.fromTheme("save"), "Save NIfTI", self)
        save_nifti_action.triggered.connect(self.save_nifti)
        toolbar.addAction(save_nifti_action)

        toolbar.addSeparator()

        help_action = QAction(QIcon.fromTheme("help-contents"), "Help", self)
        help_action.triggered.connect(self.show_help)
        toolbar.addAction(help_action)

    def set_tool(self, tool_name):
        self.current_tool = tool_name
        self.segmentation_tools.setCurrentText(tool_name)

    # -------------------------------------------------------------- sidebar mode switching
    def show_settings_page(self):
        self.settings_btn.setChecked(True)
        self.ai_seg_btn.setChecked(False)
        self.lab_btn.setChecked(False)
        self.settings_page.setVisible(True)
        self.segmentation_page.setVisible(False)
        if hasattr(self, 'lab_page'):
            self.lab_page.setVisible(False)
        if self._lab_active:
            self._exit_lab_mode()

    def show_segmentation_page(self):
        self.settings_btn.setChecked(False)
        self.ai_seg_btn.setChecked(True)
        self.lab_btn.setChecked(False)
        self.settings_page.setVisible(False)
        self.segmentation_page.setVisible(True)
        if hasattr(self, 'lab_page'):
            self.lab_page.setVisible(False)
        if self._lab_active:
            self._exit_lab_mode()

    def show_lab_page(self):
        self.settings_btn.setChecked(False)
        self.ai_seg_btn.setChecked(False)
        self.lab_btn.setChecked(True)
        self.settings_page.setVisible(False)
        self.segmentation_page.setVisible(False)
        self.lab_page.setVisible(True)

    def _build_lab_sidebar_page(self, layout):
        """Build the 3D Lab control panel in the sidebar."""
        # Title
        title = QLabel("3D Lab")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #005577; padding: 0 8px;")
        layout.addWidget(title)

        subtitle = QLabel("Cut, crop, and peel away layers to see inside the volume.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #666666; font-size: 10px; padding: 0 8px 4px 8px;")
        layout.addWidget(subtitle)

        # Scroll area for the controls (sidebar is 265px wide, need scroll for many controls)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; } QScrollBar:vertical { width: 6px; }")

        inner = QWidget()
        inner.setStyleSheet("background-color: white;")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(8, 4, 8, 4)
        inner_layout.setSpacing(4)

        # -- Box Crop --
        box = QGroupBox("Box Crop")
        box.setStyleSheet(self._lab_group_style())
        bv = QVBoxLayout(box)
        info = QLabel("Drag the box handles in the 3D view to cut away everything outside the box.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #555555; font-size: 11px;")
        bv.addWidget(info)
        self._lab_box_crop_checkbox = QCheckBox("Enable box crop")
        self._lab_box_crop_checkbox.setStyleSheet("color: #333333; font-size: 11px;")
        self._lab_box_crop_checkbox.stateChanged.connect(self._on_lab_box_crop_toggled)
        bv.addWidget(self._lab_box_crop_checkbox)
        inner_layout.addWidget(box)

        inner_layout.addWidget(self._lab_hline())

        # -- Orthogonal Clips --
        clip_box = QGroupBox("Orthogonal Clips")
        clip_box.setStyleSheet(self._lab_group_style())
        cv = QVBoxLayout(clip_box)
        cinfo = QLabel("Slide to cut the volume along an axis. 'Flip' swaps which half is removed.")
        cinfo.setWordWrap(True)
        cinfo.setStyleSheet("color: #555555; font-size: 11px;")
        cv.addWidget(cinfo)

        self._lab_clip_checkboxes = {}
        self._lab_clip_sliders = {}
        axis_dims = None

        for axis in ["x", "y", "z"]:
            row = QHBoxLayout()
            cb = QCheckBox(axis.upper())
            cb.setFixedWidth(30)
            cb.setStyleSheet("color: #333333; font-size: 11px;")
            cb.stateChanged.connect(lambda state, a=axis: self._on_lab_clip_toggled(a, state))
            row.addWidget(cb)
            self._lab_clip_checkboxes[axis] = cb

            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(100)
            slider.setValue(50)
            slider.valueChanged.connect(lambda val, a=axis: self._on_lab_clip_slider(a, val))
            row.addWidget(slider)
            self._lab_clip_sliders[axis] = slider

            flip_btn = QPushButton("Flip")
            flip_btn.setFixedWidth(45)
            flip_btn.clicked.connect(lambda checked, a=axis: self._on_lab_clip_flip(a))
            row.addWidget(flip_btn)

            cv.addLayout(row)
        inner_layout.addWidget(clip_box)

        inner_layout.addWidget(self._lab_hline())

        # -- AI Segmentation --
        ai_box = QGroupBox("AI Segmentation")
        ai_box.setStyleSheet(self._lab_group_style())
        av = QVBoxLayout(ai_box)
        av.setContentsMargins(6, 4, 6, 6)
        av.setSpacing(3)

        self._lab_ai_stack = QStackedWidget()

        # Page 0 — Run button
        run_page = QWidget()
        rp = QVBoxLayout(run_page)
        rp.setContentsMargins(0, 0, 0, 0)
        rp.setSpacing(2)

        self._lab_ai_run_btn = QPushButton("Run AI Segmentation")
        self._lab_ai_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #005577; color: white;
                border: 1px solid #004466; border-radius: 4px;
                padding: 5px; font-size: 11px;
            }
            QPushButton:hover  { background-color: #007799; }
            QPushButton:disabled { background-color: #cccccc; color: #888888; border-color: #aaaaaa; }
        """)
        self._lab_ai_run_btn.clicked.connect(self._on_lab_ai_run)
        rp.addWidget(self._lab_ai_run_btn)

        self._lab_ai_progress = QLabel("")
        self._lab_ai_progress.setWordWrap(True)
        self._lab_ai_progress.setStyleSheet("color: #555555; font-size: 10px;")
        self._lab_ai_progress.setVisible(False)
        rp.addWidget(self._lab_ai_progress)

        self._lab_ai_stack.addWidget(run_page)

        # Page 1 — Controls (organ selector + two sliders)
        ctrl_page = QWidget()
        cp = QVBoxLayout(ctrl_page)
        cp.setContentsMargins(0, 0, 0, 0)
        cp.setSpacing(2)

        organ_row = QHBoxLayout()
        organ_lbl = QLabel("Organ:")
        organ_lbl.setStyleSheet("color: #333333; font-size: 10px;")
        organ_row.addWidget(organ_lbl)
        self._lab_ai_organ_combo = QComboBox()
        self._lab_ai_organ_combo.setStyleSheet(
            "font-size: 10px; padding: 1px; color: #333333; "
            "background-color: white; "
            "QComboBox QAbstractItemView { color: #333333; background-color: white; selection-background-color: #cceeff; }"
        )
        self._lab_ai_organ_combo.currentIndexChanged.connect(self._on_lab_ai_organ_selected)
        organ_row.addWidget(self._lab_ai_organ_combo, stretch=1)
        cp.addLayout(organ_row)

        olbl = QLabel("Organ opacity:")
        olbl.setStyleSheet("color: #333333; font-size: 10px;")
        cp.addWidget(olbl)
        self._lab_ai_organ_slider = QSlider(Qt.Horizontal)
        self._lab_ai_organ_slider.setRange(0, 100)
        self._lab_ai_organ_slider.setValue(100)
        self._lab_ai_organ_slider.valueChanged.connect(self._on_lab_ai_organ_opacity)
        cp.addWidget(self._lab_ai_organ_slider)

        rlbl = QLabel("Rest of volume opacity:")
        rlbl.setStyleSheet("color: #333333; font-size: 10px;")
        cp.addWidget(rlbl)
        self._lab_ai_rest_slider = QSlider(Qt.Horizontal)
        self._lab_ai_rest_slider.setRange(0, 100)
        self._lab_ai_rest_slider.setValue(100)
        self._lab_ai_rest_slider.valueChanged.connect(self._on_lab_ai_rest_opacity)
        cp.addWidget(self._lab_ai_rest_slider)

        self._lab_ai_stack.addWidget(ctrl_page)
        self._lab_ai_stack.setCurrentIndex(0)

        av.addWidget(self._lab_ai_stack)
        inner_layout.addWidget(ai_box)

        inner_layout.addWidget(self._lab_hline())

        # -- Tissue Layers --
        tissue_box = QGroupBox("Tissue Layers (intensity)")
        tissue_box.setStyleSheet(self._lab_group_style())
        tv = QVBoxLayout(tissue_box)
        tinfo = QLabel("Peel back low-density tissue (skin/fat) to reveal denser structures (organs/bone).")
        tinfo.setWordWrap(True)
        tinfo.setStyleSheet("color: #555555; font-size: 11px;")
        tv.addWidget(tinfo)

        from volume_explorer_ui import TISSUE_PRESETS
        preset_col = QVBoxLayout()
        preset_col.setSpacing(1)
        self._lab_tissue_preset_group = QButtonGroup(self)
        for name in TISSUE_PRESETS:
            btn = QRadioButton(name)
            btn.setStyleSheet("font-size: 11px; color: #333333;")
            if name == "All tissue":
                btn.setChecked(True)
            btn.toggled.connect(lambda checked, n=name: self._on_lab_tissue_preset(n, checked))
            self._lab_tissue_preset_group.addButton(btn)
            preset_col.addWidget(btn)
        tv.addLayout(preset_col)

        tv.addWidget(QLabel("lower-bound cutoff:"))
        self._lab_tissue_threshold_slider = QSlider(Qt.Horizontal)
        self._lab_tissue_threshold_slider.setRange(0, 255)
        self._lab_tissue_threshold_slider.setValue(0)
        self._lab_tissue_threshold_slider.valueChanged.connect(self._on_lab_tissue_threshold_changed)
        tv.addWidget(self._lab_tissue_threshold_slider)

        inner_layout.addWidget(tissue_box)

        inner_layout.addWidget(self._lab_hline())

        # Reset button
        reset_btn = QPushButton("Reset All")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #dddddd; color: #333333;
                font-weight: bold; padding: 5px; border-radius: 4px;
                font-size: 11px; border: 1px solid #cccccc;
            }
            QPushButton:hover { background-color: #cccccc; }
        """)
        reset_btn.clicked.connect(self._lab_reset_all)
        inner_layout.addWidget(reset_btn)

        inner_layout.addStretch()

        scroll.setWidget(inner)
        layout.addWidget(scroll)

    def _lab_group_style(self):
        return """
            QGroupBox {
                color: #333333;
                font-weight: bold;
                font-size: 12px;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 6px;
                padding-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }
            QLabel { color: #555555; }
            QCheckBox { color: #333333; }
            QRadioButton { color: #333333; }
        """

    def _lab_hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: #cccccc;")
        return line

    # -------------------------------------------------------------- sidebar
    def create_left_sidebar(self):
        sidebar = QDockWidget("", self)
        sidebar.setFeatures(QDockWidget.NoDockWidgetFeatures)
        sidebar.setTitleBarWidget(QWidget())

        sidebar.setFixedWidth(265)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; border-right: 2px solid #555555; }")

        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- toggle buttons ----
        toggle_layout = QHBoxLayout()
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        toggle_layout.setSpacing(0)

        self.settings_btn = QPushButton("Main")
        self.settings_btn.setCheckable(True)
        self.settings_btn.setChecked(True)
        self.ai_seg_btn = QPushButton("AI Segmentation")
        self.ai_seg_btn.setCheckable(True)
        self.lab_btn = QPushButton("3D Lab")
        self.lab_btn.setCheckable(True)

        tab_style = """
            QPushButton {
                background-color: white;
                color: #888888;
                border: none;
                border-bottom: 2px solid #cccccc;
                padding: 10px 0px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:checked {
                background-color: white;
                color: #005577;
                border-bottom: 2px solid #005577;
            }
            QPushButton:hover:!checked {
                color: #333333;
                border-bottom: 2px solid #aaaaaa;
            }
        """
        self.settings_btn.setStyleSheet(tab_style)
        self.ai_seg_btn.setStyleSheet(tab_style)
        self.lab_btn.setStyleSheet(tab_style)

        toggle_layout.addWidget(self.settings_btn)
        toggle_layout.addWidget(self.ai_seg_btn)
        toggle_layout.addWidget(self.lab_btn)
        main_layout.addLayout(toggle_layout)

        # ---- content area ----
        content_area = QWidget()
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # -- settings page (all the original sidebar content) --
        self.settings_page = QWidget()
        settings_layout = QVBoxLayout(self.settings_page)
        settings_layout.setContentsMargins(8, 8, 8, 8)

        # Tool selection
        settings_layout.addWidget(QLabel("Tool:"))
        settings_layout.addWidget(self.segmentation_tools)

        # Color selection
        color_button = QPushButton("Select Color")
        color_button.clicked.connect(self.select_color)
        settings_layout.addWidget(color_button)

        # Brush size
        settings_layout.addWidget(QLabel("Brush Size:"))
        brush_size_slider = QSlider(Qt.Horizontal)
        brush_size_slider.setRange(1, 20)
        brush_size_slider.setValue(self.brush_thickness)
        brush_size_slider.valueChanged.connect(self.update_brush_size)
        settings_layout.addWidget(brush_size_slider)

        # Eraser size
        settings_layout.addWidget(QLabel("Eraser Size:"))
        eraser_size_slider = QSlider(Qt.Horizontal)
        eraser_size_slider.setRange(1, 20)
        eraser_size_slider.setValue(self.eraser_thickness)
        eraser_size_slider.valueChanged.connect(self.update_eraser_size)
        settings_layout.addWidget(eraser_size_slider)

        # Separator
        hline = QFrame()
        hline.setFrameShape(QFrame.HLine)
        hline.setFrameShadow(QFrame.Sunken)
        settings_layout.addWidget(hline)

        # Per-view settings
        for i, view_name in enumerate(["Axial", "Sagittal", "Coronal"]):
            view_settings_button = QPushButton(f"{view_name} Settings")
            view_settings_button.clicked.connect(
                lambda checked, idx=i: self.toggle_view_settings(idx)
            )
            settings_layout.addWidget(view_settings_button)

            view_settings_widget = QWidget()
            view_settings_layout = QVBoxLayout(view_settings_widget)
            view_settings_widget.setVisible(False)
            view_settings_widget.setObjectName(f"view_settings_widget_{i}")

            # Slice row: label + dynamic count
            slice_header = QHBoxLayout()
            slice_header.addWidget(QLabel("Slice:"))
            slice_count = QLabel("— / —")
            slice_count.setObjectName(f"slice_count_label_{i}")
            slice_count.setStyleSheet("font-weight: bold;")
            slice_header.addWidget(slice_count)
            slice_header.addStretch()
            view_settings_layout.addLayout(slice_header)
            view_settings_layout.addWidget(self.sliders[i])

            zoom_in_button = QPushButton("Zoom In")
            zoom_in_button.clicked.connect(
                lambda checked, idx=i: self.zoom_image(idx, 1.1, None)
            )
            view_settings_layout.addWidget(zoom_in_button)

            zoom_out_button = QPushButton("Zoom Out")
            zoom_out_button.clicked.connect(
                lambda checked, idx=i: self.zoom_image(idx, 0.9, None)
            )
            view_settings_layout.addWidget(zoom_out_button)

            brightness_slider = QSlider(Qt.Horizontal)
            brightness_slider.setRange(-100, 100)
            brightness_slider.setValue(0)
            brightness_slider.valueChanged.connect(
                lambda value, idx=i: self.update_brightness_contrast(idx)
            )
            brightness_slider.setObjectName(f"brightness_slider_{i}")
            view_settings_layout.addWidget(QLabel("Brightness:"))
            view_settings_layout.addWidget(brightness_slider)

            contrast_slider = QSlider(Qt.Horizontal)
            contrast_slider.setRange(1, 300)
            contrast_slider.setValue(100)
            contrast_slider.valueChanged.connect(
                lambda value, idx=i: self.update_brightness_contrast(idx)
            )
            contrast_slider.setObjectName(f"contrast_slider_{i}")
            view_settings_layout.addWidget(QLabel("Contrast:"))
            view_settings_layout.addWidget(contrast_slider)

            rotate_layout = QHBoxLayout()
            rotate_label  = QLabel("Rotate:")
            rotate_layout.addWidget(rotate_label)
            rotate_spinbox = QSpinBox()
            rotate_spinbox.setRange(-180, 180)
            rotate_spinbox.setValue(180 if i > 0 else 0)
            rotate_spinbox.valueChanged.connect(
                lambda value, idx=i: self.rotate_image(idx, value)
            )
            rotate_spinbox.setObjectName(f"rotate_spinbox_{i}")
            rotate_layout.addWidget(rotate_spinbox)
            view_settings_layout.addLayout(rotate_layout)

            reset_button = QPushButton(f"Reset {view_name} View")
            reset_button.clicked.connect(
                lambda checked, idx=i: self.reset_view(idx)
            )
            view_settings_layout.addWidget(reset_button)

            settings_layout.addWidget(view_settings_widget)

        settings_layout.addWidget(self.notification_label)
        settings_layout.addStretch()

        # -- segmentation page --
        self.segmentation_page = QWidget()
        seg_layout = QVBoxLayout(self.segmentation_page)
        seg_layout.setContentsMargins(4, 2, 4, 2)
        seg_layout.setSpacing(2)

        # AI landmark navigation section (added by LandmarkNavMixin)
        self.create_landmark_sidebar_section(seg_layout)
        seg_layout.addStretch(10)


        # -- lab page (3D Lab controls) --
        self.lab_page = QWidget()
        lab_page_layout = QVBoxLayout(self.lab_page)
        lab_page_layout.setContentsMargins(0, 0, 0, 0)
        lab_page_layout.setSpacing(0)
        self._build_lab_sidebar_page(lab_page_layout)

        # -- stack pages --
        content_layout.addWidget(self.settings_page)
        content_layout.addWidget(self.segmentation_page)
        content_layout.addWidget(self.lab_page)
        self.segmentation_page.setVisible(False)
        self.lab_page.setVisible(False)

        main_layout.addWidget(content_area)

        # -- connect toggle buttons --
        self.settings_btn.clicked.connect(self.show_settings_page)
        self.ai_seg_btn.clicked.connect(self.show_segmentation_page)
        self.lab_btn.clicked.connect(self._enter_lab_mode)

        scroll_area.setWidget(main_widget)
        sidebar.setWidget(scroll_area)
        self.addDockWidget(Qt.LeftDockWidgetArea, sidebar)

    def toggle_view_settings(self, index):
        w = self.findChild(QWidget, f"view_settings_widget_{index}")
        if w:
            w.setVisible(not w.isVisible())

    def reset_view(self, index):
        from PyQt5.QtWidgets import QSlider, QSpinBox
        self.image_labels[index].zoom_factor = 1.0
        self.brightness[index] = 0
        self.contrast[index]   = 1

        brightness_slider = self.findChild(QSlider, f"brightness_slider_{index}")
        contrast_slider   = self.findChild(QSlider, f"contrast_slider_{index}")
        if brightness_slider and contrast_slider:
            brightness_slider.setValue(0)
            contrast_slider.setValue(100)

        self.h_offset[index] = 0
        self.v_offset[index] = 0

        self.rotation_angles[index] = 0
        rotate_spinbox = self.findChild(QSpinBox, f"rotate_spinbox_{index}")
        if rotate_spinbox:
            rotate_spinbox.setValue(0)

        if self.segmentation_mask is not None:
            if index == 0:
                self.segmentation_mask[self.current_slice[0], :, :] = 0
            elif index == 1:
                self.segmentation_mask[:, :, self.current_slice[1]] = 0
            else:
                self.segmentation_mask[:, self.current_slice[2], :] = 0

        if hasattr(self, "caliper_lines"):
            self.caliper_lines[index] = None

        self.update_image_slice(index)

    # -------------------------------------------------------- file I/O helpers
    def save_image(self):
        if self.image_array is not None:
            file_name, _ = QFileDialog.getSaveFileName(
                self, "Save Image", "", "Image Files (*.nii *.nii.gz)"
            )
            if file_name:
                sitk.WriteImage(sitk.GetImageFromArray(self.image_array), file_name)
                self.notification_label.setText("Image saved successfully.")
                self.current_nifti_path = file_name
        else:
            self.notification_label.setText("No image to save.")
            self.notification_label.setStyleSheet("color: red; font-size: 14px;")

    def save_nifti(self):
        if self.image_array is not None:
            file_name, _ = QFileDialog.getSaveFileName(
                self, "Save NIfTI Image", "", "NIfTI Files (*.nii.gz)"
            )
            if file_name:
                try:
                    nifti_img = nib.Nifti1Image(self.image_array, np.eye(4))
                    nib.save(nifti_img, file_name)
                    self.notification_label.setText(f"NIfTI file saved: {file_name}")
                    self.notification_label.setStyleSheet("color: green; font-size: 14px;")
                    self.current_nifti_path = file_name
                except Exception as e:
                    self.notification_label.setText(f"Error saving NIfTI: {str(e)}")
                    self.notification_label.setStyleSheet("color: red; font-size: 14px;")
        else:
            self.notification_label.setText("No image to save.")
            self.notification_label.setStyleSheet("color: red; font-size: 14px;")

    def import_dicom(self):
        folder_selected = QFileDialog.getExistingDirectory(
            self, "Select DICOM Folder", ""
        )
        if folder_selected:
            try:
                self.notification_label.setText("Converting DICOM to NIfTI...")
                self.notification_label.setStyleSheet("color: blue; font-size: 14px;")
                QApplication.processEvents()

                reader = sitk.ImageSeriesReader()
                dicom_names = reader.GetGDCMSeriesFileNames(folder_selected)
                reader.SetFileNames(dicom_names)
                image = reader.Execute()

                temp_dir       = tempfile.gettempdir()
                temp_nifti_path = os.path.join(temp_dir, "temp_converted_image.nii.gz")
                sitk.WriteImage(image, temp_nifti_path)

                self.load_nifti(temp_nifti_path)

                self.notification_label.setText("Converted and Loaded successfully.")
                self.notification_label.setStyleSheet("color: green; font-size: 14px;")
            except Exception as e:
                self.notification_label.setText(f"Error importing DICOM: {str(e)}")
                self.notification_label.setStyleSheet("color: red; font-size: 14px;")



    def show_help(self):
        from dialogs import show_help
        show_help(self)

    def open_3d_lab(self):
        """Open the standalone '3D Lab' window: a big 3D view with tools to
        crop, clip, and peel away organ/tissue layers to see inside the
        volume. Hands off the data already loaded in this window — does
        not load anything new."""
        if self.image_array is None:
            self.notification_label.setText("Load an image before opening the 3D Lab.")
            self.notification_label.setStyleSheet("color: red; font-size: 14px;")
            return

        from volume_explorer import VolumeExplorerWindow

        # Reuse a single instance across opens rather than piling up windows.
        if getattr(self, "_volume_explorer", None) is not None:
            try:
                self._volume_explorer.close()
            except Exception:
                pass
            self._volume_explorer = None

        has_mask = self.segmentation_mask is not None and np.any(self.segmentation_mask)
        self._volume_explorer = VolumeExplorerWindow(
            image_array=self.image_array,
            spacing=self.spacing,
            segmentation_mask=self.segmentation_mask if has_mask else None,
            label_colormap=self.label_colormap if (has_mask and self.label_colormap) else None,
            parent=self,
        )

        # If organs were detected via AI Segmentation, give the 3D Lab their
        # real display names instead of generic "Region N" labels. We rebuild
        # the label->name mapping the same way LandmarkDetector assigned
        # label values (insertion order over the organ_map it was given),
        # using the centroid lookup already cached in landmark_positions.
        if self.label_colormap and self.landmark_positions:
            # No direct reverse-lookup (label_val -> name) is stored on the
            # viewer, so we rebuild it the same way LandmarkDetector assigned
            # label values originally: insertion order over landmark_positions
            # corresponds to label_idx + 1.
            names_by_label = {}
            names = list(self.landmark_positions.keys())
            for i, name in enumerate(names):
                label_val = i + 1
                if label_val in self.label_colormap:
                    names_by_label[label_val] = name
            self._volume_explorer.set_organ_names(names_by_label)

        self._volume_explorer.show()
        self._volume_explorer.raise_()
        self._volume_explorer.activateWindow()


    def get_active_view_index(self):
        """Returns the index of the active view. Placeholder – always returns 0."""
        return 0
