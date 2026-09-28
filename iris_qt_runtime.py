import os
import sys
from pathlib import Path

# Make Qt Quick/QML modules discoverable in a PyInstaller frozen app.
if getattr(sys, "frozen", False):
    root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    qml = root / "PySide6" / "qml"
    plugins = root / "PySide6" / "plugins"
    if qml.exists():
        os.environ["QML2_IMPORT_PATH"] = str(qml)
    if plugins.exists():
        os.environ["QT_PLUGIN_PATH"] = str(plugins)
