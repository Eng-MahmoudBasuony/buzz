"""YouTube video URL validation shared by the desktop and browser bridge."""

import re
from urllib.parse import parse_qs, urlsplit

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def canonical_video(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("Open a YouTube video first.")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ValueError("A YouTube HTTPS video URL is required.")
    host = parsed.hostname
    parts = parsed.path.strip("/").split("/")
    if host == "youtu.be" and len(parts) == 1:
        video = parts[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        if parsed.path == "/watch":
            video = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
            video = parts[1]
        else:
            video = ""
    else:
        video = ""
    if not VIDEO_ID.fullmatch(video):
        raise ValueError("A single YouTube video is required.")
    return video, "https://www.youtube.com/watch?v=" + video
