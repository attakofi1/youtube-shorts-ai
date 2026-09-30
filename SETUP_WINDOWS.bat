@echo off
setlocal
cd /d "%~dp0"
title YouTube Shorts AI - Windows Setup

echo ================================================
echo   YouTube Shorts AI - Windows Setup
 echo ================================================

where py >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Install Python 3.11+ from https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
  echo Node.js was not found. Installing Node.js LTS with winget...
  winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo Automatic Node.js installation failed. Install Node.js LTS manually from https://nodejs.org/
    pause
    exit /b 1
  )
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo FFmpeg was not found. Installing FFmpeg with winget...
  winget install --id Gyan.FFmpeg.Shared -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo Automatic FFmpeg installation failed. Install FFmpeg manually and ensure ffmpeg.exe is on PATH.
    pause
    exit /b 1
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo Could not create the Python environment.
    pause
    exit /b 1
  )
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r backend\requirements-windows.txt
if errorlevel 1 (
  echo Python dependency installation failed.
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Installing frontend dependencies...
  cd frontend
  call npm install
  cd ..
)

if not exist "storage" mkdir storage
if not exist "assets" mkdir assets
if not exist ".env" copy .env.example .env >nul

echo.
echo Setup complete. Double-click START_WINDOWS.bat to run the app.
echo.
pause
