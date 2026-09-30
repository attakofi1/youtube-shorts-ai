# YouTube Shorts AI

AI-powered long-video to Shorts pipeline.

## Planned features

- YouTube URL or local video input
- Transcript generation with Whisper
- AI detection of high-value moments
- Batch creation of multiple clips
- 9:16 vertical reframing
- Speaker/face-aware cropping
- Animated subtitles
- Hook, title, description and hashtag generation
- Parallel FFmpeg rendering
- Download individual clips or a ZIP

## Architecture

- Next.js + TypeScript frontend
- FastAPI backend
- FFmpeg video processing
- faster-whisper transcription
- Redis/Celery job queue
- PostgreSQL metadata store
- Docker deployment

## Legal

Only process videos you own or have permission to use. The application does not bypass YouTube access controls or copyright restrictions.
