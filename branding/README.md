# Branding assets

Drop the following files here. `build.py` copies them next to the
`Serial-MonitorApp.exe` after every build (NOT into `_internal/`), and the
runtime picks them up via `_find_logo()` in `app/ui/main_window.py`.

| File           | Size                                  | Purpose                                                              |
|----------------|---------------------------------------|----------------------------------------------------------------------|
| `logo_sq.ico`  | 256×256 (with 16/32/48/64/128 frames) | Window icon, taskbar icon, exe icon, installer icon                  |
| `logo_sq.png`  | 512×512                               | PNG fallback for places that won't render `.ico`                     |
| `logo_rec.png` | ~512×200                              | Rectangular logo for in-window banners / about dialog                |

The runtime searches `branding/` first, then the project/exe root.
If no logo is found, the app falls back to the default Qt icon — the build
does not fail.
