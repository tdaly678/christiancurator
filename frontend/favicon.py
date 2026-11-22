"""Favicon links for every page (S1 report, section 6).

The icons are drawn by scripts/build_favicons.py. ``add_favicon(html)`` adds
or refreshes the block between ``<!-- CC-FAVICON:START -->`` and
``<!-- CC-FAVICON:END -->`` right after the viewport meta (else right after
<head>). It edits the <head> only and is idempotent.
"""
from __future__ import annotations

import re

FAVICON_START = "<!-- CC-FAVICON:START -->"
FAVICON_END = "<!-- CC-FAVICON:END -->"
FAVICON_LINKS = (
    FAVICON_START
    + '<link rel="icon" href="/favicon.ico" sizes="any" />'
    + '<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32x32.png" />'
    + '<link rel="apple-touch-icon" href="/apple-touch-icon.png" />'
    + FAVICON_END
)
_BLOCK_RE = re.compile(re.escape(FAVICON_START) + r".*?" + re.escape(FAVICON_END), re.S)
_VIEWPORT_RE = re.compile(r'([ \t]*)<meta\b[^>]*\bname="viewport"[^>]*>\n?')
_HEAD_RE = re.compile(r"<head[^>]*>\n?")


def add_favicon(html: str) -> str:
    head_end = html.find("</head>")
    if head_end < 0:
        return html
    head, rest = html[:head_end], html[head_end:]
    if FAVICON_START in head:
        return _BLOCK_RE.sub(FAVICON_LINKS, head, count=1) + rest
    m = _VIEWPORT_RE.search(head)
    if m:
        line_break = "" if m.group(0).endswith("\n") else "\n"
        return head[:m.end()] + line_break + m.group(1) + FAVICON_LINKS + "\n" + head[m.end():] + rest
    m = _HEAD_RE.search(head)
    if not m:
        return html
    return head[:m.end()] + FAVICON_LINKS + "\n" + head[m.end():] + rest
