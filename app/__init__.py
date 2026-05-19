"""Bytehound app package.

Bootstrap note: ``pyqtgraph`` auto-detects its Qt binding by trying imports in
alphabetical order — if both ``PyQt6`` and ``PySide6`` are installed, it picks
PyQt6 first, which then conflicts with our PySide6 widgets (e.g. QAction(parent)
type checks fail because parent's QObject is from a different binding). Setting
``PYQTGRAPH_QT_LIB`` *before* any submodule loads pyqtgraph forces the choice
to match the rest of the app.
"""

import os

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")
