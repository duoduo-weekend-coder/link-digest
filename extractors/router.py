from urllib.parse import urlparse


def detect_source_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()

    if any(domain in host for domain in ["youtube.com", "youtu.be"]):
        return "youtube"
    if "xiaohongshu.com" in host or "xhslink.com" in host:
        return "xiaohongshu"
    if path.endswith((".mp3", ".m4a", ".wav", ".aac", ".ogg")):
        return "audio"
    return "generic"
