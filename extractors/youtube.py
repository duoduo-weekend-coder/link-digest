from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi


def _video_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.strip("/") or None
    qs = parse_qs(parsed.query)
    return qs.get("v", [None])[0]


def extract_youtube(url: str) -> dict:
    video_id = _video_id(url)
    if not video_id:
        return {
            "ok": False,
            "source_type": "youtube",
            "title": None,
            "transcript": None,
            "notes": ["Could not parse YouTube video id."],
        }

    try:
        rows = YouTubeTranscriptApi.get_transcript(video_id)
        transcript = " ".join(row["text"].strip() for row in rows if row.get("text"))
        return {
            "ok": True,
            "source_type": "youtube",
            "title": None,
            "transcript": transcript,
            "notes": ["Used YouTube transcript when available."],
        }
    except Exception as exc:
        return {
            "ok": False,
            "source_type": "youtube",
            "title": None,
            "transcript": None,
            "notes": [
                "No public YouTube transcript was available.",
                f"Transcript API error: {exc}",
            ],
        }
