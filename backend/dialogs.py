"""
dialogs.py
----------
Standalone dialog classes used by ImageViewer:
  - WindowLevelDialog  : sliders for adjusting window/level of displayed image.
  - show_help()        : free function that opens the help text dialog.
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QSlider, QLabel, QPushButton, QTextEdit
)
from PyQt5.QtCore import Qt


def show_help(parent):
    """Open the Help dialog (free function, called by the toolbar action)."""
    dialog = QDialog(parent)
    dialog.setWindowTitle("Help")
    dialog.setFixedSize(400, 300)

    layout = QVBoxLayout()

    help_text = QTextEdit()
    help_text.setReadOnly(True)
    help_content = """
    <h2>Enhanced By Anas, Zyad, Hassan, Nada</h2>
    <p>This application allows you to view and interact with medical images
       in axial, sagittal, and coronal planes.</p>
    <h3>Features:</h3>
    <ul>
        <li><b>Import:</b> Import medical images in various formats.</li>
        <li><b>Segmentation:</b> Use tools like Brush, Eraser, and Threshold for segmentation.</li>
        <li><b>Measurement:</b> Measure distances and areas within the image.</li>
        <li><b>Window/Level:</b> Adjust the intensity window and level for better visualisation.</li>
        <li><b>3D Rendering:</b> View the 3D volume rendering of the image.</li>
        <li><b>Zoom in and Zoom out:</b> Zoom in and out of the image slices.</li>
    </ul>
    """
    help_text.setHtml(help_content)
    layout.addWidget(help_text)

    close_button = QPushButton("Close")
    close_button.clicked.connect(dialog.accept)
    layout.addWidget(close_button)

    dialog.setLayout(layout)
    dialog.exec_()
