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
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
import qdarktheme

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from PySide6.QtCore import QSettings
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow, APP_ORG, APP_NAME, TitleBarThemeFilter, _find_logo

_LOG_MAX_BYTES = 5 * 1024 * 1024
_LOG_BACKUP_COUNT = 3
_LOGGING_CONFIGURED = False


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


def configure_logging(level: int = logging.INFO) -> None:
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
        logging.getLogger("bytehound").error(
            "Uncaught exception",
            exc_info=(exc_type, exc, tb),
        )
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _handle_uncaught
    _LOGGING_CONFIGURED = True


def _run_app() -> int:
    app = QApplication(sys.argv)

    icon_path = _find_logo("logo_sq.ico") or _find_logo("logo_sq.png")
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))

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
    args, remaining = parser.parse_known_args(argv)
    # Strip our own flags so Qt sees a clean argv.
    sys.argv = [sys.argv[0], *remaining]

    configure_logging()

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
