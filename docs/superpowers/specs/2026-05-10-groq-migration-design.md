# Groq Migration Design

**Date:** 2026-05-10
**Status:** Approved

## Goal

Replace all OpenAI API usage with Groq's free-tier API. The `openai` Python package is removed entirely. A single `GROQ_API_KEY` covers both text summarization and audio transcription.

## Scope

- Replace OpenAI client with Groq client in `summarizer.py` and `extractors/audio.py`
- Update `requirements.txt` and `.env.example`
- No structural changes, no new files, no fallback logic

Out of scope: changing any extractor logic, UI changes, adding provider switching.

## Files Changed

| File | Change |
|---|---|
| `summarizer.py` | Swap `OpenAI` → `Groq`, `client.responses.create` → `client.chat.completions.create`, update env var and model default |
| `extractors/audio.py` | Swap `OpenAI` → `Groq`, update env var and model default |
| `requirements.txt` | Remove `openai==1.47.0`, add `groq` (latest) |
| `.env.example` | Replace `OPENAI_API_KEY`/`OPENAI_MODEL`/`WHISPER_MODEL` with `GROQ_API_KEY`/`GROQ_MODEL`/`GROQ_WHISPER_MODEL` |

## API Differences

### Summarization (`summarizer.py`)

Current (OpenAI Responses API):
```python
from openai import OpenAI
client = OpenAI(api_key=api_key)
response = client.responses.create(
    model=model,
    input=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
)
return response.output_text.strip()
```

New (Groq Chat Completions — OpenAI-compatible):
```python
from groq import Groq
client = Groq(api_key=api_key)
response = client.chat.completions.create(
    model=model,
    messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
)
return response.choices[0].message.content.strip()
```

### Audio Transcription (`extractors/audio.py`)

The `audio.transcriptions.create` interface is identical between OpenAI and Groq — only the client class and env var change.

```python
from groq import Groq
client = Groq(api_key=api_key)
transcript = client.audio.transcriptions.create(model=model, file=handle)
```

## Environment Variables

| Old | New | Default |
|---|---|---|
| `OPENAI_API_KEY` | `GROQ_API_KEY` | (required) |
| `OPENAI_MODEL` | `GROQ_MODEL` | `llama-3.3-70b-versatile` |
| `WHISPER_MODEL` | `GROQ_WHISPER_MODEL` | `whisper-large-v3` |

## Error Handling

No changes. Both files already catch exceptions broadly — Groq raises standard Python exceptions compatible with existing `try/except` blocks.

## Tests

The existing 5 tests mock `app.summarize_text` and extractors at the `app` module level — they do not instantiate any AI client. No test changes are needed.
