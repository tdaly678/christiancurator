"""Retired topic slugs and their redirect stubs.

A topic page that is folded into another keeps its URL as a redirect stub
(meta refresh + canonical to the new page, robots noindex, follow), the same
pattern as merged voice pages. The record of retired slugs lives in
frontend/topics_redirects.json: {old_slug: {"to": new_slug, "name": ..., ...}}.

Every script that walks docs/topics/ should use live_topic_dirs() (or skip
retired_topic_slugs()) so the stub is never treated as a topic page: no
sitemap entry, no hub card, no quality or AEO checks, no injected blocks.
Tests: tests/test_ai_topic_page.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REDIRECTS_PATH = REPO_ROOT / "frontend" / "topics_redirects.json"
SITE = "https://www.christiancurator.com"

STUB = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>{name} | Christian Curator</title>
  <meta name="robots" content="noindex, follow" />
  <link rel="canonical" href="{site}/topics/{to}/" />
  <meta http-equiv="refresh" content="0; url=/topics/{to}/" />
</head>
<body data-pagefind-ignore="all">
  <p>This page has moved to <a href="/topics/{to}/">{to_name}</a>.</p>
</body>
</html>
"""


def load_topic_redirects(path: Path = REDIRECTS_PATH) -> dict[str, dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def retired_topic_slugs(path: Path = REDIRECTS_PATH) -> set[str]:
    return set(load_topic_redirects(path))


def redirect_target(slug: str, path: Path = REDIRECTS_PATH) -> str:
    """The live slug for a slug (itself when it is not retired)."""
    return (load_topic_redirects(path).get(slug) or {}).get("to") or slug


def live_topic_dirs(topics_dir: Path, path: Path = REDIRECTS_PATH) -> list[Path]:
    """Sorted topic directories with an index.html, retired stubs left out."""
    retired = retired_topic_slugs(path)
    if not topics_dir.exists():
        return []
    return sorted(d for d in topics_dir.iterdir()
                  if d.is_dir() and d.name not in retired and (d / "index.html").exists())


def render_stub(old: str, to: str, name: str, to_name: str) -> str:
    import html as html_mod
    return STUB.format(name=html_mod.escape(name), to=to, site=SITE,
                       to_name=html_mod.escape(to_name))
