@echo off
REM ─────────────────────────────────────────────────────────────
REM  Tonal – Windows build script
REM  Produces: dist\Tonal\Tonal.exe
REM
REM  Prerequisites (run once in PowerShell as admin):
REM    pip install pyinstaller PySide6 mutagen Pillow
REM ─────────────────────────────────────────────────────────────
setlocal enabledelayedexpansion

echo ═══════════════════════════════════════════
echo   Tonal – Windows build
echo ═══════════════════════════════════════════

cd /d "%~dp0\.."

REM ── Virtual environment ──────────────────────────────────────
if not exist ".venv" (
    echo ^→ Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
echo ^→ Installing / upgrading dependencies...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

REM ── Clean ────────────────────────────────────────────────────
echo ^→ Cleaning previous build artefacts...
if exist "build" rd /s /q "build"
if exist "dist"  rd /s /q "dist"

REM ── PyInstaller ──────────────────────────────────────────────
echo ^→ Running PyInstaller...
pyinstaller installer\tonal.spec --noconfirm

if not exist "dist\Tonal\Tonal.exe" (
    echo ^✗  Build failed: dist\Tonal\Tonal.exe not found
    exit /b 1
)

echo ^✓  Built: dist\Tonal\Tonal.exe
echo.
echo ═══════════════════════════════════════════
echo   Build complete!  Distribute the dist\Tonal folder.
echo ═══════════════════════════════════════════
