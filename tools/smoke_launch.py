"""Headless launch smoke: boot the real MainWindow offscreen with isolated
settings, pump the event loop, exercise a few UI paths, close cleanly.

Run:  python tools/smoke_launch.py
Exit status = number of failed checks (0 = all good). The user's real
settings are never touched (QSettings is redirected to a temp .ini).
"""
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
REPO = Path(__file__).resolve().parents[1]
SCRATCH = Path(tempfile.mkdtemp(prefix="bh_smoke_")) / "smoke_settings.ini"
sys.path.insert(0, str(REPO))
os.chdir(REPO)

import PySide6.QtCore as QtCore  # noqa: E402

_RealQSettings = QtCore.QSettings


class IsolatedQSettings(_RealQSettings):
    def __init__(self, *args, **kwargs):
        # (org, app) / () -> redirect to scratch ini; explicit file paths pass through.
        if len(args) <= 2 and all(isinstance(a, str) for a in args) and not (
            args and (args[0].endswith(".ini") or "/" in args[0] or "\\" in args[0])
        ):
            super().__init__(str(SCRATCH), _RealQSettings.Format.IniFormat)
        else:
            super().__init__(*args, **kwargs)


QtCore.QSettings = IsolatedQSettings

errors = []
_orig_hook = sys.excepthook


def hook(t, v, tb):
    errors.append("".join(traceback.format_exception(t, v, tb)))
    _orig_hook(t, v, tb)


sys.excepthook = hook

from PySide6.QtWidgets import QApplication  # noqa: E402
import qdarktheme  # noqa: E402

from app.ui import main_window as mw  # noqa: E402

mw.MainWindow._check_and_recover_temp_logs = lambda self, *a, **k: None

app = QApplication(sys.argv[:1])
app.setApplicationName("Bytehound")
app.setOrganizationName("Bytehound")
qdarktheme.setup_theme("dark", corner_shape="rounded")


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"[{' OK ' if cond else 'FAIL'}] {name} {detail}")


t0 = time.time()
w = mw.MainWindow()
w.show()
pump(3)
check("MainWindow constructed + shown", w.isVisible(), f"({time.time() - t0:.2f}s)")
check("Window title set", bool(w.windowTitle()), repr(w.windowTitle()))
check("Window has non-trivial size", w.width() > 400 and w.height() > 300, f"{w.width()}x{w.height()}")

# Load the bundled template config, if the window exposes a loader.
tmpl = REPO / "app" / "resources" / "config_template"
loader = getattr(w, "_load_config_from_path", None) or getattr(w, "load_config", None)
if loader and tmpl.exists():
    try:
        loader(str(tmpl))
        pump(1.5)
        check("Bundled config_template loads", getattr(w, "_config", None) is not None)
    except Exception as e:  # noqa: BLE001
        check("Bundled config_template loads", False, repr(e))
else:
    print("[skip] no config loader method / template found")

# Toggle theme through the same path the UI uses, if present.
for name in ("_apply_theme", "_on_theme_changed", "set_theme"):
    fn = getattr(w, name, None)
    if callable(fn):
        try:
            fn("light")
            pump(0.5)
            fn("dark")
            pump(0.5)
            check(f"Theme switch via {name}", True)
        except TypeError:
            continue
        except Exception as e:  # noqa: BLE001
            check(f"Theme switch via {name}", False, repr(e))
        break

w.close()
pump(1)
check("Window closed cleanly", not w.isVisible())
check("No uncaught exceptions", not errors, f"({len(errors)})")
for e in errors:
    print(e)

failed = sum(1 for _, ok in results if not ok)
print(f"\nPASSED: {len(results) - failed}  FAILED: {failed}")
app.quit()
sys.exit(failed)
