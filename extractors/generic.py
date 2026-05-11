from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_generic_webpage(url: str) -> dict:
    try:
        response = httpx.get(url, follow_redirects=True, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        return {
            "ok": False,
            "source_type": "generic",
            "title": None,
            "transcript": None,
            "notes": [f"Request failed: {exc}"],
        }

    soup = BeautifulSoup(response.text, "html.parser")
    title = _clean(soup.title.text) if soup.title and soup.title.text else None

    blocks = []
    for tag in soup.find_all(["article", "p", "h1", "h2", "h3"]):
        text = _clean(tag.get_text(" ", strip=True))
        if len(text) >= 40:
            blocks.append(text)

    transcript = "\n\n".join(blocks[:20])
    if not transcript:
        desc = soup.find("meta", attrs={"name": "description"})
        if desc and desc.get("content"):
            transcript = _clean(desc["content"])

    return {
        "ok": bool(transcript),
        "source_type": "generic",
        "title": title,
        "transcript": transcript or None,
        "notes": ["Generic webpage extraction is best effort."],
    }
