"""
segmentation.py
---------------
Mixin that handles brush/eraser drawing onto the segmentation mask.
"""

import cv2
import numpy as np
from PyQt5.QtGui import QPainter, QPen, QColor
from PyQt5.QtCore import Qt


class SegmentationMixin:
    def snap_to_boundary(self, slice_img, x, y, radius=8, sigma=3.0):
        height, width = slice_img.shape[:2]
        
        # Local window boundaries
        x_min = max(0, x - radius)
        x_max = min(width - 1, x + radius)
        y_min = max(0, y - radius)
        y_max = min(height - 1, y + radius)
        
        local_window = slice_img[y_min:y_max+1, x_min:x_max+1]
        if local_window.size == 0:
            return x, y
            
        # Normalize local window intensities to compute robust gradients
        window_f = local_window.astype(np.float64)
        win_min, win_max = window_f.min(), window_f.max()
        if win_max > win_min:
            window_norm = (window_f - win_min) / (win_max - win_min) * 255.0
        else:
            window_norm = np.zeros_like(window_f)
            
        # Compute Sobel gradients
        grad_x = cv2.Sobel(window_norm, cv2.CV_64F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(window_norm, cv2.CV_64F, 0, 1, ksize=3)
        grad_mag = np.sqrt(grad_x**2 + grad_y**2)
        
        best_x, best_y = x, y
        max_score = -1.0
        
        # Select the pixel that maximizes the gradient-proximity score
        for row in range(grad_mag.shape[0]):
            for col in range(grad_mag.shape[1]):
                img_x = x_min + col
                img_y = y_min + row
                
                # Gaussian proximity weight
                dist_sq = (img_x - x)**2 + (img_y - y)**2
                proximity = np.exp(-dist_sq / (2.0 * sigma**2))
                
                # Combine gradient magnitude and proximity
                score = (grad_mag[row, col] + 1e-5) * proximity
                
                if score > max_score:
                    max_score = score
                    best_x, best_y = img_x, img_y
                    
        return best_x, best_y

    def _draw_snapped_line(self, mask, slice_img, x1, y1, x2, y2, val, thickness):
        dist = np.hypot(x2 - x1, y2 - y1)
        if dist > 2:
            num_steps = int(np.ceil(dist / 2.0))
            pts = []
            for step in range(num_steps + 1):
                t = step / float(num_steps)
                px = int(round((1 - t) * x1 + t * x2))
                py = int(round((1 - t) * y1 + t * y2))
                psx, psy = self.snap_to_boundary(slice_img, px, py)
                pts.append((psx, psy))
            
            for i in range(len(pts) - 1):
                cv2.line(mask, pts[i], pts[i+1], val, thickness)
        else:
            x1_s, y1_s = self.snap_to_boundary(slice_img, x1, y1)
            x2_s, y2_s = self.snap_to_boundary(slice_img, x2, y2)
            cv2.line(mask, (x1_s, y1_s), (x2_s, y2_s), val, thickness)

    def continue_drawing(self, label, start, end):
        if self.current_tool == "Move":
            return

        if not self.is_abdomen:
            self.notification_label.setText("Segmentation only works on abdominal CT scans.")
            self.notification_label.setStyleSheet("color: red; font-size: 14px;")
            return

        index = self.image_labels.index(label)
        
        start_coords = self.get_raw_pixel_from_pos(index, start)
        end_coords = self.get_raw_pixel_from_pos(index, end)
        
        if not start_coords or not end_coords or self.segmentation_mask is None:
            return

        x1, y1 = start_coords
        x2, y2 = end_coords

        val = 1 if self.current_tool in ["Brush", "Smart Brush"] else 0
        thickness = self.brush_thickness if self.current_tool in ["Brush", "Smart Brush"] else self.eraser_thickness

        if index == 0:  # Axial
            mask = self.segmentation_mask[self.current_slice[0]]
            if self.current_tool == "Smart Brush":
                slice_img = self.image_array[self.current_slice[0], :, :]
                self._draw_snapped_line(mask, slice_img, x1, y1, x2, y2, val, thickness)
            else:
                cv2.line(mask, (x1, y1), (x2, y2), val, thickness)

        elif index == 1:  # Sagittal
            temp = self.segmentation_mask[:, :, self.current_slice[1]].copy()
            if self.current_tool == "Smart Brush":
                slice_img = self.image_array[:, :, self.current_slice[1]]
                self._draw_snapped_line(temp, slice_img, x1, y1, x2, y2, val, thickness)
            else:
                cv2.line(temp, (x1, y1), (x2, y2), val, thickness)
            self.segmentation_mask[:, :, self.current_slice[1]] = temp

        else:  # Coronal
            temp = self.segmentation_mask[:, self.current_slice[2], :].copy()
            if self.current_tool == "Smart Brush":
                slice_img = self.image_array[:, self.current_slice[2], :]
                self._draw_snapped_line(temp, slice_img, x1, y1, x2, y2, val, thickness)
            else:
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
