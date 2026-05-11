from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _is_video(soup: BeautifulSoup) -> bool:
    if soup.find("meta", property="og:video"):
        return True
    if soup.find("video"):
        return True
    return False


def extract_xiaohongshu(url: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    try:
        response = httpx.get(url, headers=headers, follow_redirects=True, timeout=20)
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
    seen = set()
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
            "notes": ["Could not extract useful public text from Xiaohongshu.", "Private, login-only, or anti-bot pages are intentionally unsupported."],
        }

    return {
        "ok": True,
        "source_type": "xiaohongshu",
        "title": title,
        "transcript": transcript,
        "notes": ["Best-effort public-page text extraction only.", "Video/audio transcription is not guaranteed for Xiaohongshu links in this MVP."],
    }
