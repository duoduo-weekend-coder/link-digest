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

Language rules:
- Detect the language of the source text.
- If the source is in English, write the entire summary in Chinese. Keep proper nouns, technical terms, and names in English.
- Otherwise, write the summary in the same language as the source.
"""

PUNCTUATION_PROMPT = """Add proper punctuation (commas, periods, question marks, etc.) to the following transcript.
Do not change any words, do not summarize, do not add or remove content. Only insert punctuation where naturally needed.
Return only the corrected transcript with no explanation."""


def restore_punctuation(transcript: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required")

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": PUNCTUATION_PROMPT},
            {"role": "user", "content": transcript[:20000]},
        ],
    )
    return response.choices[0].message.content.strip()


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
