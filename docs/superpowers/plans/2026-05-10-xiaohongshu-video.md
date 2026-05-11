# 小红书视频支持 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add video detection and audio transcription to the 小红书 extractor, with optional XHS_COOKIES cookie retry and SSE progress streaming.

**Architecture:** `_download_audio` in `audio.py` gains an optional `cookies_file` parameter. `xiaohongshu.py` is refactored with `_is_video` detection, `_extract_from_soup` for text parsing, and `_try_video_extract` for the two-attempt yt-dlp path. `app.py` upgrades the xiaohongshu branch to the SSE+queue pattern already used for YouTube audio fallback.

**Tech Stack:** httpx, BeautifulSoup4, yt-dlp (subprocess), Groq Whisper, FastAPI SSE, pytest + unittest.mock

---

## File Map

| File | Change |
|------|--------|
| `extractors/audio.py` | Add `cookies_file: str \| None = None` param to `_download_audio` |
| `extractors/xiaohongshu.py` | Full rewrite: add `_is_video`, `_extract_from_soup`, `_try_video_extract`, update `extract_xiaohongshu` signature |
| `app.py` | Add `_run_extract_xiaohongshu`, upgrade xiaohongshu branch to SSE+queue |
| `tests/test_xiaohongshu.py` | Create with 6 focused tests |
| `tests/test_app.py` | Add xiaohongshu integration test |

---

### Task 1: Extend `_download_audio` to support a cookies file

**Files:**
- Modify: `extractors/audio.py:19-34`
- Test: `tests/test_audio.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_audio.py`:

```python
def test_download_audio_passes_cookies_flag_to_yt_dlp(tmp_path):
    cookies_file = str(tmp_path / "cookies.txt")
    (tmp_path / "cookies.txt").write_text("# Netscape HTTP Cookie File\n")
    (tmp_path / "source.mp3").touch()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        _download_audio("https://example.com/video", str(tmp_path), cookies_file=cookies_file)

    args = mock_run.call_args[0][0]
    assert "--cookies" in args
    idx = args.index("--cookies")
    assert args[idx + 1] == cookies_file


def test_download_audio_no_cookies_flag_when_none(tmp_path):
    (tmp_path / "source.mp3").touch()

    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        _download_audio("https://example.com/video", str(tmp_path), cookies_file=None)

    args = mock_run.call_args[0][0]
    assert "--cookies" not in args
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/minidreamer/workplace/link-summarizer && .venv/bin/pytest tests/test_audio.py::test_download_audio_passes_cookies_flag_to_yt_dlp tests/test_audio.py::test_download_audio_no_cookies_flag_when_none -v
```

Expected: FAIL — `_download_audio() got an unexpected keyword argument 'cookies_file'`

- [ ] **Step 3: Add `cookies_file` parameter to `_download_audio`**

In `extractors/audio.py`, replace lines 19–34:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_audio.py::test_download_audio_passes_cookies_flag_to_yt_dlp tests/test_audio.py::test_download_audio_no_cookies_flag_when_none -v
```

Expected: PASS (2 passed)

- [ ] **Step 5: Run full test suite for regressions**

```bash
.venv/bin/pytest --tb=short -q
```

Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add extractors/audio.py tests/test_audio.py
git commit -m "feat: add cookies_file param to _download_audio"
```

---

### Task 2: Add `_is_video` detection to `xiaohongshu.py`

**Files:**
- Modify: `extractors/xiaohongshu.py`
- Create: `tests/test_xiaohongshu.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_xiaohongshu.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_xiaohongshu.py -v
```

Expected: FAIL — `cannot import name '_is_video' from 'extractors.xiaohongshu'`

- [ ] **Step 3: Add `_is_video` to `xiaohongshu.py`**

Add this function after the `_clean` function in `extractors/xiaohongshu.py` (after line 10):

```python
def _is_video(soup: BeautifulSoup) -> bool:
    if soup.find("meta", property="og:video"):
        return True
    if soup.find("video"):
        return True
    return False
```

Also add the missing import at the top of the file (it already imports BeautifulSoup so just verify it's there):

```python
from bs4 import BeautifulSoup
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_xiaohongshu.py -v
```

Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add extractors/xiaohongshu.py tests/test_xiaohongshu.py
git commit -m "feat: add _is_video detection for xiaohongshu posts"
```

---

### Task 3: Implement full video path in `extract_xiaohongshu`

**Files:**
- Modify: `extractors/xiaohongshu.py` (full rewrite)
- Modify: `tests/test_xiaohongshu.py` (add 3 tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_xiaohongshu.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_xiaohongshu.py::test_video_post_yt_dlp_success_no_cookie tests/test_xiaohongshu.py::test_video_post_cookie_retry_success tests/test_xiaohongshu.py::test_image_post_skips_yt_dlp -v
```

Expected: FAIL — various errors (import errors, wrong signature, etc.)

- [ ] **Step 3: Rewrite `extractors/xiaohongshu.py`**

Replace the entire file with:

```python
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from extractors.audio import _download_audio, _transcribe_file

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_video(soup: BeautifulSoup) -> bool:
    if soup.find("meta", property="og:video"):
        return True
    if soup.find("video"):
        return True
    return False


def _extract_from_soup(soup: BeautifulSoup) -> dict:
    title = None
    description = None

    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    if og_title and og_title.get("content"):
        title = _clean(og_title["content"])
    if og_desc and og_desc.get("content"):
        description = _clean(og_desc["content"])

    if not title:
        title_tag = soup.find("title")
        if title_tag and title_tag.text:
            title = _clean(title_tag.text)

    text_candidates = []
    for tag in soup.find_all(["meta", "p", "span"]):
        if tag.name == "meta" and tag.get("name") in {"description", "keywords"}:
            content = tag.get("content")
            if content:
                text_candidates.append(_clean(content))
        elif tag.text:
            text = _clean(tag.text)
            if 30 <= len(text) <= 500:
                text_candidates.append(text)

    deduped = []
    seen: set[str] = set()
    for item in text_candidates:
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)

    transcript = description or "\n".join(deduped[:10])
    if not transcript:
        return {
            "ok": False,
            "source_type": "xiaohongshu",
            "title": title,
            "transcript": None,
            "notes": ["Could not extract useful public text from Xiaohongshu."],
        }

    return {
        "ok": True,
        "source_type": "xiaohongshu",
        "title": title,
        "transcript": transcript,
        "notes": ["Best-effort public-page text extraction only."],
    }


def _try_video_extract(url: str, on_chunk) -> dict | None:
    """Two-attempt yt-dlp download. Returns result dict on success, None if both attempts fail."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Attempt 1: no cookie
        try:
            audio_path = _download_audio(url, tmpdir, cookies_file=None)
            transcript = _transcribe_file(audio_path, on_chunk=on_chunk)
            return {
                "ok": True,
                "source_type": "xiaohongshu",
                "title": None,
                "transcript": transcript,
                "notes": ["Downloaded video audio with yt-dlp (no cookie)."],
            }
        except subprocess.CalledProcessError:
            pass

        # Attempt 2: with XHS_COOKIES if available
        cookie_str = os.getenv("XHS_COOKIES")
        if not cookie_str:
            return None

        cookies_file: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as cf:
                cf.write(cookie_str)
                cookies_file = cf.name
            audio_path = _download_audio(url, tmpdir, cookies_file=cookies_file)
            transcript = _transcribe_file(audio_path, on_chunk=on_chunk)
            return {
                "ok": True,
                "source_type": "xiaohongshu",
                "title": None,
                "transcript": transcript,
                "notes": ["Downloaded video audio with yt-dlp (XHS_COOKIES used)."],
            }
        except Exception:
            return None
        finally:
            if cookies_file:
                os.unlink(cookies_file)


def extract_xiaohongshu(url: str, on_chunk=None) -> dict:
    try:
        response = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        return {
            "ok": False,
            "source_type": "xiaohongshu",
            "title": None,
            "transcript": None,
            "notes": [f"Request failed: {exc}", "Likely blocked by login, anti-bot, or unavailable page."],
        }

    soup = BeautifulSoup(response.text, "html.parser")

    if _is_video(soup):
        result = _try_video_extract(url, on_chunk)
        if result:
            return result
        text_result = _extract_from_soup(soup)
        text_result["notes"] = ["yt-dlp failed, fell back to text extraction."] + text_result.get("notes", [])
        return text_result

    return _extract_from_soup(soup)
```

- [ ] **Step 4: Run all xiaohongshu tests to verify they pass**

```bash
.venv/bin/pytest tests/test_xiaohongshu.py -v
```

Expected: PASS (6 passed)

- [ ] **Step 5: Run full test suite for regressions**

```bash
.venv/bin/pytest --tb=short -q
```

Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```bash
git add extractors/xiaohongshu.py tests/test_xiaohongshu.py
git commit -m "feat: add video detection and audio extraction to xiaohongshu extractor"
```

---

### Task 4: Upgrade `app.py` xiaohongshu branch to SSE+queue mode

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
@pytest.mark.asyncio
async def test_analyze_xiaohongshu_streams_progress_then_result():
    mock_extracted = {
        "ok": True,
        "source_type": "xiaohongshu",
        "title": "旅游vlog",
        "transcript": "今天去了一个很美的地方",
        "notes": ["Downloaded video audio with yt-dlp (no cookie)."],
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        with (
            patch("app.extract_xiaohongshu", return_value=mock_extracted),
            patch("app.summarize_text", return_value="美丽的旅行摘要。"),
        ):
            resp = await client.post(
                "/analyze", json={"url": "https://www.xiaohongshu.com/explore/abc123"}
            )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    progress_steps = [e["data"]["step"] for e in events if e["event"] == "progress"]
    assert "detecting" in progress_steps
    assert "summarizing" in progress_steps
    result_events = [e for e in events if e["event"] == "result"]
    assert len(result_events) == 1
    assert result_events[0]["data"]["summary"] == "美丽的旅行摘要。"
    assert result_events[0]["data"]["source_type"] == "xiaohongshu"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/pytest tests/test_app.py::test_analyze_xiaohongshu_streams_progress_then_result -v
```

Expected: FAIL — test passes or SSE structure doesn't match (current simple branch doesn't send `extracting` progress step)

- [ ] **Step 3: Update `app.py`**

Add `_run_extract_xiaohongshu` after `_run_extract_audio` (around line 63):

```python
async def _run_extract_xiaohongshu(url: str, cb, queue: asyncio.Queue) -> dict:
    result = await asyncio.to_thread(extract_xiaohongshu, url, cb)
    queue.put_nowait(None)  # sentinel
    return result
```

Replace the `elif source_type == "xiaohongshu":` branch (currently lines 134–135) with:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
.venv/bin/pytest tests/test_app.py::test_analyze_xiaohongshu_streams_progress_then_result -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/pytest --tb=short -q
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: upgrade xiaohongshu app branch to SSE+queue with on_chunk support"
```

---

## Self-Review

**Spec coverage:**
- ✅ Video detection via `og:video` / `<video>` tag → `_is_video`
- ✅ yt-dlp download, no cookie first attempt → `_try_video_extract` attempt 1
- ✅ XHS_COOKIES retry on failure → `_try_video_extract` attempt 2
- ✅ Fallback to text extraction → `_extract_from_soup(soup)` after `_try_video_extract` returns None
- ✅ SSE progress streaming → Task 4
- ✅ Notes field per scenario → in each return dict
- ✅ Image post skips yt-dlp → Task 3 test

**Placeholder scan:** None found. All steps contain full code.

**Type consistency:**
- `_download_audio(url: str, workdir: str, cookies_file: str | None = None)` — consistent across Task 1 and Task 3 usage
- `_transcribe_file(audio_path, on_chunk=on_chunk)` — consistent with existing `audio.py` signature
- `extract_xiaohongshu(url: str, on_chunk=None)` — consistent between Task 3 implementation and Task 4 `app.py` call via `asyncio.to_thread(extract_xiaohongshu, url, cb)`
