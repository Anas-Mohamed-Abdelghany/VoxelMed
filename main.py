"""
main.py
-------
Application entry point.  Run with:

    python main.py
"""

import sys
from PyQt5.QtWidgets import QApplication
from image_viewer import ImageViewer

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    viewer = ImageViewer()
    viewer.showMaximized()
    sys.exit(app.exec_())
