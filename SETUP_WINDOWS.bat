@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title YouTube Shorts AI - Windows Setup

echo ================================================
echo   YouTube Shorts AI - Windows Setup
echo ================================================
echo.

set "ROOT=%~dp0"
cd /d "%ROOT%"

REM -----------------------------
REM Check / install Python
REM -----------------------------
where py >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Installing Python 3.12 with winget...
  winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo.
    echo Automatic Python installation failed.
    echo Install Python 3.12+ from:
    echo https://www.python.org/downloads/windows/
    pause
    exit /b 1
  )
)

set "PATH=%LocalAppData%\Programs\Python\Python312;%LocalAppData%\Programs\Python\Python312\Scripts;%PATH%"

py -3 --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo Python is installed but the Python Launcher is not available yet.
  echo Close this window, open a new Command Prompt, and run SETUP_WINDOWS.bat again.
  pause
  exit /b 1
)

REM -----------------------------
REM Find requirements file
REM -----------------------------
set "REQ=%ROOT%backend\requirements-windows.txt"

if exist "%REQ%" goto REQUIREMENTS_READY

REM Some GitHub ZIP layouts place the requirements file at the repository root.
if exist "%ROOT%requirements-windows.txt" (
  echo.
  echo Found requirements-windows.txt at the repository root.
  echo Copying it to the expected backend folder...
  if not exist "%ROOT%backend" mkdir "%ROOT%backend"
  copy /Y "%ROOT%requirements-windows.txt" "%REQ%" >nul
  if exist "%REQ%" goto REQUIREMENTS_READY
)

REM Search all project folders.
echo.
echo requirements-windows.txt was not found in the expected location:
echo %REQ%
echo.
echo Searching the project for the file...

set "FOUND_REQ="
for /r "%ROOT%" %%F in (requirements-windows.txt) do (
  if not defined FOUND_REQ set "FOUND_REQ=%%F"
)

if defined FOUND_REQ (
  echo Found it here:
  echo !FOUND_REQ!
  echo Copying it to the expected backend folder...
  if not exist "%ROOT%backend" mkdir "%ROOT%backend"
  copy /Y "!FOUND_REQ!" "%REQ%" >nul
  if exist "%REQ%" goto REQUIREMENTS_READY
)

REM Last resort: download the official file directly.
echo.
echo The requirements file is missing locally.
echo Downloading the official project copy...
if not exist "%ROOT%backend" mkdir "%ROOT%backend"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/attakofi1/youtube-shorts-ai/main/backend/requirements-windows.txt' -OutFile '%REQ%' -ErrorAction Stop } catch { exit 1 }"

if not exist "%REQ%" (
  echo.
  echo Could not obtain requirements-windows.txt automatically.
  echo Please download the complete repository ZIP from:
  echo https://github.com/attakofi1/youtube-shorts-ai
  pause
  exit /b 1
)

:REQUIREMENTS_READY
echo.
echo Requirements file ready:
echo %REQ%

REM -----------------------------
REM Check / install Node.js
REM -----------------------------
where node >nul 2>&1
if errorlevel 1 (
  echo.
  echo Node.js was not found. Installing Node.js LTS with winget...
  winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo Automatic Node.js installation failed.
    echo Install Node.js LTS manually from https://nodejs.org/
    pause
    exit /b 1
  )
  set "PATH=%ProgramFiles%\nodejs;%PATH%"
)

REM -----------------------------
REM Check / install FFmpeg
REM -----------------------------
where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo.
  echo FFmpeg was not found. Installing FFmpeg with winget...
  winget install --id Gyan.FFmpeg.Shared -e --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo Automatic FFmpeg installation failed.
    echo Install FFmpeg manually and ensure ffmpeg.exe is on PATH.
    pause
    exit /b 1
  )
  set "PATH=%ProgramFiles%\ffmpeg\bin;%PATH%"
)

REM -----------------------------
REM Create Python environment
REM -----------------------------
if not exist "%ROOT%.venv\Scripts\python.exe" (
  echo.
  echo Creating Python virtual environment...
  py -3 -m venv "%ROOT%.venv"
  if errorlevel 1 (
    echo Could not create the Python environment.
    pause
    exit /b 1
  )
)

call "%ROOT%.venv\Scripts\activate.bat"
if errorlevel 1 (
  echo Could not activate the Python environment.
  pause
  exit /b 1
)

echo.
echo Installing Python dependencies...
python -m pip install --upgrade pip
python -m pip install -r "%REQ%"
if errorlevel 1 (
  echo.
  echo Python dependency installation failed.
  echo The requirements file used was:
  echo %REQ%
  pause
  exit /b 1
)

REM -----------------------------
REM Install frontend dependencies
REM -----------------------------
if not exist "%ROOT%frontend\package.json" (
  echo.
  echo frontend\package.json was not found.
  echo Your repository download appears incomplete.
  pause
  exit /b 1
)

if not exist "%ROOT%frontend\node_modules" (
  echo.
  echo Installing frontend dependencies...
  cd /d "%ROOT%frontend"
  call npm install
  if errorlevel 1 (
    echo Frontend dependency installation failed.
    cd /d "%ROOT%"
    pause
    exit /b 1
  )
  cd /d "%ROOT%"
)

if not exist "%ROOT%storage" mkdir "%ROOT%storage"
if not exist "%ROOT%assets" mkdir "%ROOT%assets"
if not exist "%ROOT%.env" if exist "%ROOT%.env.example" copy "%ROOT%.env.example" "%ROOT%.env" >nul

echo.
echo ================================================
echo   Setup complete!
echo ================================================
echo.
echo Double-click START_WINDOWS.bat to run the app.
echo.
pause
