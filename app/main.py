"""Entry point for the Serial-Monitor desktop app.

Run either way:
    python -m app.main          # from the project root (preferred)
    python app/main.py          # direct file run (e.g. VS Code "Code Runner")

The sys.path bootstrap at the top makes the direct-file form work too,
so editor "run file" buttons don't break.
"""

from __future__ import annotations
import argparse
import cProfile
import logging
import multiprocessing
import os
import pstats
import signal
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

import openpyxl  # MUST be imported before PySide6/qdarktheme to prevent Shiboken import hook from freezing
import qdarktheme
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow, APP_ORG, APP_NAME, _find_logo
from app.ui.widgets import TitleBarThemeFilter

_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 3
_LOGGING_CONFIGURED = False
_CRASH_DIALOG_OPEN = False


def _fallback_log_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.getenv("APPDATA") or Path.home())
        return base / APP_NAME / "logs"
    return Path.home() / f".{APP_NAME.lower()}" / "logs"


def _create_file_handler(log_path: Path) -> RotatingFileHandler | None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return RotatingFileHandler(
            log_path,
            maxBytes=_LOG_MAX_BYTES,
            backupCount=_LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        return None


def configure_logging(level: int = logging.DEBUG) -> None:
    global _LOGGING_CONFIGURED
    root = logging.getLogger()
    if _LOGGING_CONFIGURED:
        return

    root.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    primary_path = _PROJECT_ROOT / "logs" / "bytehound.log"
    file_handler = _create_file_handler(primary_path)
    if file_handler is None:
        file_handler = _create_file_handler(_fallback_log_dir() / "bytehound.log")
    if file_handler is not None:
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    else:
        root.warning("File logging disabled: could not create log file.")

    def _handle_uncaught(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return

        # Always log first — the dialog is best-effort, the log file is
        # the durable record. Re-raising in either step would lose info.
        logging.getLogger("bytehound").error(
            "Uncaught exception",
            exc_info=(exc_type, exc, tb),
        )
        # Show a modal crash dialog if a Qt app is running so the user
        # sees what happened and can copy the traceback. Wrapped in a
        # broad try because an excepthook that raises is worse than one
        # that's silent.
        try:
            _show_crash_dialog(exc_type, exc, tb)
        except Exception:
            logging.getLogger("bytehound").exception(
                "Crash dialog itself failed; original exception still logged above."
            )
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _handle_uncaught
    _LOGGING_CONFIGURED = True


def _show_crash_dialog(exc_type, exc, tb) -> None:
    """Modal crash dialog with copy-to-clipboard. No-op if no QApplication.

    Called from sys.excepthook, so it must never raise. The caller wraps
    this in its own try/except as a defence-in-depth layer.
    """
    global _CRASH_DIALOG_OPEN
    if _CRASH_DIALOG_OPEN:
        return
    _CRASH_DIALOG_OPEN = True

    import traceback
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except Exception:
        return
    app = QApplication.instance()
    if app is None:
        return  # Crash happened before/after the app — terminal output only.

    tb_text = "".join(traceback.format_exception(exc_type, exc, tb))
    short = f"{exc_type.__name__}: {exc}"

    box = QMessageBox()
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(f"{APP_NAME} — Unexpected Error")
    box.setText("An unexpected error occurred and the operation could not complete.")
    box.setInformativeText(
        f"{short}\n\nThe full traceback has been written to bytehound.log. "
        "Click 'Copy Details' to copy it to your clipboard for a bug report."
    )
    box.setDetailedText(tb_text)
    # ActionRole keeps the dialog open after click so the user can copy
    # AND read the dialog. Close button explicitly dismisses.
    copy_btn = box.addButton("Copy Details", QMessageBox.ButtonRole.ActionRole)
    close_btn = box.addButton(QMessageBox.StandardButton.Close)
    box.setDefaultButton(close_btn)

    try:
        while True:
            box.exec()
            clicked = box.clickedButton()
            if clicked is copy_btn:
                QApplication.clipboard().setText(tb_text)
                # Loop so Copy doesn't dismiss — the user can then click Close.
                continue
            break
    finally:
        _CRASH_DIALOG_OPEN = False


def _run_app() -> int:
    app = QApplication(sys.argv)

    icon_path = _find_logo("logo_sq.ico") or _find_logo("logo_sq.png")
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

    # Allow Ctrl+C to cleanly kill the application from the terminal.
    # Otherwise, PySide6 swallows the KeyboardInterrupt in its C++ event loop.
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    settings = QSettings(APP_ORG, APP_NAME)
    saved_theme = str(settings.value("ui/theme", "dark"))
    qdarktheme.setup_theme(saved_theme, corner_shape="rounded")

    font = QFont("PT Sans", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)

    titlebar_filter = TitleBarThemeFilter(settings)
    app.installEventFilter(titlebar_filter)
    app._titlebar_filter = titlebar_filter  # keep reference alive

    window = MainWindow()
    window.show()
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bytehound", add_help=True)
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Run under cProfile and dump a .prof file on exit (for diagnosing CPU usage).",
    )
    parser.add_argument(
        "--validate",
        type=str,
        metavar="CONFIG_FILE",
        help="Validate a config file without opening the GUI and exit. Returns 0 if valid, 1 otherwise.",
    )
    args, remaining = parser.parse_known_args(argv)
    # Strip our own flags so Qt sees a clean argv.
    sys.argv = [sys.argv[0], *remaining]

    configure_logging()

    if args.validate:
        try:
            from app.decoder.config_loader import load_config
            config = load_config(args.validate)
            print(f"OK: Config {args.validate} is valid.")
            print(f"Loaded {len(config.all_signals)} signals across {len(config.frames)} frames.")
            return 0
        except Exception as e:
            print(f"ERROR: Config validation failed for {args.validate}\n{e}", file=sys.stderr)
            return 1

    if not args.profile:
        return _run_app()

    profile_dir = _PROJECT_ROOT / "logs"
    profile_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    prof_path = profile_dir / f"bytehound-{stamp}.prof"

    logging.getLogger("bytehound").info("Profiling enabled — output will be %s", prof_path)

    profiler = cProfile.Profile()
    profiler.enable()
    try:
        rc = _run_app()
    finally:
        profiler.disable()
        profiler.dump_stats(str(prof_path))
        stats = pstats.Stats(profiler).sort_stats("cumulative")
        print(f"\n=== Top 30 by cumulative time ===  (full dump: {prof_path})")
        stats.print_stats(30)
        stats.sort_stats("tottime")
        print("\n=== Top 30 by self (tottime) ===")
        stats.print_stats(30)
    return rc


if __name__ == "__main__":
    # Prevent fork-bomb when the frozen EXE spawns child processes (PyInstaller).
    multiprocessing.freeze_support()
    # Enable crisp rendering on 4K / HiDPI monitors before QApplication starts.
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    sys.exit(main())
