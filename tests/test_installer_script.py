"""installer.iss must stay the Bytehound installer: on 2026-09-30 it was
overwritten by another app's script and build.py stopped producing
Bytehound_Setup_<version>.exe without failing the build."""

from pathlib import Path

ISS = (Path(__file__).resolve().parents[1] / "installer.iss").read_text(encoding="utf-8-sig")


def test_installer_packages_bytehound():
    assert '#define MyAppExe       "Bytehound.exe"' in ISS
    assert r'#define MyDistDir      "dist\Bytehound"' in ISS
    assert "OutputDir                 = installer_output" in ISS
    assert "OutputBaseFilename        = Bytehound_Setup_{#MyAppVersion}" in ISS


def test_installer_keeps_identity_version_file_and_guards():
    assert "AppId                     = {{FD5F3D1F-A6B1-4A59-99E7-2485AC78B5F6}" in ISS  # upgrades in place
    assert '#include "installer_version.iss"' in ISS
    assert 'Source: "version.json";' in ISS            # the updater reads it beside the exe
    assert "function IsDowngrade" in ISS
