# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = [('version.json', '.'), ('app/resources/*', 'app/resources/')]
binaries = []
hiddenimports = ['pyqtgraph', 'numpy', 'openpyxl', 'serial', 'pandas', 'qdarktheme']

# Collect every binary, data file, and submodule of PySide6 + shiboken6
# so PySide6/__init__._additional_dll_directories() finds shiboken6 next to it.
raw_datas = []
raw_binaries = []
raw_hiddenimports = []
for pkg in ('PySide6', 'shiboken6'):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    raw_datas += pkg_datas
    raw_binaries += pkg_binaries
    raw_hiddenimports += pkg_hidden

# Massive unused modules and packages to exclude to reduce build bloat and resolve warnings
excluded_modules = {
    # Large third-party packages that are not used but get dragged in
    'torch', 'scipy', 'matplotlib', 'sympy', 'IPython', 'tornado', 'twisted',
    'PIL', 'lxml', 'pygments', 'tensorflow', 'coremltools', 'pytorch_lightning',
    'jinja2', 'jedi', 'psutil',
    
    # Unused PySide6 submodules
    'QtWebEngineCore', 'QtWebEngineQuick', 'QtWebEngine', 'QtWebView', 'QtWebViewQuick',
    'Qt3DCore', 'Qt3DRender', 'Qt3DInput', 'Qt3DLogic', 'Qt3DExtras', 'Qt3DAnimation',
    'QtMultimedia', 'QtMultimediaWidgets', 'QtCharts', 'QtDataVisualization',
    'QtVirtualKeyboard', 'QtQuick', 'QtQuickWidgets', 'QtQuickControls2',
    'QtQml', 'QtQmlModels', 'QtRemoteObjects', 'QtScxml', 'QtSensors',
    'QtSerialBus', 'QtPositioning', 'QtBluetooth', 'QtNfc', 'QtWebChannel',
    'QtWebSockets', 'QtSql', 'QtTest', 'QtXmlPatterns', 'QtTextToSpeech', 'QtLocation',
    'QtSpatialAudio', 'QtDesigner', 'QtHelp', 'QtQuickTemplates2', 'QtQuickControls2Impl',
    'QtQuickLayouts', 'QtQuickDialogs2', 'QtQuickDialogs2QuickImpl', 'QtQuickDialogs2Utils',
    'QtQuickEffects', 'QtQuickParticles', 'QtQuickShapes', 'QtQuickTest', 'QtQuickTimeline',
    'QtQuickTimelineBlendTrees', 'QtQuickVectorImage', 'QtQuickVectorImageGenerator',
    'QtQuickVectorImageHelpers', 'QtStateMachine', 'QtStateMachineQml', 'QtWebViewQuick'
}

def is_excluded(item_name: str) -> bool:
    # Normalize by converting to lowercase and removing '6'
    normalized = item_name.lower().replace('qt6', 'qt')
    for m in excluded_modules:
        if m.lower() in normalized:
            return True
    return False

# Filter collected PySide6/shiboken6 files
for src, dst in raw_datas:
    if not is_excluded(src) and not is_excluded(dst):
        datas.append((src, dst))

for src, dst in raw_binaries:
    if not is_excluded(src) and not is_excluded(dst):
        binaries.append((src, dst))

for imp in raw_hiddenimports:
    if not is_excluded(imp):
        hiddenimports.append(imp)

# List of explicit excludes for PyInstaller Analysis
excludes_list = [
    'PyQt5', 'PyQt6', 'PySide2',
    'torch', 'scipy', 'matplotlib', 'sympy', 'IPython', 'tornado', 'twisted',
    'PIL', 'lxml', 'pygments', 'tensorflow', 'coremltools', 'pytorch_lightning',
    'jinja2', 'jedi', 'psutil'
] + [f'PySide6.{m}' for m in excluded_modules]

a = Analysis(
    ['app/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes_list,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Post-analysis filtering to strip out any unwanted binaries/datas collected by default hooks
a.binaries = [bin_entry for bin_entry in a.binaries if not is_excluded(bin_entry[0]) and not is_excluded(bin_entry[1])]
a.datas = [data_entry for data_entry in a.datas if not is_excluded(data_entry[0]) and not is_excluded(data_entry[1])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Bytehound',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Embed the logo as the exe's icon resource. Without this, Windows
    # falls back to a generic application icon everywhere the exe icon
    # is shown — taskbar, alt-tab, file explorer, and the Programs &
    # Features uninstall entry (which reads its icon from this exe via
    # UninstallDisplayIcon in installer.iss).
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Bytehound',
)
