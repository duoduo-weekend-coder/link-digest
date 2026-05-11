from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from dotenv import load_dotenv

from extractors import (
    detect_source_type,
    extract_audio,
    extract_generic_webpage,
    extract_xiaohongshu,
    extract_youtube,
)
from summarizer import summarize_text


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class AnalyzeRequest(BaseModel):
    url: HttpUrl


load_dotenv()

app = FastAPI(title="Link Summarizer MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "groq_configured": bool(os.getenv("GROQ_API_KEY"))}


@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> StreamingResponse:
    return StreamingResponse(
        _analyze_stream(str(request.url)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _analyze_stream(url: str):
    source_type = "unknown"
    try:
        yield _sse("progress", {"step": "detecting", "message": "检测链接类型..."})
        source_type = detect_source_type(url)

        if source_type == "youtube":
            yield _sse("progress", {"step": "transcript", "message": "获取 YouTube 字幕..."})
            extracted = await asyncio.to_thread(extract_youtube, url)

            if not extracted.get("ok"):
                yield _sse("progress", {"step": "audio_download", "message": "下载并转录音频..."})
                extracted = await asyncio.to_thread(extract_audio, url)
                notes = ["Fell back to audio transcription because transcript API failed."] + list(extracted.get("notes", []))
                extracted = {**extracted, "notes": notes}
        elif source_type == "audio":
            extracted = await asyncio.to_thread(extract_audio, url)
        elif source_type == "xiaohongshu":
            extracted = await asyncio.to_thread(extract_xiaohongshu, url)
        else:
            extracted = await asyncio.to_thread(extract_generic_webpage, url)

        transcript = extracted.get("transcript")
        if not transcript:
            yield _sse("error", {
                "message": "Could not extract useful text from this link.",
                "source_type": source_type,
                "notes": extracted.get("notes", []),
            })
            return

        yield _sse("progress", {"step": "summarizing", "message": "生成摘要..."})
        summary = await asyncio.to_thread(
            summarize_text, source_type, extracted.get("title"), transcript
        )

        yield _sse("result", {
            "url": url,
            "source_type": source_type,
            "title": extracted.get("title"),
            "transcript": transcript,
            "summary": summary,
            "notes": extracted.get("notes", []),
        })
    except Exception as exc:
        yield _sse("error", {"message": str(exc), "source_type": source_type, "notes": []})
