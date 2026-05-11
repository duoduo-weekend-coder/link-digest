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
