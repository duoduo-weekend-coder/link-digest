from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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


class AnalyzeRequest(BaseModel):
    url: HttpUrl


load_dotenv()

app = FastAPI(title="Link Summarizer MVP")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
    return {"ok": True, "openai_configured": bool(os.getenv("OPENAI_API_KEY"))}


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    url = str(request.url)
    source_type = detect_source_type(url)

    if source_type == "youtube":
        extracted = extract_youtube(url)
        if not extracted.get("ok"):
            extracted = extract_audio(url)
            extracted.setdefault("notes", []).insert(0, "Fell back to audio transcription because transcript API failed.")
    elif source_type == "audio":
        extracted = extract_audio(url)
    elif source_type == "xiaohongshu":
        extracted = extract_xiaohongshu(url)
    else:
        extracted = extract_generic_webpage(url)

    transcript = extracted.get("transcript")
    if not transcript:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Could not extract useful text from this link.",
                "source_type": source_type,
                "notes": extracted.get("notes", []),
            },
        )

    summary = summarize_text(source_type, extracted.get("title"), transcript)
    return {
        "url": url,
        "source_type": source_type,
        "title": extracted.get("title"),
        "transcript": transcript,
        "summary": summary,
        "notes": extracted.get("notes", []),
    }
