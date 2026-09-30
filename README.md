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


## Run it on Windows 11

1. Install Docker Desktop.
2. Clone this repository.
3. Copy `.env.example` to `.env`.
4. Add your OpenAI API key to `.env` if you want LLM-powered clip selection. The app still works with local ranking without a key.
5. Start everything:

```bash
docker compose up --build
```

6. Open `http://localhost:3000`.
7. Paste a YouTube URL, choose the number and duration of Shorts, and click Generate Shorts.

The API runs on `http://localhost:8000`.

### Processing pipeline

YouTube download → Whisper transcription → local candidate ranking → optional OpenAI semantic selection → face detection → vertical 1080×1920 crop → word-timed captions → parallel FFmpeg rendering → MP4 downloads.

The LLM stage uses the OpenAI Responses API when `OPENAI_API_KEY` is configured, with GPT-5.6 Luna as the default clip-selection model. OpenAI documents GPT-5.6 Luna as a cost-sensitive, high-volume model available through the Responses API. citeturn0search0

Only process videos you own or have permission to use.
