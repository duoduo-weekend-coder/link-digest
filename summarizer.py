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
