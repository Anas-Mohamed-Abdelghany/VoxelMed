"""
volume_explorer_ui.py
---------------------
UI mixin for the 3D Lab window.  Contains all widget-building methods;
the logic lives in volume_explorer.py.
"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QCheckBox, QFrame, QGroupBox, QButtonGroup,
    QRadioButton, QSizePolicy, QComboBox, QStackedWidget,
)
from PyQt5.QtCore import Qt


TISSUE_PRESETS = {
    "All tissue":  (0,   255),
    "Skin / Fat":  (20,  90),
    "Soft tissue": (90,  160),
    "Bone":        (160, 255),
}


class VolumeExplorerUIMixin:
    """Mixin providing all UI-building methods for VolumeExplorerWindow."""

    def _build_tool_panel(self):
        panel = QWidget()
        panel.setFixedWidth(300)
        panel.setStyleSheet("background-color: white; border-right: 2px solid #cccccc;")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        title = QLabel("3D Lab")
        title.setStyleSheet("font-weight: bold; font-size: 14px; color: #005577;")
        layout.addWidget(title)

        subtitle = QLabel("Cut, crop, and peel away layers to see inside the volume.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #666666; font-size: 10px;")
        layout.addWidget(subtitle)

        layout.addWidget(self._hline())

        layout.addWidget(self._build_ai_seg_group())
        layout.addWidget(self._hline())

        layout.addWidget(self._build_box_crop_group())
        layout.addWidget(self._hline())

        layout.addWidget(self._build_clip_planes_group())
        layout.addWidget(self._hline())

        layout.addWidget(self._build_tissue_layers_group())
        layout.addWidget(self._hline())

        reset_btn = QPushButton("Reset All")
        reset_btn.setStyleSheet(
            "QPushButton { background-color: #dddddd; color: #333333; "
            "font-weight: bold; padding: 5px; border-radius: 4px; font-size: 11px; border: 1px solid #cccccc; }"
            "QPushButton:hover { background-color: #cccccc; }"
        )
        reset_btn.clicked.connect(self.reset_all)
        layout.addWidget(reset_btn)

        return panel

    def _hline(self):
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("color: #cccccc;")
        return line

    # -- Box crop ------------------------------------------------------------
    def _build_box_crop_group(self):
        box = QGroupBox("Box Crop")
        box.setStyleSheet(self._group_style())
        v = QVBoxLayout(box)

        info = QLabel("Drag the box handles in the 3D view to cut away "
                       "everything outside the box.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #555555; font-size: 11px;")
        v.addWidget(info)

        self.box_crop_checkbox = QCheckBox("Enable box crop")
        self.box_crop_checkbox.setStyleSheet("color: #333333; font-size: 11px;")
        self.box_crop_checkbox.stateChanged.connect(self._on_box_crop_toggled)
        v.addWidget(self.box_crop_checkbox)

        return box

    # -- Orthogonal clipping planes ------------------------------------------
    def _build_clip_planes_group(self):
        box = QGroupBox("Orthogonal Clips")
        box.setStyleSheet(self._group_style())
        v = QVBoxLayout(box)

        info = QLabel("Slide to cut the volume along an axis. "
                       "'Flip' swaps which half is removed.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #555555; font-size: 11px;")
        v.addWidget(info)

        self.clip_sliders = {}
        self.clip_checkboxes = {}

        depth, height, width = self.image_array.shape
        axis_dims = {"x": width, "y": height, "z": depth}

        for axis in ["x", "y", "z"]:
            row = QHBoxLayout()
            cb = QCheckBox(axis.upper())
            cb.setFixedWidth(30)
            cb.setStyleSheet("color: #333333; font-size: 11px;")
            cb.stateChanged.connect(lambda state, a=axis: self._on_clip_toggled(a, state))
            row.addWidget(cb)
            self.clip_checkboxes[axis] = cb

            slider = QSlider(Qt.Horizontal)
            slider.setMinimum(0)
            slider.setMaximum(max(1, axis_dims[axis] - 1))
            slider.setValue(axis_dims[axis] // 2)
            slider.valueChanged.connect(lambda val, a=axis: self._on_clip_slider(a, val))
            row.addWidget(slider)
            self.clip_sliders[axis] = slider

            flip_btn = QPushButton("Flip")
            flip_btn.setFixedWidth(45)
            flip_btn.clicked.connect(lambda checked, a=axis: self._on_clip_flip(a))
            row.addWidget(flip_btn)

            v.addLayout(row)

        return box

    # -- AI Segmentation group -----------------------------------------------
    def _build_ai_seg_group(self):
        box = QGroupBox("AI Segmentation")
        box.setStyleSheet(self._group_style())
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 4, 6, 6)
        v.setSpacing(3)

        self._ai_stack = QStackedWidget()

        # Page 0 — Run button
        run_page = QWidget()
        rp = QVBoxLayout(run_page)
        rp.setContentsMargins(0, 0, 0, 0)
        rp.setSpacing(2)

        self._ai_run_btn = QPushButton("Run AI Segmentation")
        self._ai_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #005577; color: white;
                border: 1px solid #004466; border-radius: 4px;
                padding: 5px; font-size: 11px;
            }
            QPushButton:hover  { background-color: #007799; }
            QPushButton:disabled { background-color: #cccccc; color: #888888; border-color: #aaaaaa; }
        """)
        self._ai_run_btn.clicked.connect(self._on_ai_run)
        rp.addWidget(self._ai_run_btn)

        self._ai_progress = QLabel("")
        self._ai_progress.setWordWrap(True)
        self._ai_progress.setStyleSheet("color: #555555; font-size: 10px;")
        self._ai_progress.setVisible(False)
        rp.addWidget(self._ai_progress)

        self._ai_stack.addWidget(run_page)

        # Page 1 — Controls (organ selector + two sliders)
        ctrl_page = QWidget()
        cp = QVBoxLayout(ctrl_page)
        cp.setContentsMargins(0, 0, 0, 0)
        cp.setSpacing(2)

        organ_row = QHBoxLayout()
        organ_lbl = QLabel("Organ:")
        organ_lbl.setStyleSheet("color: #333333; font-size: 10px;")
        organ_row.addWidget(organ_lbl)
        self._ai_organ_combo = QComboBox()
        self._ai_organ_combo.setStyleSheet(
            "font-size: 10px; padding: 1px; color: #333333; "
            "background-color: white; "
            "QComboBox QAbstractItemView { color: #333333; background-color: white; selection-background-color: #cceeff; }"
        )
        self._ai_organ_combo.currentIndexChanged.connect(self._on_ai_organ_selected)
        organ_row.addWidget(self._ai_organ_combo, stretch=1)
        cp.addLayout(organ_row)

        olbl = QLabel("Organ opacity:")
        olbl.setStyleSheet("color: #333333; font-size: 10px;")
        cp.addWidget(olbl)
        self._ai_organ_slider = QSlider(Qt.Horizontal)
        self._ai_organ_slider.setRange(0, 100)
        self._ai_organ_slider.setValue(100)
        self._ai_organ_slider.valueChanged.connect(self._on_ai_organ_opacity)
        cp.addWidget(self._ai_organ_slider)

        rlbl = QLabel("Rest of volume opacity:")
        rlbl.setStyleSheet("color: #333333; font-size: 10px;")
        cp.addWidget(rlbl)
        self._ai_rest_slider = QSlider(Qt.Horizontal)
        self._ai_rest_slider.setRange(0, 100)
        self._ai_rest_slider.setValue(100)
        self._ai_rest_slider.valueChanged.connect(self._on_ai_rest_opacity)
        cp.addWidget(self._ai_rest_slider)

        self._ai_stack.addWidget(ctrl_page)
        self._ai_stack.setCurrentIndex(1 if self._ai_seg_available else 0)

        v.addWidget(self._ai_stack)
        return box

    # -- Tissue (intensity) layers -------------------------------------------
    def _build_tissue_layers_group(self):
        box = QGroupBox("Tissue Layers (intensity)")
        box.setStyleSheet(self._group_style())
        v = QVBoxLayout(box)

        info = QLabel("Works without any segmentation. Peel back low-density "
                       "tissue (skin/fat) to reveal denser structures (organs/bone).")
        info.setWordWrap(True)
        info.setStyleSheet("color: #555555; font-size: 11px;")
        v.addWidget(info)

        preset_col = QVBoxLayout()
        preset_col.setSpacing(1)
        self.tissue_preset_group = QButtonGroup(self)
        for name in TISSUE_PRESETS:
            btn = QRadioButton(name)
            btn.setStyleSheet("font-size: 11px; color: #333333;")
            if name == "All tissue":
                btn.setChecked(True)
            btn.toggled.connect(lambda checked, n=name: self._on_tissue_preset(n, checked))
            self.tissue_preset_group.addButton(btn)
            preset_col.addWidget(btn)
        v.addLayout(preset_col)

        v.addWidget(QLabel("lower-bound cutoff:"))
        self.tissue_threshold_slider = QSlider(Qt.Horizontal)
        self.tissue_threshold_slider.setRange(0, 255)
        self.tissue_threshold_slider.setValue(0)
        self.tissue_threshold_slider.valueChanged.connect(self._on_tissue_threshold_changed)
        v.addWidget(self.tissue_threshold_slider)

        return box

    # -- Shared styles -------------------------------------------------------
    def _group_style(self):
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
