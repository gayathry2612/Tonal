# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Tonal
#
# Usage (from project root):
#   pyinstaller installer/tonal.spec
#
# Produces:
#   dist/Tonal.app       (macOS)
#   dist/Tonal/Tonal.exe (Windows)

import sys
import os
from pathlib import Path

project_root = Path(SPECPATH).parent          # …/Music player/
src_root     = project_root / "src"
assets_dir   = project_root / "assets"

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
a = Analysis(
    [str(src_root / "tonal" / "main.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=[
        # Bundle the assets folder
        (str(assets_dir), "assets"),
    ],
    hiddenimports=[
        # PySide6 multimedia plugins
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        # mutagen parsers
        "mutagen.mp3",
        "mutagen.flac",
        "mutagen.mp4",
        "mutagen.oggvorbis",
        "mutagen.wavpack",
        "mutagen.id3",
        "mutagen.aiff",
        # Pillow
        "PIL.Image",
        "PIL.JpegImagePlugin",
        "PIL.PngImagePlugin",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Things we definitely don't need
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "pandas",
        "IPython",
        "notebook",
    ],
    noarchive=False,
    optimize=1,
)

# ---------------------------------------------------------------------------
# PYZ archive
# ---------------------------------------------------------------------------
pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
# macOS .app bundle
# ---------------------------------------------------------------------------
if sys.platform == "darwin":
    icon_path = str(assets_dir / "icons" / "tonal.icns")
    icon      = icon_path if os.path.isfile(icon_path) else None

    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="Tonal",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,        # no terminal window
        disable_windowed_traceback=False,
        icon=icon,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="Tonal",
    )

    app = BUNDLE(
        coll,
        name="Tonal.app",
        icon=icon,
        bundle_identifier="com.tonal.musicplayer",
        info_plist={
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion":            "1.0.0",
            "NSHighResolutionCapable":    True,
            "NSMicrophoneUsageDescription": "",
            # Allow reading local audio files
            "com.apple.security.files.user-selected.read-only": True,
        },
    )

# ---------------------------------------------------------------------------
# Windows .exe
# ---------------------------------------------------------------------------
elif sys.platform == "win32":
    icon_path = str(assets_dir / "icons" / "tonal.ico")
    icon      = icon_path if os.path.isfile(icon_path) else None

    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="Tonal",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        icon=icon,
        version="installer/win_version_info.txt",  # optional
    )

# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="tonal",
        debug=False,
        strip=False,
        upx=True,
        console=False,
    )
