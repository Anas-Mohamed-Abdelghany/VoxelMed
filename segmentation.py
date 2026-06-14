"""
segmentation.py
---------------
Mixin that handles brush/eraser drawing onto the segmentation mask.
"""

import cv2
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtCore import Qt


class SegmentationMixin:
    def continue_drawing(self, label, start, end):
        if self.current_tool == "Move":
            return

        index = self.image_labels.index(label)
        
        start_coords = self.get_raw_pixel_from_pos(index, start)
        end_coords = self.get_raw_pixel_from_pos(index, end)
        
        if not start_coords or not end_coords or self.segmentation_mask is None:
            return

        x1, y1 = start_coords
        x2, y2 = end_coords

        if index == 0:  # Axial
            mask = self.segmentation_mask[self.current_slice[0]]
            val  = 1 if self.current_tool == "Brush" else 0
            thickness = self.brush_thickness if self.current_tool == "Brush" else self.eraser_thickness
            cv2.line(mask, (x1, y1), (x2, y2), val, thickness)

        elif index == 1:  # Sagittal
            temp = self.segmentation_mask[:, :, self.current_slice[1]].copy()
            val  = 1 if self.current_tool == "Brush" else 0
            thickness = self.brush_thickness if self.current_tool == "Brush" else self.eraser_thickness
            cv2.line(temp, (x1, y1), (x2, y2), val, thickness)
            self.segmentation_mask[:, :, self.current_slice[1]] = temp

        else:  # Coronal
            temp = self.segmentation_mask[:, self.current_slice[2], :].copy()
            val  = 1 if self.current_tool == "Brush" else 0
            thickness = self.brush_thickness if self.current_tool == "Brush" else self.eraser_thickness
            cv2.line(temp, (x1, y1), (x2, y2), val, thickness)
            self.segmentation_mask[:, self.current_slice[2], :] = temp
        # Redraw all 3 views so the drawing is visible in orthogonal views too
        for i in range(3):
            self.update_image_slice(i)

    def end_drawing(self):
        """Redraw all views when drawing finishes to ensure final state is visible."""
        for i in range(3):
            self.update_image_slice(i)

    def select_color(self):
        from PyQt5.QtWidgets import QColorDialog
        color = QColorDialog.getColor()
        if color.isValid():
            self.drawing_color = (color.red(), color.green(), color.blue())

    def update_brush_size(self, value):
        self.brush_thickness = value

    def update_eraser_size(self, value):
        self.eraser_thickness = value

    def update_current_tool(self, tool):
        self.current_tool = tool
