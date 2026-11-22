"""
media_kind.py: is this feed item a podcast episode or a video? (Nov 22 2026)

Shared by frontend.layout.is_audio_video() (the homepage audio/video cap) and
curator.title_rewriter (podcast episodes keep the publisher's title). No API
clients here.

Signals, any one is enough:
  - a media_format set by a media feed
  - a YouTube or Vimeo host
  - a podcast or episode URL path: /podcast, /erlc-podcast/, /episode-844,
    /episodes/, /p/ep205 (Substack), /ep-12
  - a title opening "Podcast:", "Video:", "Episode 12", "Ep. 12"
  - a description opening "Ep.", "Episode 12", "In this episode",
    "Join me as I talk with", "On this episode", "Listen", "Watch"
"""

import re
from urllib.parse import urlsplit

VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")

_PATH_RE = re.compile(
    r"/podcasts?(?:[/-]|$)"                   # /podcast, /podcasts/, /podcast-x
    r"|/[\w-]+-podcasts?(?:/|$)"              # /erlc-podcast/ (not /why-podcasts-matter)
    r"|/episodes?(?:[/-]|$)"                  # /episode-844, /episodes/x
    r"|/(?:p/)?ep-?\d+(?:[/-]|$)"             # /p/ep205, /ep-12
    r"|/p/[\w-]*-ep-?\d+(?:[/-]|$)"           # /p/show-ep-205
    r"|/[\w-]+-episode-\d+(?:[/-]|$)",        # /great-talk-episode-12
    re.IGNORECASE,
)
_TITLE_RE = re.compile(
    r"^\s*(?:podcast|video)\s*:"
    r"|^\s*(?:ep(?:isode)?\.?\s*#?\d+)\b",
    re.IGNORECASE,
)
_DESC_RE = re.compile(
    r"^\s*(?:ep\.|ep\s*\d|episode\s*#?\d)"
    r"|^\s*join\s+(?:me|us)\s+as\s+(?:i|we)\s+(?:talk|speak|sit\s+down|chat|discuss)\b"
    r"|^\s*(?:in|on)\s+(?:this|today's)\s+(?:week's\s+)?(?:episode|podcast|conversation)\b"
    r"|^\s*(?:listen|watch)\s+(?:now|to\s+(?:this|the|our)|as)\b",
    re.IGNORECASE,
)


def _description(a: dict) -> str:
    text = a.get("summary") or a.get("description") or a.get("full_content") or ""
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())[:200]


def looks_like_audio_video(a: dict) -> bool:
    """True for podcast episodes and videos, whatever feed they came from."""
    if a.get("media_format"):
        return True
    parts = urlsplit(a.get("url") or "")
    host = (parts.hostname or "").lower()
    if any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS):
        return True
    if _PATH_RE.search(parts.path or ""):
        return True
    if _TITLE_RE.search(a.get("original_title") or a.get("title") or ""):
        return True
    return bool(_DESC_RE.search(_description(a)))
