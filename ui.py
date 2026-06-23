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
    QScrollArea,
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

    # -------------------------------------------------------------- sidebar
    def create_left_sidebar(self):
        sidebar = QDockWidget("Settings", self)
        sidebar.setFeatures(QDockWidget.NoDockWidgetFeatures)
        
        # Stop sidebar from changing width (increased slightly for scrollbar)
        sidebar.setFixedWidth(265)
        
        # Add scroll area so we can scroll down
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # Vertical line to separate sidebar
        scroll_area.setStyleSheet("QScrollArea { border: none; border-right: 2px solid #555555; }")

        sidebar_widget = QWidget()
        sidebar_layout = QVBoxLayout(sidebar_widget)

        # Tool selection
        sidebar_layout.addWidget(QLabel("Tool:"))
        sidebar_layout.addWidget(self.segmentation_tools)

        # Color selection
        color_button = QPushButton("Select Color")
        color_button.clicked.connect(self.select_color)
        sidebar_layout.addWidget(color_button)

        # Brush size
        sidebar_layout.addWidget(QLabel("Brush Size:"))
        brush_size_slider = QSlider(Qt.Horizontal)
        brush_size_slider.setRange(1, 20)
        brush_size_slider.setValue(self.brush_thickness)
        brush_size_slider.valueChanged.connect(self.update_brush_size)
        sidebar_layout.addWidget(brush_size_slider)

        # Eraser size
        sidebar_layout.addWidget(QLabel("Eraser Size:"))
        eraser_size_slider = QSlider(Qt.Horizontal)
        eraser_size_slider.setRange(1, 20)
        eraser_size_slider.setValue(self.eraser_thickness)
        eraser_size_slider.valueChanged.connect(self.update_eraser_size)
        sidebar_layout.addWidget(eraser_size_slider)

        # Separator
        hline = QFrame()
        hline.setFrameShape(QFrame.HLine)
        hline.setFrameShadow(QFrame.Sunken)
        sidebar_layout.addWidget(hline)

        # Per-view settings
        for i, view_name in enumerate(["Axial", "Sagittal", "Coronal"]):
            view_settings_button = QPushButton(f"{view_name} Settings")
            view_settings_button.clicked.connect(
                lambda checked, idx=i: self.toggle_view_settings(idx)
            )
            sidebar_layout.addWidget(view_settings_button)

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

            sidebar_layout.addWidget(view_settings_widget)

        # AI landmark navigation section (added by LandmarkNavMixin)
        self.create_landmark_sidebar_section(sidebar_layout)

        sidebar_layout.addWidget(self.notification_label)
        sidebar_layout.addStretch()
        
        scroll_area.setWidget(sidebar_widget)
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

    def get_active_view_index(self):
        """Returns the index of the active view. Placeholder – always returns 0."""
        return 0
