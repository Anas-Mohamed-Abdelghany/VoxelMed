"""
main.py
-------
Application entry point.  Run with:

    python main.py
"""

import sys
import os

# Pre-load torch BEFORE PyQt5 takes over the process.
# On Windows, importing torch for the first time inside a PyQt5 QThread
# (after PyQt5 has already loaded its own C++ runtime DLLs) can fail with
# "OSError: [WinError 1114] DLL initialization routine failed" for
# torch\lib\c10.dll. Importing torch here, first, while the process DLL
# search path is still clean, avoids that conflict. Safe no-op if torch /
# TotalSegmentator are not installed — the AI landmark feature degrades
# gracefully and the rest of the viewer is unaffected either way.
try:
    import torch  # noqa: F401
except ImportError:
    pass

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
