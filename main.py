"""
main.py
-------
Application entry point.  Run with:

    python main.py
"""

import sys
import os
from PyQt5.QtWidgets import QApplication
from image_viewer import ImageViewer

if __name__ == "__main__":
    # Prevent OpenCV's Qt plugins from overriding PyQt5 plugins
    os.environ.pop("QT_QPA_PLATFORM_PLUGIN_PATH", None)
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    viewer = ImageViewer()
    viewer.showMaximized()
    sys.exit(app.exec_())
