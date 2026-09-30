# YouTube Shorts AI

AI-powered long-video to Shorts pipeline.

## Windows one-click mode

Docker is not required for the Windows-native mode.

1. Install Python 3.11 or newer.
2. Install Git.
3. Clone this repository.
4. Double-click `SETUP_WINDOWS.bat` once. It installs Node.js and FFmpeg through Windows Package Manager when available, creates the Python environment, and installs the required packages.
5. Double-click `START_WINDOWS.bat`.
6. The browser opens at `http://localhost:3000`.

After setup, `START_WINDOWS.bat` is the normal one-click launcher. It starts a local FastAPI worker and the Next.js dashboard without Docker, Redis, Celery, or PostgreSQL.

Optional OpenAI configuration goes in `.env` as `OPENAI_API_KEY=...`. Without a key, local clip ranking and fallback metadata generation are used.

Optional music goes in `assets/background.mp3`. Only use music you have permission to use.

## Features

- YouTube URL or local video input
- Whisper transcription
- AI detection of high-value moments
- Batch creation of multiple clips
- 9:16 vertical reframing
- Smoothed face-aware cropping
- Bold, clean, and karaoke captions
- Optional silence trimming
- Optional background music
- AI title, description and hashtag generation
- Automatic thumbnails
- Parallel FFmpeg rendering
- Individual MP4 downloads and ZIP download

## Architecture

- Next.js + TypeScript frontend
- FastAPI backend
- FFmpeg video processing
- faster-whisper transcription
- Local Windows ThreadPoolExecutor in one-click mode
- Optional OpenAI Responses API
- Docker/Celery/Redis/PostgreSQL remain available for server deployment

## Legal

Only process videos you own or have permission to use. The application does not bypass YouTube access controls or copyright restrictions.
