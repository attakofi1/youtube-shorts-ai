@echo off
setlocal
cd /d "%~dp0"
title YouTube Shorts AI

if not exist ".venv\Scripts\python.exe" (
  echo First run detected. Running setup...
  call SETUP_WINDOWS.bat
  if errorlevel 1 exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
  echo Node.js is missing. Run SETUP_WINDOWS.bat first.
  pause
  exit /b 1
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo FFmpeg is missing. Run SETUP_WINDOWS.bat first.
  pause
  exit /b 1
)

if not exist "storage" mkdir storage
if not exist "assets" mkdir assets
if not exist ".env" if exist ".env.example" copy .env.example .env >nul

call ".venv\Scripts\activate.bat"
start "YouTube Shorts AI Backend" cmd /k "cd /d "%~dp0" && call .venv\Scripts\activate.bat && set SHORTS_STORAGE=%~dp0storage && set BACKGROUND_MUSIC_PATH=%~dp0assets\background.mp3 && uvicorn backend.app.windows_main:app --host 127.0.0.1 --port 8000"

cd frontend
start "YouTube Shorts AI Frontend" cmd /k "cd /d "%~dp0frontend" && set NEXT_PUBLIC_API_URL=http://localhost:8000 && npm run dev"
cd ..

timeout /t 5 /nobreak >nul
start "" http://localhost:3000

echo.
echo YouTube Shorts AI is starting.
echo Browser: http://localhost:3000
 echo Close the two command windows to stop the app.
