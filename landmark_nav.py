"""
landmark_nav.py
---------------
LandmarkNavMixin

Mixed into ImageViewer alongside the existing mixins. Adds:

  - create_landmark_sidebar_section() : builds the "AI Segmentation" panel
    inside the left sidebar, with section buttons, organ checkboxes,
    and a Run Segmentation button.
  - run_landmark_detection(organ_map)  : starts the background LandmarkDetector
    thread for a specific set of organs.
  - navigate_to_landmark(name)        : jumps all 3 views + crosshairs to the
    centroid of the named organ, flashes a highlight ring for 2 seconds.
  - draw_landmark_highlight()         : called from update_image_slice() to
    draw the ring overlay.
"""

import cv2
import numpy as np

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import (
    QPushButton, QLabel, QFrame, QWidget, QVBoxLayout, QHBoxLayout,
    QCheckBox, QGridLayout,
)

from landmark_detector import (
    get_sections,
    get_section_description,
    get_organs_for_section,
    get_all_organs,
    LandmarkDetector,
)


class LandmarkNavMixin:
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_landmark_detection(self, organ_map: dict = None):
        """
        Start background TotalSegmentator for a specific set of organs
        (organ_map: {display_name: stem}). If None, segments all organs.
        Safe no-op if nothing is loaded.
        """
        if self.image_array is None or not self.current_nifti_path:
            return

        self.landmark_positions  = {}
        self.active_landmark     = None
        self._landmark_highlight = False

        count = len(organ_map) if organ_map else 0
        self._run_status_label.setText("Running TotalSegmentator...")
        self._run_status_label.setVisible(True)

        detector = LandmarkDetector(
            nifti_path  = self.current_nifti_path,
            image_array = self.image_array,
            organ_map   = organ_map,
            parent      = self,
        )
        self._landmark_thread = detector
        detector.landmarks_ready.connect(self._on_landmarks_ready)
        detector.masks_ready.connect(self._on_masks_ready)
        detector.progress_update.connect(self._on_landmark_progress)
        detector.error_occurred.connect(self._on_landmark_error)
        detector.start()

    # ------------------------------------------------------------------

    def navigate_to_landmark(self, name: str):
        """Jump all 3 views + crosshairs to the centroid of *name*."""
        if name not in self.landmark_positions:
            return

        z, y, x = self.landmark_positions[name]

        for i, val in enumerate([z, x, y]):
            self.sliders[i].blockSignals(True)
            self.sliders[i].setValue(val)
            self.current_slice[i] = val
            self.sliders[i].blockSignals(False)

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

        if index == 0:
            px, py = x, y
        elif index == 1:
            px, py = y, z
        else:
            px, py = x, z

        px = int(np.clip(px, 0, w_img - 1))
        py = int(np.clip(py, 0, h_img - 1))

        cv2.circle(color_img, (px, py), 18, (0, 0, 0),     3)
        cv2.circle(color_img, (px, py), 18, (0, 200, 255), 2)
        cv2.circle(color_img, (px, py),  4, (0, 200, 255), -1)

    # ------------------------------------------------------------------
    # Reset UI when a new image is loaded
    # ------------------------------------------------------------------

    def _reset_ai_segmentation_ui(self):
        """Reset the AI segmentation panel when a new image is loaded."""
        self.landmark_positions  = {}
        self.active_landmark     = None
        self._landmark_highlight = False
        self._active_section     = None
        self._selected_organs    = set()
        self.label_colormap      = {}

        for sec in get_sections():
            btn = self.findChild(QPushButton, f"section_btn_{sec}")
            if btn and btn.isChecked():
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)

        if hasattr(self, "_detect_btn"):
            self._detect_btn.setVisible(False)
            self._detect_btn.setEnabled(False)
            self._detect_btn.setText("Run Segmentation")

        if hasattr(self, "_run_status_label"):
            self._run_status_label.setVisible(False)
            self._run_status_label.setText("")

        self._set_landmark_status("Select a section above to begin.", "#aaaaaa")
        self._clear_organ_buttons()

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_landmarks_ready(self, landmarks: dict):
        self.landmark_positions = landmarks
        self._populate_organ_results()
        self._run_status_label.setVisible(False)

        count = len(landmarks)
        if count:
            self._set_landmark_status(
                f"Found {count} organ(s). Click to navigate.",
                "#00cc88"
            )
        else:
            self._set_landmark_status(
                "No organs found.",
                "#ff6666"
            )

    def _on_masks_ready(self, combined_mask, label_map, landmarks):
        self.segmentation_mask = combined_mask
        self.label_colormap    = label_map
        # Build label→name mapping from the same iteration order LandmarkDetector used
        self._label_organ_names = {}
        names = list(landmarks.keys())
        for i, label_val in enumerate(sorted(label_map.keys())):
            if i < len(names):
                self._label_organ_names[label_val] = names[i]
        for i in range(3):
            self.update_image_slice(i)

    def _on_landmark_progress(self, message: str):
        self._run_status_label.setText(message)
        self._run_status_label.setVisible(True)

    def _on_landmark_error(self, message: str):
        self._set_landmark_status(message, "#ff6666")
        self._run_status_label.setVisible(False)
        self.notification_label.setText("Landmark detection failed - see sidebar.")
        self.notification_label.setStyleSheet("color: red; font-size: 14px;")
        section = getattr(self, "_active_section", None)
        if section:
            self._detect_btn.setEnabled(True)
            self._detect_btn.setText(f"Run Segmentation — {section}")
            self._detect_btn.setVisible(True)

    def _clear_landmark_highlight(self):
        self._landmark_highlight = False
        for i in range(3):
            self.update_image_slice(i)

    # ------------------------------------------------------------------
    # Sidebar construction
    # ------------------------------------------------------------------

    def create_landmark_sidebar_section(self, sidebar_layout):
        """
        Builds the 'AI Segmentation' block with section buttons,
        organ buttons, and a Run Segmentation button.
        """
        title = QLabel("AI Segmentation")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #00ccff;")
        sidebar_layout.addWidget(title)

        subtitle = QLabel("Select section, pick organs, click Run Segmentation.")
        subtitle.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        subtitle.setWordWrap(True)
        sidebar_layout.addWidget(subtitle)

        # -- Map button --
        map_btn = QPushButton("Map")
        map_btn.setToolTip("Show the TotalSegmentator class overview map")
        map_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a3a4a;
                color: #88bbcc;
                border: 1px solid #005577;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #005577; color: white; }
        """)
        map_btn.clicked.connect(self._show_class_map)
        sidebar_layout.addWidget(map_btn)

        # -- Segment All button --
        all_btn = QPushButton("Segment All")
        all_btn.setToolTip("Run TotalSegmentator on all organs at once")
        all_btn.setStyleSheet("""
            QPushButton {
                background-color: #004d40;
                color: #80cbc4;
                border: 1px solid #00695c;
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #00695c; color: white; }
            QPushButton:disabled { background-color: #333333; color: #666666; border: 1px solid #444444; }
        """)
        all_btn.clicked.connect(self._on_segment_all_clicked)
        sidebar_layout.addWidget(all_btn)

        # -- Section buttons --
        section_container = QWidget()
        section_container.setObjectName("section_buttons_container")
        sec_layout = QVBoxLayout(section_container)
        sec_layout.setSpacing(1)
        sec_layout.setContentsMargins(0, 0, 0, 0)

        all_sections = get_sections()
        row = QHBoxLayout()
        row.setSpacing(1)
        for i, sec in enumerate(all_sections):
            btn = QPushButton(sec)
            btn.setObjectName(f"section_btn_{sec}")
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1a3a4a;
                    color: #88bbcc;
                    border: 1px solid #005577;
                    border-radius: 4px;
                    padding: 4px 6px;
                    font-size: 11px;
                }
                QPushButton:hover  { background-color: #005577; color: white; }
                QPushButton:checked {
                    background-color: #007799;
                    color: white;
                    border: 1px solid #00ccff;
                }
            """)
            btn.clicked.connect(lambda checked, s=sec: self._on_section_clicked(s))
            row.addWidget(btn)
            if (i + 1) % 3 == 0 and i + 1 < len(all_sections):
                sec_layout.addLayout(row)
                row = QHBoxLayout()
                row.setSpacing(1)
        sec_layout.addLayout(row)
        sidebar_layout.addWidget(section_container)

        # -- Status label --
        status_label = QLabel("Select a section above to begin.")
        status_label.setObjectName("landmark_status_label")
        status_label.setWordWrap(True)
        status_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        sidebar_layout.addWidget(status_label)

        # -- Organ buttons/results container --
        self._landmark_buttons_container = QWidget()
        self._landmark_buttons_container.setObjectName("landmark_buttons_container")
        sidebar_layout.addWidget(self._landmark_buttons_container)

        # -- Running status label (above the Run button) --
        self._run_status_label = QLabel("")
        self._run_status_label.setObjectName("run_status_label")
        self._run_status_label.setWordWrap(True)
        self._run_status_label.setAlignment(Qt.AlignCenter)
        self._run_status_label.setStyleSheet("color: #00ccff; font-size: 11px; font-weight: bold;")
        self._run_status_label.setVisible(False)
        sidebar_layout.addWidget(self._run_status_label)

        # -- Run detection button --
        self._detect_btn = QPushButton("Run Segmentation")
        self._detect_btn.setObjectName("run_detection_btn")
        self._detect_btn.setVisible(False)
        self._detect_btn.setEnabled(False)
        self._detect_btn.setStyleSheet("""
            QPushButton {
                background-color: #005577;
                color: white;
                border: 1px solid #00ccff;
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
            }
            QPushButton:hover  { background-color: #007799; }
            QPushButton:pressed{ background-color: #0099bb; }
            QPushButton:disabled { background-color: #333333; color: #666666; border: 1px solid #444444; }
        """)
        self._detect_btn.clicked.connect(self._on_run_detection_clicked)
        sidebar_layout.addWidget(self._detect_btn)

    # ------------------------------------------------------------------
    # Section / organ helpers
    # ------------------------------------------------------------------

    def _on_segment_all_clicked(self):
        """Run TotalSegmentator on ALL organs across all sections."""
        if self.image_array is None:
            self._set_landmark_status("Load an image first.", "#ff6666")
            return

        self._active_section = None
        self._selected_organs = set()
        self.landmark_positions = {}

        for sec in get_sections():
            btn = self.findChild(QPushButton, f"section_btn_{sec}")
            if btn and btn.isChecked():
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)

        all_organs = get_all_organs()
        self._set_landmark_status(f"Segmenting all ({len(all_organs)} organs)...", "#00ccff")
        self._clear_organ_buttons()
        self._detect_btn.setVisible(False)

        self.run_landmark_detection(all_organs)

    def _on_section_clicked(self, section: str):
        """Called when a section button is clicked."""
        self._active_section  = section
        self._selected_organs = set()
        self.landmark_positions = {}

        # Block signals when updating other buttons to avoid re-entry
        for sec in get_sections():
            btn = self.findChild(QPushButton, f"section_btn_{sec}")
            if btn and btn.isChecked() != (sec == section):
                btn.blockSignals(True)
                btn.setChecked(sec == section)
                btn.blockSignals(False)

        desc = get_section_description(section)
        self._set_landmark_status(f"Selected: {section} \u2014 {desc}", "#aaaaaa")

        self._detect_btn.setVisible(True)
        self._detect_btn.setEnabled(False)
        self._detect_btn.setText(f"Run Segmentation — {section}")

        self._populate_organ_checkboxes(section)

    def _populate_organ_checkboxes(self, section: str):
        """Populate toggle buttons for all organs in the section (2‑column grid)."""
        container = self._get_landmark_buttons_container()
        if container is None:
            return

        old_layout = container.layout()
        if old_layout is not None:
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            QWidget().setLayout(old_layout)

        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(1)
        container.setLayout(grid)

        organs = get_organs_for_section(section)
        if not organs:
            placeholder = QLabel("No organs configured for this section.")
            placeholder.setStyleSheet("color: #666666; font-size: 11px; font-style: italic;")
            grid.addWidget(placeholder)
            return

        label = QLabel("Select organs, then click Run Segmentation:")
        label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        grid.addWidget(label, 0, 0, 1, 2)

        self._organ_checkboxes = {}
        for idx, name in enumerate(organs):
            btn = QPushButton(f"  {name}")
            btn.setObjectName(f"organ_btn_{name}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1a3a4a;
                    color: #88bbcc;
                    border: 1px solid #005577;
                    border-radius: 3px;
                    padding: 2px 4px;
                    text-align: left;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: #005577;
                    color: white;
                    border: 1px solid #00ccff;
                }
                QPushButton:checked {
                    background-color: #007799;
                    color: white;
                    border: 1px solid #00ccff;
                }
            """)
            btn.toggled.connect(lambda checked, n=name: self._on_organ_toggled(n, checked))
            grid.addWidget(btn, idx // 2 + 1, idx % 2)
            self._organ_checkboxes[name] = btn

        container.updateGeometry()
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

    def _on_organ_toggled(self, name: str, checked: bool):
        """Track selected organs and update button state."""
        if checked:
            self._selected_organs.add(name)
        else:
            self._selected_organs.discard(name)

        has_selection = len(self._selected_organs) > 0
        self._detect_btn.setEnabled(has_selection)
        if has_selection:
            section = getattr(self, "_active_section", "")
            self._detect_btn.setText(
                f"Segment {len(self._selected_organs)} organ(s) — {section}"
            )
        else:
            section = getattr(self, "_active_section", "")
            self._detect_btn.setText(f"Run Segmentation — {section}")

    def _on_run_detection_clicked(self):
        """Run TotalSegmentator detection for the currently selected organs."""
        section = getattr(self, "_active_section", None)
        if not section or not self._selected_organs:
            return

        all_organs = get_organs_for_section(section)
        organ_map = {
            name: stem
            for name, stem in all_organs.items()
            if name in self._selected_organs
        }

        if not organ_map:
            return

        self._detect_btn.setEnabled(False)
        self._detect_btn.setText("Running...")
        self.run_landmark_detection(organ_map)

    def _populate_organ_results(self):
        """
        After detection, replace checkboxes with navigation buttons
        for found organs and disabled entries for unfound ones.
        """
        container = self._get_landmark_buttons_container()
        if container is None:
            return

        layout = container.layout()
        if layout is None:
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(1)
            container.setLayout(layout)

        self._clear_organ_buttons()

        section = getattr(self, "_active_section", None)
        if section:
            organs = get_organs_for_section(section)
            selected = getattr(self, "_selected_organs", set())
        else:
            # "Segment All" mode — use all found organs
            organs = list(self.landmark_positions.keys())
            selected = set(organs)

        if not organs:
            return

        found_count = sum(1 for n in organs if n in self.landmark_positions)
        total = len(self._selected_organs) if self._selected_organs else len(organs)
        label = QLabel(f"Results ({found_count}/{total} found):")
        label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        layout.addWidget(label)

        for name in organs:
            was_selected = name in selected
            is_found     = name in self.landmark_positions

            if is_found:
                z = self.landmark_positions[name][0]
                btn = QPushButton(f"\u2192 {name} (sl. {z})")
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1a3a4a;
                        color: #00ccff;
                        border: 1px solid #005577;
                        border-radius: 4px;
                        padding: 4px 8px;
                        text-align: left;
                        font-size: 12px;
                    }
                    QPushButton:hover  { background-color: #005577; color: white; }
                    QPushButton:pressed{ background-color: #007799; }
                """)
                btn.clicked.connect(lambda checked, n=name: self.navigate_to_landmark(n))
                layout.addWidget(btn)
            elif was_selected:
                lbl = QLabel(f"{name} (not found)")
                lbl.setStyleSheet("color: #555555; font-size: 11px; font-style: italic;")
                layout.addWidget(lbl)

        self._detect_btn.setEnabled(True)
        section = getattr(self, "_active_section", "")
        self._detect_btn.setText(f"Run Segmentation \u2014 {section}")

    # ------------------------------------------------------------------
    def _show_class_map(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout
        from PyQt5.QtGui import QPixmap
        import os

        path = os.path.join(os.path.dirname(__file__), "overview_classes_v2.png")
        if not os.path.isfile(path):
            self._set_landmark_status("Overview image not found.", "#ff6666")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("TotalSegmentator Class Overview")
        dialog.resize(900, 700)

        layout = QVBoxLayout(dialog)
        label = QLabel()
        pixmap = QPixmap(path)
        label.setPixmap(pixmap.scaled(
            860, 660, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        dialog.exec_()

    # ------------------------------------------------------------------
    # Widget helpers
    # ------------------------------------------------------------------

    def _get_landmark_status_label(self):
        return self.findChild(QLabel, "landmark_status_label")

    def _get_landmark_buttons_container(self):
        if hasattr(self, "_landmark_buttons_container"):
            return self._landmark_buttons_container
        return self.findChild(QWidget, "landmark_buttons_container")

    def _set_landmark_status(self, text: str, color_hex: str):
        lbl = self._get_landmark_status_label()
        if lbl:
            lbl.setText(text)
            lbl.setStyleSheet(f"color: {color_hex}; font-size: 11px;")

    def _clear_organ_buttons(self):
        container = self._get_landmark_buttons_container()
        if container is None:
            return
        layout = container.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item is None:
                continue
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._organ_checkboxes = {}
