# Groq Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all OpenAI API usage with Groq's free-tier API, removing the `openai` package entirely.

**Architecture:** Two modules use OpenAI — `summarizer.py` (LLM via `client.responses.create`) and `extractors/audio.py` (Whisper via `client.audio.transcriptions.create`). Both are swapped to use the `groq` SDK: LLM moves to `client.chat.completions.create`, Whisper interface stays the same. Env vars `OPENAI_API_KEY`/`OPENAI_MODEL`/`WHISPER_MODEL` become `GROQ_API_KEY`/`GROQ_MODEL`/`GROQ_WHISPER_MODEL`.

**Tech Stack:** `groq` Python SDK (replaces `openai==1.47.0`), pytest + monkeypatch for unit tests.

---

## File Map

| File | Action | Change |
|---|---|---|
| `summarizer.py` | Modify | Swap `OpenAI` → `Groq`, `responses.create` → `chat.completions.create`, new env vars |
| `extractors/audio.py` | Modify | Swap `OpenAI` → `Groq`, new env vars, update notes string |
| `requirements.txt` | Modify | Remove `openai==1.47.0`, add `groq` |
| `.env.example` | Modify | Replace all three env vars with Groq equivalents |
| `tests/test_summarizer.py` | Create | Unit tests for `summarize_text` using mocked Groq client |
| `tests/test_audio.py` | Create | Unit tests for `_transcribe_file` using mocked Groq client |

---

## Task 1: Install Groq SDK and scaffold failing tests

**Files:**
- Create: `tests/test_summarizer.py`
- Create: `tests/test_audio.py`

- [ ] **Step 1: Install the groq package into the venv**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pip install groq
```

Expected: groq installs cleanly. `openai` remains installed for now (still needed by the old code).

- [ ] **Step 2: Create `tests/test_summarizer.py` with failing tests**

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from summarizer import summarize_text


def test_summarize_text_calls_groq_chat_completions(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    mock_message = MagicMock()
    mock_message.content = "  A great summary.  "
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("summarizer.Groq", return_value=mock_client) as mock_groq_cls:
        result = summarize_text("youtube", "Test Title", "hello world transcript")

    mock_groq_cls.assert_called_once_with(api_key="test-key")
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "llama-3.3-70b-versatile"
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "hello world transcript" in messages[1]["content"]
    assert result == "A great summary."


def test_summarize_text_raises_without_groq_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        summarize_text("youtube", None, "some text")
```

- [ ] **Step 3: Create `tests/test_audio.py` with failing tests**

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from extractors.audio import _transcribe_file


def test_transcribe_file_uses_groq_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_WHISPER_MODEL", "whisper-large-v3")

    mock_transcript = MagicMock()
    mock_transcript.text = "hello from audio"

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = mock_transcript

    test_audio = tmp_path / "audio.mp3"
    test_audio.write_bytes(b"fake audio data")

    with patch("extractors.audio.Groq", return_value=mock_client) as mock_groq_cls:
        result = _transcribe_file(test_audio)

    mock_groq_cls.assert_called_once_with(api_key="test-key")
    call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == "whisper-large-v3"
    assert result == "hello from audio"


def test_transcribe_file_raises_without_groq_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    test_audio = tmp_path / "audio.mp3"
    test_audio.write_bytes(b"fake audio data")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        _transcribe_file(test_audio)
```

- [ ] **Step 4: Run new tests — expect failure**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pytest tests/test_summarizer.py tests/test_audio.py -v
```

Expected: both `test_..._calls_groq_...` tests FAIL (the modules still use OpenAI, so `patch("summarizer.Groq", ...)` patches a non-existent name and assertions on the mock fail). The `raises_without_key` tests also fail (still checks `OPENAI_API_KEY`).

- [ ] **Step 5: Commit test scaffolding**

```bash
git add tests/test_summarizer.py tests/test_audio.py
git commit -m "test: add failing Groq unit tests for summarizer and audio extractor"
```

---

## Task 2: Migrate `summarizer.py` to Groq

**Files:**
- Modify: `summarizer.py`

- [ ] **Step 1: Replace the entire content of `summarizer.py`**

```python
from __future__ import annotations

import os

from groq import Groq


SYSTEM_PROMPT = """You turn raw transcripts or extracted page text into clean, useful notes.
Return concise readable markdown with:
1. one-line takeaway
2. bullet summary
3. key quotes or points
4. action items or follow-ups if obvious
Be honest when the source text looks partial or noisy.
"""


def summarize_text(source_type: str, source_title: str | None, transcript: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required for summarization")

    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    client = Groq(api_key=api_key)
    prompt = f"Source type: {source_type}\nTitle: {source_title or 'Unknown'}\n\nSource text:\n{transcript[:20000]}"
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    )
    return response.choices[0].message.content.strip()
```

- [ ] **Step 2: Run summarizer tests — expect pass**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pytest tests/test_summarizer.py -v
```

Expected: both tests PASS.

- [ ] **Step 3: Run full suite — existing SSE tests must still pass**

```bash
pytest tests/ -v
```

Expected: all 7 tests pass (2 new summarizer + 5 existing SSE tests). The audio tests still fail — that's fine, Task 3 fixes them.

- [ ] **Step 4: Commit**

```bash
git add summarizer.py
git commit -m "feat: migrate summarizer to Groq chat completions"
```

---

## Task 3: Migrate `extractors/audio.py` to Groq

**Files:**
- Modify: `extractors/audio.py`

- [ ] **Step 1: Replace the entire content of `extractors/audio.py`**

```python
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
```

- [ ] **Step 2: Run audio tests — expect pass**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pytest tests/test_audio.py -v
```

Expected: both tests PASS.

- [ ] **Step 3: Run full suite — all 9 tests must pass**

```bash
pytest tests/ -v
```

Expected: all 9 tests pass (2 summarizer + 2 audio + 5 SSE endpoint).

- [ ] **Step 4: Commit**

```bash
git add extractors/audio.py
git commit -m "feat: migrate audio extractor to Groq Whisper"
```

---

## Task 4: Remove OpenAI from requirements, update .env.example

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Update `requirements.txt`**

Replace the entire file with:

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
httpx==0.27.2
beautifulsoup4==4.12.3
youtube-transcript-api==0.6.2
yt-dlp==2024.9.27
groq
python-multipart==0.0.9
pydantic==2.9.2
python-dotenv==1.0.1
```

- [ ] **Step 2: Update `.env.example`**

Replace the entire file with:

```
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_WHISPER_MODEL=whisper-large-v3
PORT=8000
```

- [ ] **Step 3: Uninstall openai from venv to confirm nothing imports it**

```bash
cd /Users/minidreamer/workplace/link-summarizer
source .venv/bin/activate
pip uninstall openai -y
```

- [ ] **Step 4: Run full test suite — confirm openai is not needed**

```bash
pytest tests/ -v
```

Expected: all 9 tests pass with openai uninstalled.

- [ ] **Step 5: Confirm the app starts without openai**

```bash
python -c "from app import app; from summarizer import summarize_text; from extractors.audio import extract_audio; print('OK')"
```

Expected: `OK` printed, no ImportError.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: remove openai dependency, update env vars to GROQ_*"
```

---

## Self-Review Checklist

- [x] Spec "swap OpenAI → Groq in summarizer.py" → Task 2
- [x] Spec "swap OpenAI → Groq in audio.py" → Task 3
- [x] Spec "client.responses.create → chat.completions.create" → Task 2 Step 1 (full file replacement)
- [x] Spec "response.output_text → response.choices[0].message.content" → Task 2 Step 1
- [x] Spec "audio interface unchanged, only client + env var" → Task 3 Step 1
- [x] Spec "remove openai from requirements, add groq" → Task 4 Step 1
- [x] Spec "OPENAI_API_KEY → GROQ_API_KEY, OPENAI_MODEL → GROQ_MODEL, WHISPER_MODEL → GROQ_WHISPER_MODEL" → Task 4 Step 2
- [x] Tests mock at module level (patch("summarizer.Groq"), patch("extractors.audio.Groq")) — consistent across all tasks
- [x] No placeholders found
- [x] No TBDs found
