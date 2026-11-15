"""Capture the installed launcher window inside an Xvfb smoke session."""
import sys
from PySide6.QtGui import QGuiApplication

app = QGuiApplication([])
window_id = int(sys.argv[1])
image = app.primaryScreen().grabWindow(window_id)
if image.isNull() or not image.save(sys.argv[2]):
    raise SystemExit('Could not capture installed launcher')
print(f'Captured {image.width()}x{image.height()} installed launcher to {sys.argv[2]}')
