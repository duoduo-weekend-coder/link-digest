# Link Summarizer MVP

A small local web app that accepts a link, extracts text or transcript when possible, and turns it into readable notes.

## Day-1 scope
- ✅ YouTube links
  - First tries public subtitles via `youtube-transcript-api`
  - Falls back to audio download + transcription when needed
- ✅ Podcast / audio links
  - Downloads media with `yt-dlp`
  - Transcribes with OpenAI audio transcription API
- ✅ Xiaohongshu links
  - Best-effort public page text extraction only
  - Does **not** promise reliable video/audio transcription for Xiaohongshu
- ⚠️ Generic webpages
  - Basic article/body extraction as a bonus path

## Honest limits
This is **not** truly “any link”. It currently works best for:
- public YouTube videos
- public audio/video URLs that `yt-dlp` can download
- public Xiaohongshu pages with readable metadata/text
- normal public webpages

It may fail on:
- private or login-only content
- DRM-protected streams
- heavily scripted pages
- links blocked by anti-bot rules
- very large media files that exceed API or local limits

## Stack
- FastAPI backend
- tiny static HTML frontend
- `youtube-transcript-api` for YouTube subtitles
- `yt-dlp` for media download
- OpenAI API for transcription + summarization

## Setup
```bash
cd link-summarizer
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set env vars in `.env`:
```bash
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
WHISPER_MODEL=gpt-4o-mini-transcribe
PORT=8000
```

## Run
```bash
cd link-summarizer
source .venv/bin/activate
uvicorn app:app --reload --port ${PORT:-8000}
```

Open:
- http://127.0.0.1:8000

## API
### POST `/analyze`
```json
{
  "url": "https://www.youtube.com/watch?v=..."
}
```

Returns:
- `source_type`
- `title`
- `transcript`
- `summary`
- `notes`

## File map
- `app.py` — FastAPI app and routing
- `summarizer.py` — LLM summarization
- `extractors/router.py` — source detection
- `extractors/youtube.py` — YouTube transcript path
- `extractors/audio.py` — audio/video download + transcription path
- `extractors/xiaohongshu.py` — conservative Xiaohongshu extraction
- `extractors/generic.py` — basic webpage extraction
- `static/index.html` — simple UI

## Next obvious upgrades
1. Add queue/progress UI for long transcriptions
2. Add PDF support
3. Store history/results
4. Add URL adapters per platform instead of generic scraping
5. Add chunking for long transcripts before summarization
