# AiPod - Podcast Translation Pipeline

Automated podcast translation web app that handles audio cleanup, transcription, translation, voice cloning, speech generation, and mastering.

## Pipeline Stages

1. **Audio Cleanup** — Auphonic (leveling, noise reduction, loudness normalization)
2. **Transcription** — HappyScribe (AI transcription with speaker diarization)
3. **Translation** — DeepL + Claude (machine translation + context-aware polishing)
4. **Human Review** — Web editor with side-by-side transcript and translation
5. **Voice Cloning** — ElevenLabs (instant voice clone per speaker)
6. **Speech Generation** — ElevenLabs TTS (segment-by-segment with cloned voices)
7. **Mix & Master** — pydub stitching + Auphonic final mastering

## Requirements

- Python 3.11+
- Redis (for Celery task queue)
- ffmpeg (for pydub audio processing)

## Setup

```bash
# Clone and enter the project
cd aipod

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your API keys

# Start Redis (macOS)
brew services start redis

# Start the web server
python run.py

# In a separate terminal, start the Celery worker
celery -A app.pipeline.worker:celery_app worker --loglevel=info
```

## API Keys Required

| Service | Purpose | Get Key |
|---------|---------|---------|
| Auphonic | Audio cleanup & mastering | https://auphonic.com |
| HappyScribe | Transcription | https://www.happyscribe.com |
| DeepL | Machine translation | https://www.deepl.com/pro-api |
| Anthropic | Translation polishing | https://console.anthropic.com |
| ElevenLabs | Voice cloning & TTS | https://elevenlabs.io |

## Usage

1. Open http://localhost:8000
2. Upload an MP3 podcast episode
3. Select source and target languages
4. Monitor progress through the 7-stage pipeline
5. Review and edit the translation when prompted
6. Download the final translated MP3

## Supported Languages

English, Spanish, French, German, Italian, Portuguese (BR), Dutch, Polish, Japanese, Korean, Chinese (Mandarin), Hindi, Arabic, Turkish, Indonesian, Swedish, Czech, Romanian, Bulgarian, Finnish, Danish, Greek, Slovak, Croatian, Ukrainian, Russian, Tamil, Filipino, Malay, Vietnamese, Hungarian, Norwegian, Kiswahili, Hausa
