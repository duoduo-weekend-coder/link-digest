# SSE Progress Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `/analyze` from a plain JSON endpoint to an SSE stream so the frontend can show a real-time progress bar while YouTube transcription and summarization run.

**Architecture:** `POST /analyze` returns a `StreamingResponse` wrapping an async generator `_analyze_stream()`. The generator yields SSE `progress` events at each pipeline step, then a final `result` or `error` event. All blocking extractor/OpenAI calls are wrapped in `asyncio.to_thread`. The frontend reads the stream with `fetch` + `ReadableStream` and advances a CSS progress bar on each `progress` event.

**Tech Stack:** FastAPI `StreamingResponse`, `asyncio.to_thread`, vanilla JS `ReadableStream`, pytest + pytest-asyncio + httpx for tests.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app.py` | Modify | Add `_sse()` helper, convert `analyze()` to SSE, add `_analyze_stream()` generator |
| `static/index.html` | Modify | Add progress bar HTML/CSS, replace fetch with streaming reader |
| `tests/__init__.py` | Create | Make tests a package |
| `tests/test_app.py` | Create | Unit test `_sse()`, integration test the streaming endpoint |

Extractors are **not touched** — they remain synchronous and are called via `asyncio.to_thread`.

---

## Task 1: Install test dependencies and scaffold test directory

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_app.py` (skeleton only)

- [ ] **Step 1: Install pytest and pytest-asyncio**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pip install pytest pytest-asyncio
```

Expected: both packages install cleanly.

- [ ] **Step 2: Create test package**

Create `tests/__init__.py` (empty file).

- [ ] **Step 3: Create test skeleton**

Create `tests/test_app.py`:

```python
from __future__ import annotations

import json

import pytest
import httpx
from unittest.mock import patch

from app import app, _sse
```

- [ ] **Step 4: Verify import works**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
python -c "from app import app"
```

Expected: no error (before `_sse` exists this will fail — that's fine, it confirms we need to add it).

- [ ] **Step 5: Commit scaffold**

```bash
git add tests/
git commit -m "test: scaffold test package"
```

---

## Task 2: Add `_sse()` helper to app.py with TDD

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing test for `_sse()`**

Append to `tests/test_app.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pytest tests/test_app.py::test_sse_formats_progress_event tests/test_app.py::test_sse_formats_result_event -v
```

Expected: `ImportError: cannot import name '_sse' from 'app'`

- [ ] **Step 3: Add imports and `_sse()` to app.py**

At the top of `app.py`, add `asyncio` and `json` to the existing imports block:

```python
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
```

Add the `_sse()` helper after the imports, before `class AnalyzeRequest`:

```python
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

Also update the `StreamingResponse` import line (currently only `FileResponse` is imported):

```python
from fastapi.responses import FileResponse, StreamingResponse
```

- [ ] **Step 4: Run tests — expect pass**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pytest tests/test_app.py::test_sse_formats_progress_event tests/test_app.py::test_sse_formats_result_event -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add _sse() helper and test"
```

---

## Task 3: Convert `/analyze` to SSE streaming endpoint

**Files:**
- Modify: `app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing integration test**

Append to `tests/test_app.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pytest tests/test_app.py -k "streams" -v
```

Expected: FAIL — `/analyze` still returns plain JSON, not SSE.

- [ ] **Step 3: Replace `analyze()` with SSE streaming version in app.py**

Replace the entire `analyze` function (lines ~52-88) with:

```python
@app.post("/analyze")
async def analyze(request: AnalyzeRequest) -> StreamingResponse:
    return StreamingResponse(
        _analyze_stream(str(request.url)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _analyze_stream(url: str):
    try:
        yield _sse("progress", {"step": "detecting", "message": "检测链接类型..."})
        source_type = detect_source_type(url)

        if source_type == "youtube":
            yield _sse("progress", {"step": "transcript", "message": "获取 YouTube 字幕..."})
            extracted = await asyncio.to_thread(extract_youtube, url)

            if not extracted.get("ok"):
                yield _sse("progress", {"step": "audio_download", "message": "下载并转录音频..."})
                extracted = await asyncio.to_thread(extract_audio, url)
                extracted.setdefault("notes", []).insert(
                    0, "Fell back to audio transcription because transcript API failed."
                )
        elif source_type == "audio":
            extracted = await asyncio.to_thread(extract_audio, url)
        elif source_type == "xiaohongshu":
            extracted = await asyncio.to_thread(extract_xiaohongshu, url)
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

        yield _sse("progress", {"step": "summarizing", "message": "生成摘要..."})
        summary = await asyncio.to_thread(
            summarize_text, source_type, extracted.get("title"), transcript
        )

        yield _sse("result", {
            "url": url,
            "source_type": source_type,
            "title": extracted.get("title"),
            "transcript": transcript,
            "summary": summary,
            "notes": extracted.get("notes", []),
        })
    except Exception as exc:
        yield _sse("error", {"message": str(exc), "notes": []})
```

- [ ] **Step 4: Add `asyncio_mode` to pytest config so async tests work**

Create `pytest.ini` at the project root:

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 5: Run all tests — expect pass**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pytest tests/test_app.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py pytest.ini
git commit -m "feat: convert /analyze to SSE streaming endpoint with progress events"
```

---

## Task 4: Add progress bar UI to frontend

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add progress bar CSS inside the existing `<style>` block**

Inside the `<style>` tag in `static/index.html`, append after the last existing rule:

```css
      #progress-section { display: none; }
      .progress-track { background: #1e2d50; border-radius: 8px; height: 8px; overflow: hidden; margin-bottom: 8px; }
      .progress-fill { background: #5eead4; height: 100%; width: 0%; transition: width 0.4s ease; }
      .progress-label { color: #9fb0d9; font-size: 13px; }
```

- [ ] **Step 2: Add progress bar HTML between the button and status div**

After `<button id="run">Transcribe + Summarize</button>` and before `<div id="status" ...>`, insert:

```html
    <div id="progress-section" class="card">
      <div class="progress-track">
        <div id="progress-fill" class="progress-fill"></div>
      </div>
      <span id="progress-label" class="progress-label"></span>
    </div>
```

- [ ] **Step 3: Replace the `<script>` block with streaming version**

Replace the entire `<script>...</script>` block with:

```html
    <script>
      const $ = (id) => document.getElementById(id);

      function showProgress(message, stepCount) {
        $("progress-section").style.display = "block";
        const pct = Math.min(stepCount * 20, 90);
        $("progress-fill").style.width = pct + "%";
        $("progress-label").textContent = message;
      }

      function hideProgress() {
        $("progress-fill").style.width = "100%";
        $("progress-label").textContent = "完成";
        setTimeout(() => { $("progress-section").style.display = "none"; }, 700);
      }

      $("run").addEventListener("click", async () => {
        const url = $("url").value.trim();
        if (!url) return;

        $("status").textContent = "处理中...";
        $("summary").value = "";
        $("transcript").value = "";
        $("progress-section").style.display = "block";
        $("progress-fill").style.width = "0%";
        $("progress-label").textContent = "";
        let stepCount = 0;

        try {
          const res = await fetch("/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url }),
          });

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buf = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const parts = buf.split("\n\n");
            buf = parts.pop();

            for (const part of parts) {
              const evtMatch = part.match(/^event: (\w+)/m);
              const dataMatch = part.match(/^data: (.+)/m);
              if (!evtMatch || !dataMatch) continue;
              const type = evtMatch[1];
              const data = JSON.parse(dataMatch[1]);

              if (type === "progress") {
                stepCount++;
                showProgress(data.message, stepCount);
              } else if (type === "result") {
                hideProgress();
                $("status").textContent = `完成。来源: ${data.source_type}. ${data.notes.join(" | ")}`;
                $("summary").value = data.summary || "";
                $("transcript").value = data.transcript || "";
              } else if (type === "error") {
                $("progress-section").style.display = "none";
                const notes = (data.notes || []).join(" | ");
                $("status").textContent = `失败: ${data.message}${notes ? " — " + notes : ""}`;
              }
            }
          }
        } catch (err) {
          $("progress-section").style.display = "none";
          $("status").textContent = `网络错误: ${err.message}`;
        }
      });
    </script>
```

- [ ] **Step 4: Start the dev server and test manually**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
uvicorn app:app --reload --port 8000
```

Open `http://127.0.0.1:8000` in a browser. Paste a public YouTube URL and click **Transcribe + Summarize**. Verify:
- Progress bar appears and fills step by step
- "获取 YouTube 字幕..." label appears
- "生成摘要..." appears before the final result
- Summary and transcript populate after completion
- Progress bar disappears with a short fade

- [ ] **Step 5: Commit**

```bash
git add static/index.html
git commit -m "feat: add SSE progress bar to frontend"
```

---

## Self-Review Checklist

- [x] Spec section "SSE helper" → Task 2
- [x] Spec section "async/blocking IO" → Task 3 Step 3 (`asyncio.to_thread`)
- [x] Spec "YouTube flow steps" (detecting, transcript, audio_download, summarizing) → Task 3 `_analyze_stream`
- [x] Spec "non-YouTube sources get detecting + summarizing" → Task 3 (elif branches only yield summarizing)
- [x] Spec "Frontend streaming fetch" → Task 4 Step 3
- [x] Spec "Progress bar advances incrementally" → Task 4 `showProgress(stepCount * 20)`
- [x] Spec "error event hides progress bar" → Task 4 Step 3 error branch
- [x] Spec "extractors not changed" → confirmed, no extractor tasks
- [x] Type consistency: `_sse()` defined in Task 2, used in Task 3 — same signature throughout
- [x] No TBDs or placeholders found
