from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from groq import Groq


AUDIO_EXTENSIONS = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".mp4", ".mov", ".mkv", ".webm")


def _download_audio(url: str, workdir: str) -> Path:
    output_template = str(Path(workdir) / "source.%(ext)s")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        output_template,
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    matches = list(Path(workdir).glob("source.*"))
    if not matches:
        raise FileNotFoundError("yt-dlp did not produce a local audio file")
    return matches[0]


def _transcribe_file(file_path: Path) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for audio transcription")

    client = Groq(api_key=api_key)
    model = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")
    with file_path.open("rb") as handle:
        transcript = client.audio.transcriptions.create(model=model, file=handle)
    return getattr(transcript, "text", "") or ""


def extract_audio(url: str) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            audio_path = _download_audio(url, tmpdir)
            transcript = _transcribe_file(audio_path)
            return {
                "ok": True,
                "source_type": "audio",
                "title": audio_path.name,
                "transcript": transcript,
                "notes": ["Downloaded media with yt-dlp.", "Transcribed with Groq Whisper API."],
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
