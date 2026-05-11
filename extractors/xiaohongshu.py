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
