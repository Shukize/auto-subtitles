@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Subtitle Studio

REM Always run from the folder this script lives in (works from any shortcut).
cd /d "%~dp0"

set "VENV=.venv"
set "PY=%VENV%\Scripts\python.exe"
set "PYW=%VENV%\Scripts\pythonw.exe"

REM If the environment already exists, skip straight to launching the app.
if exist "%PY%" goto launch

REM ---------------------------------------------------------- first-time setup
echo.
echo   ============================================
echo     Subtitle Studio - first-time setup
echo   ============================================
echo.

REM Find a Python 3 interpreter to bootstrap from (prefer the py launcher).
set "BOOT="
where py >nul 2>nul && set "BOOT=py -3"
if not defined BOOT (
    where python >nul 2>nul && set "BOOT=python"
)
if not defined BOOT (
    echo   [ERROR] Python 3 was not found on this system.
    echo.
    echo   Please install Python 3.10 or newer from:
    echo       https://www.python.org/downloads/
    echo   and tick "Add python.exe to PATH" during installation, then run this again.
    echo.
    pause
    exit /b 1
)

echo   Creating virtual environment in "%VENV%" ...
!BOOT! -m venv "%VENV%"
if errorlevel 1 (
    echo   [ERROR] Could not create the virtual environment.
    pause
    exit /b 1
)

echo   Upgrading pip ...
"%PY%" -m pip install --upgrade pip

echo.
echo   Installing dependencies. The first run can take several minutes
echo   ^(it downloads PySide6, Whisper and the CUDA libraries^). Please wait...
echo.
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo   [ERROR] Dependency installation failed - see the messages above.
    pause
    exit /b 1
)

echo.
echo   Setup complete!
echo.

REM ---------------------------------------------------------------- launch app
:launch
echo   Starting Subtitle Studio...
REM Launch with pythonw so no console window lingers behind the app.
start "" "%PYW%" run_app.py
exit /b 0
