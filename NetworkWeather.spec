# -*- mode: python ; coding: utf-8 -*-
"""Reproducible Windows onedir bundle for Network Weather."""

from pathlib import Path

project_root = Path(SPECPATH).resolve()
assets = project_root / "src" / "network_weather" / "assets"

analysis = Analysis(
    [str(project_root / "scripts" / "run_desktop.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=[
        (str(assets), "network_weather/assets"),
        (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
        (str(project_root / "licenses"), "licenses"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# Some development environments place Poppler's ICU on PATH. It exports
# version-suffixed names incompatible with Qt6Core's Windows ICU imports.
# Keep Qt's own dependencies, but let Windows provide its system ICU instead
# of accidentally bundling Poppler's copy.
analysis.binaries = [
    entry for entry in analysis.binaries
    if not (
        entry[0].lower() in {"icuuc.dll", "icudt78.dll"}
        and "poppler" in entry[1].lower()
    )
    # Qt's platform-input plugin is collected by PyInstaller even though this
    # widget uses standard Windows input only. It pulls in a GPL-only module.
    and "virtualkeyboard" not in entry[0].lower()
]

archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="NetworkWeather",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="NetworkWeather",
)
