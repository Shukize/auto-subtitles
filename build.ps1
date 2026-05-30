# Build Subtitle Studio into a distributable Windows app folder.
# Usage:  .\build.ps1
$ErrorActionPreference = "Stop"
$python = ".\.venv\Scripts\python.exe"

Write-Host "Cleaning previous build..." -ForegroundColor Cyan
if (Test-Path build) { Remove-Item build -Recurse -Force }
if (Test-Path dist)  { Remove-Item dist  -Recurse -Force }

Write-Host "Running PyInstaller (this can take several minutes)..." -ForegroundColor Cyan
& $python -m PyInstaller SubtitleStudio.spec --noconfirm

if (Test-Path "dist\SubtitleStudio\SubtitleStudio.exe") {
    Write-Host "`nBuild succeeded:" -ForegroundColor Green
    Write-Host "  dist\SubtitleStudio\SubtitleStudio.exe"
    $size = (Get-ChildItem dist\SubtitleStudio -Recurse | Measure-Object Length -Sum).Sum / 1MB
    Write-Host ("  Total size: {0:N0} MB" -f $size)
} else {
    Write-Host "Build failed - SubtitleStudio.exe not found." -ForegroundColor Red
    exit 1
}
