"""
make_icns.py — Generate assets/icons/tonal.icns from any PNG.

Usage:
    python installer/make_icns.py path/to/your_icon.png

Requirements:
    - macOS (uses built-in iconutil)
    - Pillow (already in requirements.txt)
"""
import sys
import shutil
import subprocess
from pathlib import Path
from PIL import Image

SIZES = [16, 32, 64, 128, 256, 512, 1024]

def make_icns(src_png: str) -> None:
    src = Path(src_png).resolve()
    if not src.is_file():
        sys.exit(f"Error: file not found: {src}")

    project_root = Path(__file__).resolve().parent.parent
    icons_dir    = project_root / "assets" / "icons"
    iconset_dir  = project_root / "assets" / "icons" / "tonal.iconset"
    out_icns     = icons_dir / "tonal.icns"
    out_png      = icons_dir / "tonal.png"

    icons_dir.mkdir(parents=True, exist_ok=True)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(src).convert("RGBA")

    # Copy the largest version as the runtime PNG (used by QIcon in main.py)
    img.resize((1024, 1024), Image.LANCZOS).save(out_png, "PNG")
    print(f"  Saved runtime PNG  → {out_png}")

    # Write every required iconset entry
    for size in SIZES:
        # 1x
        img.resize((size, size), Image.LANCZOS).save(
            iconset_dir / f"icon_{size}x{size}.png", "PNG"
        )
        # 2x  (same pixel count as next size up, labelled @2x)
        if size <= 512:
            img.resize((size * 2, size * 2), Image.LANCZOS).save(
                iconset_dir / f"icon_{size}x{size}@2x.png", "PNG"
            )

    # Run macOS iconutil to produce the .icns
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(out_icns)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"iconutil failed:\n{result.stderr}")

    # Clean up the temporary iconset folder
    shutil.rmtree(iconset_dir)

    print(f"  Saved macOS icon   → {out_icns}")
    print("\nDone. Rebuild the app to apply the new icon:")
    print("  bash installer/build_mac.sh")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python installer/make_icns.py path/to/icon.png")
    make_icns(sys.argv[1])
