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
    QLabel, QComboBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
import vtkmodules.all as vtk

from image_label      import ImageLabel
from image_processing import ImageProcessingMixin
from segmentation     import SegmentationMixin
from vtk_renderer     import VTKRendererMixin
from ui               import UIBuilderMixin


class ImageViewer(
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
        self.layout = QGridLayout(self.main_widget)
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
        self.vtk_widget = QVTKRenderWindowInteractor(self.main_widget)
        self.layout.addWidget(self.vtk_widget, 1, 1)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(1, 1, 1)
        self.vtk_widget.GetRenderWindow().AddRenderer(self.renderer)
        self.interactor = self.vtk_widget.GetRenderWindow().GetInteractor()

        self.layout.setColumnStretch(0, 1)
        self.layout.setColumnStretch(1, 1)


        # Segmentation
        self.segmentation_mask = None
        self.drawing_color     = (255, 0, 0)  # Red
        self.brush_thickness   = 2
        self.eraser_thickness  = 2

        self.interactor.Initialize()
        self.interactor.Start()

        # Image state
        self.image_array      = None
        self.current_nifti_path = None

        # Crosshairs
        self.crosshair_positions = [(0, 0), (0, 0), (0, 0)]

        # Per-view brightness / contrast / offsets / rotation
        self.brightness      = [0, 0, 0]
        self.contrast        = [1, 1, 1]
        self.h_offset        = [0, 0, 0]
        self.v_offset        = [0, 0, 0]
        self.rotation_angles = [0, 180, 180]

        # Tool selector (also used by SegmentationMixin)
        self.segmentation_tools = QComboBox()
        self.segmentation_tools.addItems(["Move", "Brush", "Eraser", "Select"])
        self.segmentation_tools.currentTextChanged.connect(self.update_current_tool)
        self.current_tool = "Move"

        # Build the left sidebar (must come after segmentation_tools is ready)
        self.create_left_sidebar()
