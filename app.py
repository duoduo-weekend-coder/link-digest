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
from summarizer import restore_punctuation, summarize_text


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _fmt_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


SUMMARY_CHAR_LIMIT = 20000  # must match summarizer.py truncation


def _coverage_note(transcript: str, total_chunks: int) -> str | None:
    """Return a note about summary coverage when the transcript was truncated."""
    if total_chunks <= 1 or len(transcript) <= SUMMARY_CHAR_LIMIT:
        return None
    from extractors.audio import CHUNK_SECONDS  # avoid circular at module level
    total_secs = total_chunks * CHUNK_SECONDS
    covered_secs = int(total_secs * SUMMARY_CHAR_LIMIT / len(transcript))
    return (
        f"摘要仅基于前 {_fmt_duration(covered_secs)} 的内容"
        f"（视频总时长约 {_fmt_duration(total_secs)}）。"
    )


async def _drain_until_none(queue: asyncio.Queue):
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


async def _run_extract_audio(url: str, cb, queue: asyncio.Queue) -> dict:
    result = await asyncio.to_thread(extract_audio, url, cb)
    queue.put_nowait(None)  # sentinel
    return result


async def _run_extract_xiaohongshu(url: str, cb, queue: asyncio.Queue) -> dict:
    result = await asyncio.to_thread(extract_xiaohongshu, url, cb)
    queue.put_nowait(None)  # sentinel
    return result


class AnalyzeRequest(BaseModel):
    url: HttpUrl


load_dotenv()

app = FastAPI(title="Link Digest")
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
                loop = asyncio.get_running_loop()
                q: asyncio.Queue = asyncio.Queue()
                def _cb_yt(idx, total, text, _q=q, _loop=loop):
                    _loop.call_soon_threadsafe(_q.put_nowait, {"chunk_index": idx, "total": total, "text": text})
                task = asyncio.create_task(_run_extract_audio(url, _cb_yt, q))
                async for chunk_data in _drain_until_none(q):
                    yield _sse("transcript_chunk", chunk_data)
                extracted = await task
                notes = ["Fell back to audio transcription because transcript API failed."] + list(extracted.get("notes", []))
                extracted = {**extracted, "notes": notes}
        elif source_type == "audio":
            yield _sse("progress", {"step": "audio_download", "message": "下载并转录音频..."})
            loop = asyncio.get_running_loop()
            q2: asyncio.Queue = asyncio.Queue()
            def _cb_audio(idx, total, text, _q=q2, _loop=loop):
                _loop.call_soon_threadsafe(_q.put_nowait, {"chunk_index": idx, "total": total, "text": text})
            task2 = asyncio.create_task(_run_extract_audio(url, _cb_audio, q2))
            async for chunk_data in _drain_until_none(q2):
                yield _sse("transcript_chunk", chunk_data)
            extracted = await task2
        elif source_type == "xiaohongshu":
            yield _sse("progress", {"step": "extracting", "message": "提取小红书内容..."})
            loop = asyncio.get_running_loop()
            q_xhs: asyncio.Queue = asyncio.Queue()
            def _cb_xhs(idx, total, text, _q=q_xhs, _loop=loop):
                _loop.call_soon_threadsafe(_q.put_nowait, {"chunk_index": idx, "total": total, "text": text})
            task_xhs = asyncio.create_task(_run_extract_xiaohongshu(url, _cb_xhs, q_xhs))
            async for chunk_data in _drain_until_none(q_xhs):
                yield _sse("transcript_chunk", chunk_data)
            extracted = await task_xhs
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

        total_chunks = extracted.get("total_chunks", 0)
        note = _coverage_note(transcript, total_chunks)
        notes = list(extracted.get("notes", []))
        if note:
            notes.append(note)

        yield _sse("progress", {"step": "summarizing", "message": "Generating summary…"})
        transcript, summary = await asyncio.gather(
            asyncio.to_thread(restore_punctuation, transcript),
            asyncio.to_thread(summarize_text, source_type, extracted.get("title"), transcript),
        )

        yield _sse("result", {
            "url": url,
            "source_type": source_type,
            "title": extracted.get("title"),
            "transcript": transcript,
            "summary": summary,
            "notes": notes,
        })
    except Exception as exc:
        yield _sse("error", {"message": str(exc), "source_type": source_type, "notes": []})
