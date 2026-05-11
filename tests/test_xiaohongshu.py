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
