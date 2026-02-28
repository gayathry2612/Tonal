#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Tonal – macOS build script
#  Produces: dist/Tonal.dmg
#
#  Prerequisites (install once):
#    pip install pyinstaller PySide6 mutagen Pillow
#    brew install create-dmg          # for the DMG step
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "═══════════════════════════════════════════"
echo "  Tonal – macOS build"
echo "═══════════════════════════════════════════"

# ── 1. Virtual environment / deps ────────────────────────────
if [ ! -d ".venv" ]; then
    echo "→ Creating virtual environment…"
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "→ Installing / upgrading dependencies…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# ── 2. Clean previous build ───────────────────────────────────
echo "→ Cleaning previous build artefacts…"
rm -rf build dist

# ── 3. PyInstaller ───────────────────────────────────────────
echo "→ Running PyInstaller…"
pyinstaller installer/tonal.spec --noconfirm

# ── 4. Verify .app was created ───────────────────────────────
APP_PATH="dist/Tonal.app"
if [ ! -d "$APP_PATH" ]; then
    echo "✗  Build failed: $APP_PATH not found"
    exit 1
fi
echo "✓  Built: $APP_PATH"

# ── 5. Create DMG (requires create-dmg) ──────────────────────
if command -v create-dmg &>/dev/null; then
    echo "→ Creating DMG…"
    DMG_PATH="dist/Tonal.dmg"
    rm -f "$DMG_PATH"

    create-dmg \
        --volname "Tonal" \
        --volicon "assets/icons/tonal.icns" \
        --window-pos 200 120 \
        --window-size 600 400 \
        --icon-size 128 \
        --icon "Tonal.app" 150 185 \
        --hide-extension "Tonal.app" \
        --app-drop-link 450 185 \
        --no-internet-enable \
        "$DMG_PATH" \
        "$APP_PATH"

    echo "✓  DMG created: $DMG_PATH"
else
    echo "⚠  create-dmg not found (brew install create-dmg)."
    echo "   You can distribute dist/Tonal.app directly, or zip it:"
    cd dist && zip -r Tonal.zip Tonal.app && cd ..
    echo "✓  Created: dist/Tonal.zip"
fi

echo ""
echo "═══════════════════════════════════════════"
echo "  Build complete!"
echo "═══════════════════════════════════════════"
