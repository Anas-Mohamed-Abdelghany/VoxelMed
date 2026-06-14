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

                self.update_image_slices()
                self.render_3d_volume()
                self.current_nifti_path = file_name
            else:
                self.segmentation_mask = None
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
                self.update_image_slices()
                self.render_3d_volume()
                self.current_nifti_path = nifti_path
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
