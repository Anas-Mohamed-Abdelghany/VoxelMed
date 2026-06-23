"""
landmark_nav.py
---------------
LandmarkNavMixin

Mixed into ImageViewer alongside the existing mixins. Adds:

  - run_landmark_detection()    : starts the background LandmarkDetector
                                   thread after a scan loads.
  - navigate_to_landmark(name)  : jumps all 3 views + crosshairs to the
                                   centroid of the named organ, flashes a
                                   highlight ring for 2 seconds.
  - draw_landmark_highlight()   : called from update_image_slice() to draw
                                   the ring overlay.
  - sidebar building helpers    : creates the "AI Landmarks" panel inside
                                   the existing scrollable left sidebar.

This file does not modify any existing tool, drawing, or caliper behavior.
It only adds new state (landmark_positions / active_landmark /
_landmark_highlight) and new sidebar widgets.
"""

import cv2
import numpy as np

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (
    QPushButton, QLabel, QFrame, QWidget, QVBoxLayout
)


class LandmarkNavMixin:
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_landmark_detection(self):
        """
        Start background TotalSegmentator detection on the currently loaded
        scan. Safe no-op if nothing is loaded or TotalSegmentator is missing
        (the thread reports that via error_occurred).
        """
        if self.image_array is None or not self.current_nifti_path:
            return

        self.landmark_positions  = {}
        self.active_landmark     = None
        self._landmark_highlight = False

        self._set_landmark_status("Running AI detection...\n(3-10 min first time)",
                                   "#aaaaff")
        self._clear_landmark_buttons()

        from landmark_detector import LandmarkDetector
        self._landmark_thread = LandmarkDetector(
            nifti_path  = self.current_nifti_path,
            image_array = self.image_array,
            parent      = self,
        )
        self._landmark_thread.landmarks_ready.connect(self._on_landmarks_ready)
        self._landmark_thread.progress_update.connect(self._on_landmark_progress)
        self._landmark_thread.error_occurred.connect(self._on_landmark_error)
        self._landmark_thread.start()

    # ------------------------------------------------------------------

    def navigate_to_landmark(self, name: str):
        """Jump all 3 views + crosshairs to the centroid of *name*."""
        if name not in self.landmark_positions:
            return

        z, y, x = self.landmark_positions[name]

        # Drive sliders the same way update_crosshairs() does:
        # sliders[0]=Axial->VolZ, sliders[1]=Sagittal->VolX, sliders[2]=Coronal->VolY
        for i, val in enumerate([z, x, y]):
            self.sliders[i].blockSignals(True)
            self.sliders[i].setValue(val)
            self.current_slice[i] = val
            self.sliders[i].blockSignals(False)

        # Match the exact crosshair_positions convention used elsewhere
        # in image_processing.py (update_crosshairs):
        #   Axial    expects (VolX, VolY)
        #   Sagittal expects (VolY, VolZ)
        #   Coronal  expects (VolX, VolZ)
        self.crosshair_positions = [
            (x, y),
            (y, z),
            (x, z),
        ]

        self.active_landmark     = name
        self._landmark_highlight = True

        for i in range(3):
            self.update_image_slice(i)

        QTimer.singleShot(2000, self._clear_landmark_highlight)

        self.notification_label.setText(f"Navigated to: {name}")
        self.notification_label.setStyleSheet("color: #00aaff; font-size: 14px;")

    # ------------------------------------------------------------------
    # Overlay — called from image_processing.update_image_slice()
    # ------------------------------------------------------------------

    def draw_landmark_highlight(self, color_img: np.ndarray, index: int):
        """Draws a highlight ring around the active landmark centroid."""
        if not getattr(self, "_landmark_highlight", False):
            return
        if not getattr(self, "active_landmark", None):
            return
        if self.active_landmark not in self.landmark_positions:
            return

        z, y, x = self.landmark_positions[self.active_landmark]
        h_img, w_img = color_img.shape[:2]

        if index == 0:      # Axial    -> (VolX, VolY)
            px, py = x, y
        elif index == 1:    # Sagittal -> (VolY, VolZ)
            px, py = y, z
        else:               # Coronal  -> (VolX, VolZ)
            px, py = x, z

        px = int(np.clip(px, 0, w_img - 1))
        py = int(np.clip(py, 0, h_img - 1))

        cv2.circle(color_img, (px, py), 18, (0, 0, 0),     3)
        cv2.circle(color_img, (px, py), 18, (0, 200, 255), 2)
        cv2.circle(color_img, (px, py),  4, (0, 200, 255), -1)

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_landmarks_ready(self, landmarks: dict):
        self.landmark_positions = landmarks
        self._populate_landmark_buttons(landmarks)

        count = len(landmarks)
        if count:
            self._set_landmark_status(f"Found {count} landmarks. Click to navigate.",
                                       "#00cc88")
        else:
            self._set_landmark_status("No landmarks found.\nIs this an abdominal CT?",
                                       "#ff6666")

    def _on_landmark_progress(self, message: str):
        self._set_landmark_status(message, "#aaaaaa")

    def _on_landmark_error(self, message: str):
        self._set_landmark_status(message, "#ff6666")
        self.notification_label.setText("Landmark detection failed - see sidebar.")
        self.notification_label.setStyleSheet("color: red; font-size: 14px;")

    def _clear_landmark_highlight(self):
        self._landmark_highlight = False
        for i in range(3):
            self.update_image_slice(i)

    # ------------------------------------------------------------------
    # Sidebar construction — called once from create_left_sidebar()
    # ------------------------------------------------------------------

    def create_landmark_sidebar_section(self, sidebar_layout):
        """
        Builds the 'AI Landmark Navigation' block and appends it to the
        sidebar_layout passed in from ui.py's create_left_sidebar(),
        following the same QFrame/QLabel style conventions already used
        for the per-view settings sections.
        """
        hline = QFrame()
        hline.setFrameShape(QFrame.HLine)
        hline.setFrameShadow(QFrame.Sunken)
        sidebar_layout.addWidget(hline)

        title = QLabel("AI Landmark Navigation")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00ccff;")
        sidebar_layout.addWidget(title)

        subtitle = QLabel("Load an abdominal CT.\nDetection starts automatically.")
        subtitle.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        subtitle.setWordWrap(True)
        sidebar_layout.addWidget(subtitle)

        status_label = QLabel("")
        status_label.setObjectName("landmark_status_label")
        status_label.setWordWrap(True)
        status_label.setStyleSheet("color: #aaaaff; font-size: 11px;")
        sidebar_layout.addWidget(status_label)

        buttons_container = QWidget()
        buttons_container.setObjectName("landmark_buttons_container")
        btn_layout = QVBoxLayout(buttons_container)
        btn_layout.setSpacing(4)
        btn_layout.setContentsMargins(0, 4, 0, 0)
        sidebar_layout.addWidget(buttons_container)

    def _get_landmark_status_label(self):
        return self.findChild(QLabel, "landmark_status_label")

    def _get_landmark_buttons_container(self):
        return self.findChild(QWidget, "landmark_buttons_container")

    def _set_landmark_status(self, text: str, color_hex: str):
        lbl = self._get_landmark_status_label()
        if lbl:
            lbl.setText(text)
            lbl.setStyleSheet(f"color: {color_hex}; font-size: 11px;")

    def _clear_landmark_buttons(self):
        container = self._get_landmark_buttons_container()
        if container is None:
            return
        layout = container.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _populate_landmark_buttons(self, landmarks: dict):
        container = self._get_landmark_buttons_container()
        if container is None:
            return
        layout = container.layout()
        if layout is None:
            layout = QVBoxLayout(container)
            container.setLayout(layout)

        self._clear_landmark_buttons()

        for name, (z, y, x) in sorted(landmarks.items()):
            btn = QPushButton(f"\u2192  {name}   (sl. {z})")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1a3a4a;
                    color: #00ccff;
                    border: 1px solid #005577;
                    border-radius: 4px;
                    padding: 5px 8px;
                    text-align: left;
                    font-size: 12px;
                }
                QPushButton:hover  { background-color: #005577; color: white; }
                QPushButton:pressed{ background-color: #007799; }
            """)
            btn.clicked.connect(lambda checked, n=name: self.navigate_to_landmark(n))
            layout.addWidget(btn)