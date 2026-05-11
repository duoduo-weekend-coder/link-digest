from __future__ import annotations

import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

from groq import Groq


AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".mp4", ".mov", ".mkv", ".webm")

GROQ_MAX_BYTES = 24 * 1024 * 1024  # 24 MB safety margin (Groq Whisper limit is 25 MB)
CHUNK_SECONDS = 600  # 10 minutes per chunk


def _download_audio(url: str, workdir: str, cookies_file: str | None = None) -> Path:
    output_template = str(Path(workdir) / "source.%(ext)s")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        output_template,
    ]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    cmd.append(url)
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    matches = list(Path(workdir).glob("source.*"))
    if not matches:
        raise FileNotFoundError("yt-dlp did not produce a local audio file")
    return matches[0]


def _parse_retry_after(err: Exception) -> float:
    """Extract suggested wait time in seconds from a Groq rate-limit error."""
    m = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(err), re.IGNORECASE)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2) or 0) + 2
    return 60.0


def _call_whisper(client, model: str, path: Path) -> str:
    """Transcribe one file with automatic retry on rate-limit (429)."""
    for attempt in range(10):
        try:
            with path.open("rb") as fh:
                result = client.audio.transcriptions.create(model=model, file=fh)
            return getattr(result, "text", "") or ""
        except Exception as e:
            if "rate_limit" not in str(e).lower() and "429" not in str(e):
                raise
            if attempt == 9:
                raise
            wait = _parse_retry_after(e)
            time.sleep(wait)
    return ""


def _split_audio(file_path: Path) -> list[Path]:
    chunk_dir = file_path.parent / "chunks"
    chunk_dir.mkdir(exist_ok=True)
    pattern = str(chunk_dir / "chunk_%03d.mp3")
    subprocess.run(
        ["ffmpeg", "-i", str(file_path), "-f", "segment", "-segment_time", str(CHUNK_SECONDS), "-c", "copy", pattern, "-y"],
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(chunk_dir.glob("chunk_*.mp3"))


def _transcribe_file(file_path: Path, on_chunk=None) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for audio transcription")

    client = Groq(api_key=api_key)
    model = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")

    if file_path.stat().st_size <= GROQ_MAX_BYTES:
        text = _call_whisper(client, model, file_path)
        if on_chunk:
            on_chunk(0, 1, text)
        return text

    chunks = _split_audio(file_path)
    total = len(chunks)
    parts = []
    for idx, chunk in enumerate(chunks):
        text = _call_whisper(client, model, chunk)
        parts.append(text)
        if on_chunk:
            on_chunk(idx, total, text)
    return " ".join(parts)


def extract_audio(url: str, on_chunk=None) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            audio_path = _download_audio(url, tmpdir)

            # Wrap callback to capture total chunk count after transcription
            chunk_total: list[int] = [0]
            def _tracking(idx, total, text, _orig=on_chunk):
                chunk_total[0] = total
                if _orig:
                    _orig(idx, total, text)

            transcript = _transcribe_file(audio_path, on_chunk=_tracking)
            total_chunks = chunk_total[0]

            return {
                "ok": True,
                "source_type": "audio",
                "title": audio_path.name,
                "transcript": transcript,
                "notes": ["Downloaded media with yt-dlp.", "Transcribed with Groq Whisper API."],
                "total_chunks": total_chunks,
            }
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() if exc.stderr else str(exc)
            return {
                "ok": False,
                "source_type": "audio",
                "title": None,
                "transcript": None,
                "notes": [f"yt-dlp download failed: {detail}"],
            }
        except Exception as exc:
            return {
                "ok": False,
                "source_type": "audio",
                "title": None,
                "transcript": None,
                "notes": [str(exc)],
            }
