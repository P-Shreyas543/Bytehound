"""Application entry point for Single-Cell BMS Cycler."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from single_cell_cycler.config.cycler_config import DEFAULT_LOG_DIR
from single_cell_cycler.ui.main_window import MainWindow

def main():
    # Ensure logs folder exists
    DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    app_log_path = DEFAULT_LOG_DIR / "cycler_app.txt"

    # Configure logging to continuously append to cycler_app.txt in logs folder
    file_handler = logging.FileHandler(app_log_path, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)

    # Keep console clean from continuous frame/state output; only display critical warnings/errors
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    )
    # -------------------------------------------------------------------------
    # Diagnostic Hooks: Uncaught Exceptions, Thread Failures & Qt Warnings
    # -------------------------------------------------------------------------
    import os
    import platform
    import threading
    import traceback
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.critical(
            "CRITICAL: Unhandled exception in main application thread:",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = handle_uncaught_exception

    def handle_thread_exception(args):
        logging.critical(
            f"CRITICAL: Unhandled exception in worker thread '{args.thread.name}':",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = handle_thread_exception

    def qt_message_handler(mode, context, message):
        if mode == QtMsgType.QtDebugMsg:
            logging.debug(f"[Qt Debug] {message}")
        elif mode == QtMsgType.QtInfoMsg:
            logging.info(f"[Qt Info] {message}")
        elif mode == QtMsgType.QtWarningMsg:
            logging.warning(f"[Qt Warning] {message}")
        elif mode == QtMsgType.QtCriticalMsg:
            logging.error(f"[Qt Critical] {message}")
        elif mode == QtMsgType.QtFatalMsg:
            logging.critical(f"[Qt Fatal] {message}")

    qInstallMessageHandler(qt_message_handler)

    # Diagnostic Environment Header
    try:
        import serial.tools.list_ports
        ports = [f"{p.device} ({p.description})" for p in serial.tools.list_ports.comports()]
        port_str = ", ".join(ports) if ports else "None detected"
    except Exception as exc:
        port_str = f"Scan failed: {exc}"

    print(f"[Bytehound Cycler] Operational & diagnostic logging -> {app_log_path}")
    logging.info("=" * 70)
    logging.info("=== Bytehound Single-Cell Cycler Application Started ===")
    logging.info(f"System: {platform.platform()} | Python: {platform.python_version()} ({sys.executable})")
    logging.info(f"Process PID: {os.getpid()} | Working Dir: {Path.cwd()}")
    logging.info(f"Active Diagnostic Log: {app_log_path}")
    logging.info(f"Detected Serial Ports: {port_str}")
    logging.info("=" * 70)

    app = QApplication.instance()
    if not app:
        # Enable High-DPI scaling before QApplication instantiation
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(sys.argv)

    app.setFont(QFont("Segoe UI", 10))
    app.setApplicationName("Bytehound Single-Cell Cycler")
    app.setOrganizationName("Bytehound")

    # Locate and set Bytehound branding icon
    branding_dir = _REPO_ROOT / "branding"
    if hasattr(sys, "_MEIPASS"):
        branding_dir = Path(sys._MEIPASS) / "branding"

    ico_path = branding_dir / "logo.ico"
    app_icon = None
    if ico_path.exists():
        from PySide6.QtGui import QIcon
        app_icon = QIcon(str(ico_path))
        app.setWindowIcon(app_icon)

    window = MainWindow(app_icon=app_icon)
    if app_icon:
        window.setWindowIcon(app_icon)

    # Enable native Windows 10/11 immersive dark mode on title bar
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import c_int, byref, sizeof
            hwnd = int(window.winId())
            val = c_int(1)
            # DWMWA_USE_IMMERSIVE_DARK_MODE (20 on Windows 10 build 18985+ and Windows 11; 19 on earlier builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, byref(val), sizeof(val)) != 0:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, byref(val), sizeof(val))
        except Exception as exc:
            logging.debug(f"Could not enable DWM dark title bar: {exc}")

    app.aboutToQuit.connect(window.close)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
