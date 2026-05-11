# SSE Progress Bar for YouTube Summarization

**Date:** 2026-05-10  
**Status:** Approved

## Goal

Add real-time progress feedback to the YouTube transcript → summarization pipeline using Server-Sent Events (SSE). The user sees a step-by-step progress bar while the server fetches the transcript, optionally downloads audio, and generates a summary.

## Scope

- Convert `POST /analyze` from a plain JSON response to a `StreamingResponse` (SSE)
- Add progress bar UI to `static/index.html`
- No new routes, no job IDs, no persistence

Out of scope: non-YouTube sources (they still work but get no granular progress steps), authentication, multi-user support.

## Backend Architecture

### `/analyze` endpoint

`app.py::analyze` becomes an `async def` that returns `StreamingResponse` wrapping an async generator `_analyze_stream(url)`.

The generator yields SSE-formatted strings:

```
event: progress\ndata: {"step": "<step_id>", "message": "<human label>"}\n\n
event: result\ndata: {<full result object>}\n\n
event: error\ndata: {"message": "<error>", "notes": [...]}\n\n
```

### Progress steps (YouTube path)

| step id | label |
|---|---|
| `detecting` | 检测链接类型... |
| `transcript` | 获取 YouTube 字幕... |
| `audio_download` | 下载音频（字幕不可用）... |
| `transcribing` | 转录音频... |
| `summarizing` | 生成摘要... |

Non-YouTube sources emit only `detecting` and `summarizing` steps.

### Async / blocking IO

All blocking calls (youtube-transcript-api, subprocess yt-dlp, OpenAI SDK) are wrapped with `asyncio.to_thread` so they don't block the event loop between SSE flushes.

### SSE helper

A small `_sse(event, data)` function formats one SSE message:

```python
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
```

### Error handling

- URL validation failure → `event: error` immediately
- Extraction failure → `event: error` with notes from extractor
- Summarization failure → `event: error`
- All exceptions are caught; the generator always closes cleanly

## Frontend

### Streaming fetch

Replace the existing `fetch` + `await res.json()` with a streaming `fetch` that reads the response body line by line and dispatches on `event:` type. `EventSource` is not used because the endpoint is `POST`.

### Progress bar UI

A new `#progress` section (hidden by default) appears below the input once the user clicks Submit:

- Horizontal bar advances on each `progress` event received (incremental, not percentage-based, since total steps vary by path)
- Current step label underneath
- Completed steps shown in a distinct color; current step has a CSS spinner
- On `event: result`: progress section hides, result cards animate in
- On `event: error`: progress section hides, error shown in red status card

### Existing UI

`#summary` and `#transcript` textareas are kept as-is. The `#status` line is kept for the final done/error message.

## Files Changed

| File | Change |
|---|---|
| `app.py` | Convert `analyze()` to async SSE generator |
| `static/index.html` | Add progress bar, replace fetch with streaming reader |

Extractors (`extractors/`) are **not changed** — they remain synchronous dicts returning functions, wrapped in `asyncio.to_thread` at the call site.
