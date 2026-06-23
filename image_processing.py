"""
image_processing.py
--------------------
Methods responsible for loading, normalising, and displaying image slices
as well as crosshair drawing and brightness/contrast adjustment.

These are designed to be mixed into ImageViewer (used as a mixin class).
"""

import numpy as np
import cv2
import SimpleITK as sitk
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt


class ImageProcessingMixin:
    # ------------------------------------------------------------------ load
    def load_image(self):
        from PyQt5.QtWidgets import QFileDialog
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "", "Image Files (*.nii *.nii.gz)"
        )
        if file_name:
            image = sitk.ReadImage(file_name)
            self.image_array = sitk.GetArrayFromImage(image)

            if self.image_array is not None and self.image_array.size > 0:
                for i in range(3):
                    self.image_labels[i].clear()

                self.notification_label.setText("Image loaded successfully.")
                self.segmentation_mask = np.zeros_like(self.image_array, dtype=np.uint8)
                self.spacing = image.GetSpacing()
                self.caliper_lines = [None, None, None]

                self.update_image_slices()
                self.render_3d_volume()
                self.current_nifti_path = file_name
                self.run_landmark_detection()
            else:
                self.segmentation_mask = None
                self.spacing = (1.0, 1.0, 1.0)
                self.caliper_lines = [None, None, None]
                self.notification_label.setText(
                    "Error: Image data is invalid or could not be loaded."
                )
                print("Error: Image data is invalid or could not be loaded.")

    def load_nifti(self, nifti_path):
        try:
            image = sitk.ReadImage(nifti_path)
            self.image_array = sitk.GetArrayFromImage(image)

            if self.image_array is not None and self.image_array.size > 0:
                for i in range(3):
                    self.image_labels[i].clear()

                self.segmentation_mask = np.zeros_like(self.image_array, dtype=np.uint8)
                self.spacing = image.GetSpacing()
                self.caliper_lines = [None, None, None]
                self.update_image_slices()
                self.render_3d_volume()
                self.current_nifti_path = nifti_path
                self.run_landmark_detection()
            else:
                self.segmentation_mask = None
                self.notification_label.setText(
                    "Error: Image data is invalid or could not be loaded."
                )
                self.notification_label.setStyleSheet("color: red; font-size: 14px;")
                print("Error: Image data is invalid or could not be loaded.")
        except Exception as e:
            self.notification_label.setText(f"Error loading NIfTI: {str(e)}")
            self.notification_label.setStyleSheet("color: red; font-size: 14px;")

    # --------------------------------------------------------- slice display
    def update_image_slices(self):
        depth, height, width = self.image_array.shape

        for i in range(3):
            if i == 0:      # Axial
                self.sliders[i].setMaximum(depth - 1)
                mid_slice = depth // 2
            elif i == 1:    # Sagittal
                self.sliders[i].setMaximum(width - 1)
                mid_slice = width // 2
            else:           # Coronal
                self.sliders[i].setMaximum(height - 1)
                mid_slice = height // 2

            self.sliders[i].setValue(mid_slice)
            self.current_slice[i] = mid_slice
            self.update_image_slice(i)

        # Force the layout to recalculate and repaint immediately.
        # Without this, loading a new image while the window is maximised
        # leaves the layout in a stretched/stale state until the user
        # manually resizes the window.
        from PyQt5.QtWidgets import QApplication
        self.layout.activate()
        self.main_widget.updateGeometry()
        QApplication.processEvents()


    def update_image_slice(self, index):
        if self.image_array is None:
            return

        slice_index = self.sliders[index].value()
        self.current_slice[index] = slice_index

        if index == 0:      # Axial
            slice_img  = self.image_array[slice_index, :, :]
            mask_slice = self.segmentation_mask[slice_index, :, :]
        elif index == 1:    # Sagittal
            slice_img  = self.image_array[:, :, slice_index]
            mask_slice = self.segmentation_mask[:, :, slice_index]
        else:               # Coronal
            slice_img  = self.image_array[:, slice_index, :]
            mask_slice = self.segmentation_mask[:, slice_index, :]

        # Apply brightness and contrast
        adjusted_img = cv2.convertScaleAbs(
            slice_img, alpha=self.contrast[index], beta=self.brightness[index]
        )

        # Normalise to 0-255
        min_val, max_val = adjusted_img.min(), adjusted_img.max()
        if max_val == min_val:
            normalized_img = np.zeros_like(adjusted_img, dtype=np.uint8)
        else:
            normalized_img = (
                (adjusted_img - min_val) / (max_val - min_val) * 255
            ).astype(np.uint8)

        # Convert to RGB for overlay
        color_img = cv2.cvtColor(normalized_img, cv2.COLOR_GRAY2RGB)

        # Draw crosshairs first (underneath)
        self.draw_crosshairs(color_img, index)

        # Overlay segmentation mask on top so paint is always visible
        if self.segmentation_mask is not None:
            color_img[mask_slice > 0] = self.drawing_color

        # Overlay active caliper measurement if present
        if hasattr(self, "caliper_lines") and self.caliper_lines[index] is not None:
            self.draw_caliper_overlay(color_img, index)

        # Overlay landmark highlight ring if AI navigation just fired
        if getattr(self, "_landmark_highlight", False):
            self.draw_landmark_highlight(color_img, index)

        height_px, width_px = color_img.shape[:2]

        # Apply rotation
        if self.rotation_angles[index] != 0:
            M = cv2.getRotationMatrix2D(
                (width_px // 2, height_px // 2), self.rotation_angles[index], 1
            )
            color_img = cv2.warpAffine(color_img, M, (width_px, height_px))

        # Apply pan offsets
        M = np.float32(
            [[1, 0, self.h_offset[index]], [0, 1, self.v_offset[index]]]
        )
        color_img = cv2.warpAffine(color_img, M, (width_px, height_px))

        bytes_per_line = 3 * width_px
        q_img = QImage(
            color_img.data, width_px, height_px, bytes_per_line, QImage.Format_RGB888
        )
        pixmap = QPixmap.fromImage(q_img)

        scaled_pixmap = pixmap.scaled(
            int(self.image_size[0] * self.image_labels[index].zoom_factor),
            int(self.image_size[1] * self.image_labels[index].zoom_factor),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image_labels[index].setPixmap(scaled_pixmap)

        # Update the "Slice: current / total" label in the sidebar
        from PyQt5.QtWidgets import QLabel as _QLabel
        count_lbl = self.findChild(_QLabel, f"slice_count_label_{index}")
        if count_lbl:
            total = self.sliders[index].maximum()
            count_lbl.setText(f"{slice_index} / {total}")


    def draw_crosshairs(self, image, index):
        height, width = image.shape[:2]
        color = (0, 255, 0)
        thickness = 1

        # The coordinates are already in raw slice pixels
        x, y = self.crosshair_positions[index]

        x = max(0, min(width - 1, int(x)))
        y = max(0, min(height - 1, int(y)))

        cv2.line(image, (x, 0), (x, height), color, thickness)
        cv2.line(image, (0, y), (width, y), color, thickness)

    def get_raw_pixel_from_pos(self, index, pos):
        if self.image_array is None:
            return None

        label = self.image_labels[index]
        pixmap = label.pixmap()
        if not pixmap:
            return None

        # 1. Get position relative to the drawn image (accounting for centering)
        px_w = pixmap.width()
        px_h = pixmap.height()
        offset_x = (label.width() - px_w) / 2.0
        offset_y = (label.height() - px_h) / 2.0

        mouse_px_x = pos.x() - offset_x
        mouse_px_y = pos.y() - offset_y

        # 2. Map to source image dimensions
        # image_array shape is (D, H, W) -> (VolZ, VolY, VolX)
        if index == 0:  # Axial -> shows VolX (width) and VolY (height)
            width_px, height_px = self.image_array.shape[2], self.image_array.shape[1]
        elif index == 1:  # Sagittal -> shows VolY (width) and VolZ (height)
            width_px, height_px = self.image_array.shape[1], self.image_array.shape[0]
        else:  # Coronal -> shows VolX (width) and VolZ (height)
            width_px, height_px = self.image_array.shape[2], self.image_array.shape[0]

        scale_x = px_w / float(width_px)
        scale_y = px_h / float(height_px)

        img_x = mouse_px_x / scale_x
        img_y = mouse_px_y / scale_y

        # 3. Reverse the pan offsets to get the raw un-panned pixel coordinate
        raw_x = img_x - self.h_offset[index]
        raw_y = img_y - self.v_offset[index]

        # 4. Reverse the rotation
        if self.rotation_angles[index] != 0:
            cx, cy = width_px / 2.0, height_px / 2.0
            angle_rad = np.radians(self.rotation_angles[index])
            alpha = np.cos(angle_rad)
            beta = np.sin(angle_rad)
            
            tx = raw_x - cx
            ty = raw_y - cy
            
            # Apply inverse rotation matrix
            raw_x = alpha * tx - beta * ty + cx
            raw_y = beta * tx + alpha * ty + cy

        x = int(max(0, min(width_px - 1, raw_x)))
        y = int(max(0, min(height_px - 1, raw_y)))
        return (x, y)

    def update_crosshairs(self, index, pos):
        coords = self.get_raw_pixel_from_pos(index, pos)
        if not coords:
            return
        x, y = coords  # These are screen coordinates (col, row) for the clicked view

        # Determine true 3D volume coordinates based on which view was clicked
        if index == 0:  # Axial (displays VolX, VolY)
            VolX = x
            VolY = y
            VolZ = self.current_slice[0]
        elif index == 1:  # Sagittal (displays VolY, VolZ)
            VolY = x
            VolZ = y
            VolX = self.current_slice[1]
        else:  # Coronal (displays VolX, VolZ)
            VolX = x
            VolZ = y
            VolY = self.current_slice[2]

        # Update crosshairs for all 3 views
        self.crosshair_positions = [
            (VolX, VolY),  # Axial expects (VolX, VolY)
            (VolY, VolZ),  # Sagittal expects (VolY, VolZ)
            (VolX, VolZ)   # Coronal expects (VolX, VolZ)
        ]

        # Update the orthogonal slice sliders so the other views follow the crosshair
        for i in range(3):
            self.sliders[i].blockSignals(True)
            if i == 0:
                self.sliders[i].setValue(VolZ)
                self.current_slice[i] = VolZ
            elif i == 1:
                self.sliders[i].setValue(VolX)
                self.current_slice[i] = VolX
            else:
                self.sliders[i].setValue(VolY)
                self.current_slice[i] = VolY
            self.sliders[i].blockSignals(False)

            self.update_image_slice(i)

    # ------------------------------------------------ brightness / contrast
    def update_brightness_contrast(self, index):
        from PyQt5.QtWidgets import QSlider
        brightness_slider = self.findChild(QSlider, f"brightness_slider_{index}")
        contrast_slider   = self.findChild(QSlider, f"contrast_slider_{index}")

        if brightness_slider and contrast_slider:
            self.brightness[index] = brightness_slider.value()
            self.contrast[index]   = contrast_slider.value() / 100.0
            self.update_image_slice(index)

    def adjust_brightness_contrast(self, index, dx, dy):
        """Called by right-drag on the image label."""
        self.brightness[index] = max(-100, min(100, self.brightness[index] + dx))
        self.contrast[index]   = max(0.01, self.contrast[index] + dy * 0.01)
        self.update_image_slice(index)

    # ---------------------------------------------------------- pan / zoom / rotate
    def zoom_image(self, index, factor, center):
        label = self.image_labels[index]
        old_zoom = label.zoom_factor
        new_zoom = max(1.0, old_zoom * factor)   # never zoom out past fit-to-panel
        label.zoom_factor = new_zoom

        if new_zoom == 1.0:
            # Fully zoomed out — reset pan so image fills the panel cleanly
            self.h_offset[index] = 0
            self.v_offset[index] = 0
        elif center:
            dx = int(center.x() * (new_zoom - old_zoom))
            dy = int(center.y() * (new_zoom - old_zoom))
            self.h_offset[index] -= dx
            self.v_offset[index] -= dy
            self._clamp_offsets(index)

        self.update_image_slice(index)

    def pan_image(self, index, dx, dy):
        zoom = self.image_labels[index].zoom_factor
        # Divide by zoom so that 1 screen-pixel drag = 1 screen-pixel movement
        # at any zoom level (without this, pan speed multiplies with zoom).
        self.h_offset[index] += dx / zoom
        self.v_offset[index] += dy / zoom
        self._clamp_offsets(index)
        self.update_image_slice(index)


    def _clamp_offsets(self, index):
        """Keep the image from being panned completely off-screen."""
        zoom = self.image_labels[index].zoom_factor
        # Maximum shift (in source-pixel coords) before the image edge
        # reaches the opposite panel edge.
        max_h = int(self.image_size[0] * (zoom - 1) / zoom)
        max_v = int(self.image_size[1] * (zoom - 1) / zoom)
        self.h_offset[index] = max(-max_h, min(max_h, self.h_offset[index]))
        self.v_offset[index] = max(-max_v, min(max_v, self.v_offset[index]))

    def rotate_image(self, index, angle):
        self.rotation_angles[index] = angle
        self.update_image_slice(index)

    def draw_caliper_overlay(self, image, index):
        if not hasattr(self, "caliper_lines") or self.caliper_lines[index] is None:
            return
            
        p1, p2, diameter = self.caliper_lines[index]
        x1, y1 = p1
        x2, y2 = p2
        
        # Color of caliper: Cyan (0, 255, 255)
        color = (0, 255, 255)
        thickness = 2
        
        # Draw main caliper line
        cv2.line(image, (x1, y1), (x2, y2), color, thickness)
        
        # Calculate perpendicular tick marks
        dx = x2 - x1
        dy = y2 - y1
        length = np.hypot(dx, dy)
        if length > 0:
            ux = dx / length
            uy = dy / length
            
            # Perpendicular vector
            px = -uy
            py = ux
            
            tick_size = 6  # Total tick length is 12 pixels
            
            # Tick at P1
            pt1_a = (int(round(x1 + tick_size * px)), int(round(y1 + tick_size * py)))
            pt1_b = (int(round(x1 - tick_size * px)), int(round(y1 - tick_size * py)))
            cv2.line(image, pt1_a, pt1_b, color, thickness)
            
            # Tick at P2
            pt2_a = (int(round(x2 + tick_size * px)), int(round(y2 + tick_size * py)))
            pt2_b = (int(round(x2 - tick_size * px)), int(round(y2 - tick_size * py)))
            cv2.line(image, pt2_a, pt2_b, color, thickness)
            
            # Draw diameter text next to the line midpoint
            mx = (x1 + x2) // 2
            my = (y1 + y2) // 2
            
            # Format text
            text = f"{diameter:.1f} mm"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.5
            text_thickness = 1
            
            # Get text size for background box
            (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, text_thickness)
            
            # Offset text slightly from the line
            tx = int(round(mx + 8 * px - text_w / 2))
            ty = int(round(my + 8 * py + text_h / 2))
            
            # Clamp to image boundaries
            h, w = image.shape[:2]
            tx = max(2, min(w - text_w - 2, tx))
            ty = max(text_h + 2, min(h - 2, ty))
            
            # Draw small black background box for readability
            cv2.rectangle(image, (tx - 2, ty - text_h - 2), (tx + text_w + 2, ty + 2), (0, 0, 0), -1)
            # Draw text
            cv2.putText(image, text, (tx, ty), font, font_scale, color, text_thickness, cv2.LINE_AA)

    def apply_smart_caliper(self, label, pos):
        index = self.image_labels.index(label)
        coords = self.get_raw_pixel_from_pos(index, pos)
        if not coords or self.image_array is None:
            return
            
        x_c, y_c = coords
        
        # Update the crosshair position to the clicked point
        self.update_crosshairs(index, pos)
        
        # Get active slice image
        slice_index = self.current_slice[index]
        if index == 0:      # Axial
            slice_img  = self.image_array[slice_index, :, :]
            spacing_col = self.spacing[0]
            spacing_row = self.spacing[1]
        elif index == 1:    # Sagittal
            slice_img  = self.image_array[:, :, slice_index]
            spacing_col = self.spacing[1]
            spacing_row = self.spacing[2]
        else:               # Coronal
            slice_img  = self.image_array[:, slice_index, :]
            spacing_col = self.spacing[0]
            spacing_row = self.spacing[2]
            
        height, width = slice_img.shape[:2]
        
        # Local window of size 100x100
        W_size = 100
        x_min = max(0, x_c - W_size // 2)
        x_max = min(width - 1, x_c + W_size // 2)
        y_min = max(0, y_c - W_size // 2)
        y_max = min(height - 1, y_c + W_size // 2)
        
        local_img = slice_img[y_min:y_max+1, x_min:x_max+1]
        if local_img.size == 0:
            return
            
        # Normalize local image to 0-255 uint8
        win_min, win_max = local_img.min(), local_img.max()
        if win_max > win_min:
            local_norm = ((local_img - win_min) / (win_max - win_min) * 255.0).astype(np.uint8)
        else:
            local_norm = np.zeros_like(local_img, dtype=np.uint8)
            
        # Apply Otsu's thresholding
        blurred = cv2.GaussianBlur(local_norm, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Determine the foreground class based on seed pixel
        x_seed_local = x_c - x_min
        y_seed_local = y_c - y_min
        
        # Prevent index error in case seed pixel calculation lies outside boundaries
        y_seed_local = max(0, min(thresh.shape[0] - 1, y_seed_local))
        x_seed_local = max(0, min(thresh.shape[1] - 1, x_seed_local))
        
        if thresh[y_seed_local, x_seed_local] == 0:
            thresh = cv2.bitwise_not(thresh)
            
        # Get connected components
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh)
        seed_label = labels[y_seed_local, x_seed_local]
        
        if seed_label == 0:
            # If seed is in background (e.g. edge cases), do nothing
            return
            
        # Extract the component mask
        component_mask = (labels == seed_label).astype(np.uint8) * 255
        
        # Find contours
        contours, _ = cv2.findContours(component_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            return
            
        # Use the contour
        contour = contours[0]
        pts = []
        for pt in contour:
            gx = x_min + pt[0][0]
            gy = y_min + pt[0][1]
            pts.append((gx, gy))
            
        # Calculate maximum physical/RECIST diameter pairwise
        max_dist = -1.0
        best_p1 = (x_c, y_c)
        best_p2 = (x_c, y_c)
        
        # Optimize search if too many points
        n_pts = len(pts)
        if n_pts > 400:
            step = n_pts // 200
            pts = pts[::step]
            n_pts = len(pts)
            
        for i in range(n_pts):
            for j in range(i + 1, n_pts):
                dx = (pts[i][0] - pts[j][0]) * spacing_col
                dy = (pts[i][1] - pts[j][1]) * spacing_row
                dist = np.hypot(dx, dy)
                if dist > max_dist:
                    max_dist = dist
                    best_p1 = pts[i]
                    best_p2 = pts[j]
                    
        # Update caliper state
        self.caliper_lines[index] = (best_p1, best_p2, max_dist)
        
        # Update views to show the caliper
        self.update_image_slice(index)
        
        # Show a notification text
        self.notification_label.setText(f"Smart-Caliper: {max_dist:.1f} mm")
        self.notification_label.setStyleSheet("color: #00ffff; font-size: 14px; font-weight: bold;")
