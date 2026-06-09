# CyberRadio-Gen Setup Script for Windows
# Run this in PowerShell (right-click → Run with PowerShell, or open PowerShell here and type: .\setup.ps1)

$Host.UI.RawUI.WindowTitle = "CyberRadio-Gen — Setup"

Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║        CyberRadio-Gen — Setup               ║" -ForegroundColor Cyan
Write-Host "║  AI-generated radio for Cyberpunk 2077      ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Check Python ──────────────────────────────────────────────────────
Write-Host "▶ Step 1/3: Checking Python..." -ForegroundColor Yellow

$python = $null
foreach ($cmd in @("python", "python3")) {
    $ver = & $cmd --version 2>$null
    if ($LASTEXITCODE -eq 0 -and $ver -match "Python (\d+)\.(\d+)") {
        $major = [int]$Matches[1]
        $minor = [int]$Matches[2]
        if ($major -ge 3 -and $minor -ge 10) {
            $python = $cmd
            Write-Host "  ✅ Found Python $major.$minor+ ($cmd)" -ForegroundColor Green
            break
        }
    }
}

if (-not $python) {
    Write-Host "  ❌ Python 3.10+ not found." -ForegroundColor Red
    Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

# ── Step 2: Create virtual environment + install deps ─────────────────────────
Write-Host ""
Write-Host "▶ Step 2/3: Setting up virtual environment..." -ForegroundColor Yellow

if (Test-Path "venv") {
    Write-Host "  ℹ️  Virtual environment already exists. Skipping creation." -ForegroundColor Gray
} else {
    & $python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ❌ Failed to create virtual environment." -ForegroundColor Red
        Write-Host "Press any key to exit..."
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
        exit 1
    }
    Write-Host "  ✅ Virtual environment created." -ForegroundColor Green
}

# Activate and install
$pip = if ($IsWindows -or $env:OS) { ".\venv\Scripts\pip" } else { "./venv/bin/pip" }

Write-Host "  📦 Installing dependencies..." -ForegroundColor Gray
& $pip install --quiet --upgrade pip 2>$null
& $pip install --quiet -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ Failed to install dependencies." -ForegroundColor Red
    Write-Host "  Try running manually: $pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}

Write-Host "  ✅ Dependencies installed." -ForegroundColor Green

# ── Step 3: Check FFmpeg ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "▶ Step 3/3: Checking FFmpeg..." -ForegroundColor Yellow

$ffmpeg = (Get-Command "ffmpeg" -ErrorAction SilentlyContinue)
if ($ffmpeg) {
    Write-Host "  ✅ FFmpeg found at: $($ffmpeg.Source)" -ForegroundColor Green
} else {
    Write-Host "  ⚠️  FFmpeg not found on PATH." -ForegroundColor Yellow
    Write-Host "  Download from: https://ffmpeg.org/download.html" -ForegroundColor Yellow
    Write-Host "  Add the bin folder to your system PATH, or the app will skip radio effects." -ForegroundColor Yellow
    Write-Host "  (The station will still work — audio just won't have the FM filter.)" -ForegroundColor Gray
}

# ── Verify import ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "▶ Verifying installation..." -ForegroundColor Yellow

$activate = if ($IsWindows -or $env:OS) { ".\venv\Scripts\Activate.ps1" } else { "./venv/bin/Activate.ps1" }

$test = & $pip list --format=columns 2>$null
if ($test -match "customtkinter" -and $test -match "requests") {
    Write-Host "  ✅ All packages installed and importable." -ForegroundColor Green
} else {
    Write-Host "  ❌ Package check failed. Try running manually:" -ForegroundColor Red
    Write-Host "      $pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host "Press any key to exit..."
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}
& $python -c "import sys; sys.path.insert(0, '.'); from tts_client import *; from suno_client import *; from pipeline import *; from app_gui import *; print('  ✅ All modules compile OK')" 2>&1

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║        Setup complete!                       ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Run the app:" -ForegroundColor White
Write-Host "    .\venv\Scripts\Activate.ps1     # activate environment" -ForegroundColor Gray
Write-Host "    python main.py                  # launch CyberRadio-Gen" -ForegroundColor Gray
Write-Host ""
Write-Host "  Or just run (double-click):" -ForegroundColor White
Write-Host "    run.bat" -ForegroundColor Gray
Write-Host ""

Write-Host "  ℹ️  Double-click run.bat to launch the app (already created)." -ForegroundColor Gray
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
