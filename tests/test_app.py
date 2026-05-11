from __future__ import annotations

import json

import pytest
import httpx
from unittest.mock import patch

from app import app, _sse


def test_sse_formats_progress_event():
    msg = _sse("progress", {"step": "detecting", "message": "检测链接类型..."})
    assert msg.startswith("event: progress\n")
    assert '"step": "detecting"' in msg
    assert msg.endswith("\n\n")


def test_sse_formats_result_event():
    msg = _sse("result", {"url": "https://example.com", "summary": "ok"})
    lines = msg.rstrip("\n").split("\n")
    assert lines[0] == "event: result"
    assert lines[1].startswith("data: ")
    data = json.loads(lines[1][6:])
    assert data["url"] == "https://example.com"
    assert msg.endswith("\n\n")


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_type = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type and data is not None:
            events.append({"event": event_type, "data": data})
    return events


@pytest.mark.asyncio
async def test_analyze_youtube_happy_path_streams_progress_then_result():
    mock_extracted = {
        "ok": True,
        "source_type": "youtube",
        "title": "Test Video",
        "transcript": "hello world this is a test",
        "notes": ["Used YouTube transcript when available."],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        with (
            patch("app.extract_youtube", return_value=mock_extracted),
            patch("app.summarize_text", return_value="A short summary."),
        ):
            resp = await client.post(
                "/analyze", json={"url": "https://www.youtube.com/watch?v=abc1234567"}
            )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = _parse_sse(resp.text)
    progress_steps = [e["data"]["step"] for e in events if e["event"] == "progress"]
    assert "detecting" in progress_steps
    assert "transcript" in progress_steps
    assert "summarizing" in progress_steps
    result_events = [e for e in events if e["event"] == "result"]
    assert len(result_events) == 1
    assert result_events[0]["data"]["summary"] == "A short summary."
    assert result_events[0]["data"]["title"] == "Test Video"


@pytest.mark.asyncio
async def test_analyze_youtube_fallback_to_audio_streams_audio_download_step():
    mock_youtube_fail = {
        "ok": False,
        "source_type": "youtube",
        "title": None,
        "transcript": None,
        "notes": ["No public YouTube transcript was available."],
    }
    mock_audio_ok = {
        "ok": True,
        "source_type": "audio",
        "title": "source.mp3",
        "transcript": "audio transcription text",
        "notes": ["Downloaded media with yt-dlp."],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        with (
            patch("app.extract_youtube", return_value=mock_youtube_fail),
            patch("app.extract_audio", return_value=mock_audio_ok),
            patch("app.summarize_text", return_value="Audio summary."),
        ):
            resp = await client.post(
                "/analyze", json={"url": "https://www.youtube.com/watch?v=abc1234567"}
            )
    events = _parse_sse(resp.text)
    progress_steps = [e["data"]["step"] for e in events if e["event"] == "progress"]
    assert "audio_download" in progress_steps
    result_events = [e for e in events if e["event"] == "result"]
    assert len(result_events) == 1


@pytest.mark.asyncio
async def test_analyze_returns_error_event_when_no_transcript():
    mock_fail = {
        "ok": False,
        "source_type": "youtube",
        "title": None,
        "transcript": None,
        "notes": ["No transcript available."],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        with (
            patch("app.extract_youtube", return_value=mock_fail),
            patch("app.extract_audio", return_value=mock_fail),
        ):
            resp = await client.post(
                "/analyze", json={"url": "https://www.youtube.com/watch?v=abc1234567"}
            )
    events = _parse_sse(resp.text)
    error_events = [e for e in events if e["event"] == "error"]
    assert len(error_events) == 1
    assert "notes" in error_events[0]["data"]
