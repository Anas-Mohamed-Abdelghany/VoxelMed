"""
image_label.py
--------------
Custom QLabel subclass that handles mouse interaction for each image view panel
(pan, draw, zoom, selection rectangle).
"""

from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor


class ImageLabel(QLabel):
    def __init__(self, viewer, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.viewer = viewer
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.last_point = None
        self.is_drawing = False
        self.zoom_factor = 1.0
        self.pan_start = None
        self.zoom_mode = False
        self.zoom_center = None
        self.is_panning = False
        self.rotation_angle = 0  # stores the rotation angle for this view
        self.crosshair_locked = False  # right-click toggles this
        self.right_press_pos = None

    def mousePressEvent(self, event):
        if self.viewer.current_tool == "Move" and event.button() == Qt.LeftButton:
            self.setCursor(QCursor(Qt.ClosedHandCursor))
            self.is_panning = True
            self.pan_start = event.pos()
        elif self.viewer.current_tool == "Smart Caliper" and event.button() == Qt.LeftButton:
            self.last_point = event.pos()
            if self.viewer.image_array is not None:
                self.viewer.apply_smart_caliper(self, event.pos())
        elif event.button() == Qt.LeftButton and self.viewer.current_tool not in ["Move", "Smart Caliper"]:
            self.last_point = event.pos()
            self.is_drawing = True
            if self.viewer.image_array is not None:
                self.viewer.continue_drawing(self, event.pos(), event.pos())
                self.viewer.update_crosshairs(self.viewer.image_labels.index(self), event.pos())
        elif event.button() == Qt.RightButton:
            self.last_point = event.pos()
            self.right_press_pos = event.pos()
        elif event.button() == Qt.MiddleButton:
            self.pan_start = event.pos()
        elif self.zoom_mode:
            self.zoom_center = event.pos()
            if event.button() == Qt.LeftButton:
                self.viewer.zoom_image(self.viewer.image_labels.index(self), 1.1, self.zoom_center)
            elif event.button() == Qt.RightButton:
                self.viewer.zoom_image(self.viewer.image_labels.index(self), 0.9, self.zoom_center)

    def mouseMoveEvent(self, event):
        if self.viewer.current_tool == "Move" and self.is_panning:
            dx = event.x() - self.pan_start.x()
            dy = event.y() - self.pan_start.y()
            self.viewer.pan_image(self.viewer.image_labels.index(self), dx, dy)
            self.pan_start = event.pos()
        elif self.is_drawing and self.viewer.current_tool not in ["Move"]:
            self.viewer.continue_drawing(self, self.last_point, event.pos())
            self.last_point = event.pos()
            if self.viewer.image_array is not None:
                self.viewer.update_crosshairs(self.viewer.image_labels.index(self), event.pos())
        elif event.buttons() & Qt.RightButton:
            dx = event.x() - self.last_point.x()
            dy = event.y() - self.last_point.y()
            self.viewer.adjust_brightness_contrast(self.viewer.image_labels.index(self), dx, dy)
            self.last_point = event.pos()
        else:
            # Update crosshair position (only if not locked)
            if self.viewer.image_array is not None and not self.crosshair_locked:
                self.viewer.update_crosshairs(
                    self.viewer.image_labels.index(self), event.pos()
                )

    def mouseReleaseEvent(self, event):
        if self.viewer.current_tool == "Move" and event.button() == Qt.LeftButton:
            self.setCursor(QCursor(Qt.ArrowCursor))
            self.is_panning = False
        elif event.button() == Qt.LeftButton:
            self.is_drawing = False
            self.viewer.end_drawing()
        elif event.button() == Qt.RightButton:
            # If mouse barely moved, it's a click → toggle crosshair lock
            if self.right_press_pos is not None:
                delta = (event.pos() - self.right_press_pos).manhattanLength()
                if delta < 5:
                    self.crosshair_locked = not self.crosshair_locked
            self.right_press_pos = None
        elif event.button() == Qt.MiddleButton:
            self.pan_start = None

    def paintEvent(self, event):
        super().paintEvent(event)
