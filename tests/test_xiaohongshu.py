from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY

import pytest
from bs4 import BeautifulSoup

from extractors.xiaohongshu import _is_video, extract_xiaohongshu


# ── helpers ──────────────────────────────────────────────────────────────────

def _mock_response(html: str) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.text = html
    return resp


VIDEO_HTML = (
    '<html><head>'
    '<meta property="og:title" content="旅游vlog" />'
    '<meta property="og:video" content="https://sns-video.xhscdn.com/v.mp4" />'
    '</head></html>'
)

IMAGE_HTML = (
    '<html><head>'
    '<meta property="og:title" content="花园日记" />'
    '<meta property="og:description" content="今天种了很多花，真开心！" />'
    '</head></html>'
)


# ── _is_video ─────────────────────────────────────────────────────────────────

def test_is_video_detects_og_video_meta():
    soup = BeautifulSoup(VIDEO_HTML, "html.parser")
    assert _is_video(soup) is True


def test_is_video_detects_html_video_tag():
    html = '<html><body><video src="foo.mp4"></video></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _is_video(soup) is True


def test_is_video_returns_false_for_image_post():
    soup = BeautifulSoup(IMAGE_HTML, "html.parser")
    assert _is_video(soup) is False


# ── extract_xiaohongshu: video path ───────────────────────────────────────────

def test_video_post_yt_dlp_success_no_cookie():
    with patch("extractors.xiaohongshu.httpx.get", return_value=_mock_response(VIDEO_HTML)), \
         patch("extractors.xiaohongshu._download_audio", return_value=Path("/tmp/s.mp3")) as mock_dl, \
         patch("extractors.xiaohongshu._transcribe_file", return_value="转录文本"):
        result = extract_xiaohongshu("https://www.xiaohongshu.com/explore/vid123")

    assert result["ok"] is True
    assert result["source_type"] == "xiaohongshu"
    assert result["transcript"] == "转录文本"
    assert any("no cookie" in n for n in result["notes"])
    mock_dl.assert_called_once_with(ANY, ANY, cookies_file=None)


def test_video_post_cookie_retry_success(monkeypatch):
    monkeypatch.setenv("XHS_COOKIES", "# Netscape HTTP Cookie File\n")

    calls: list[str | None] = []

    def _dl_side(url, workdir, cookies_file=None):
        calls.append(cookies_file)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, "yt-dlp")
        return Path(workdir) / "source.mp3"

    with patch("extractors.xiaohongshu.httpx.get", return_value=_mock_response(VIDEO_HTML)), \
         patch("extractors.xiaohongshu._download_audio", side_effect=_dl_side), \
         patch("extractors.xiaohongshu._transcribe_file", return_value="cookie转录"):
        result = extract_xiaohongshu("https://www.xiaohongshu.com/explore/vid456")

    assert result["ok"] is True
    assert len(calls) == 2
    assert calls[0] is None       # first attempt: no cookie
    assert calls[1] is not None   # second attempt: cookie file path
    assert any("XHS_COOKIES" in n for n in result["notes"])


def test_image_post_skips_yt_dlp():
    with patch("extractors.xiaohongshu.httpx.get", return_value=_mock_response(IMAGE_HTML)), \
         patch("extractors.xiaohongshu._download_audio") as mock_dl:
        result = extract_xiaohongshu("https://www.xiaohongshu.com/explore/img789")

    mock_dl.assert_not_called()
    assert result["ok"] is True
    assert any("Best-effort" in n for n in result["notes"])
