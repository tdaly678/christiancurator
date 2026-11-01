"""
site_stats.py: live counts for masthead and signup copy (2026-11-01).

Computed from repo data at render time so the copy never goes stale:
  source_count()   feeds that reach the page (fetcher/sources.py, minus
                   discovery-only feeds, which are never ranked)
  archive_stats()  number of published daily editions in docs/archive/ and
                   the date of the first one
  voices_count()   indexable voice pages (docs/voices_data.json minus
                   noindex and merged-duplicate stubs)

Each returns 0 / None on any error, and templates hide a claim whose count is 0.
"""

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"


def source_count() -> int:
    try:
        from fetcher.sources import SOURCES
    except Exception:
        return 0
    return sum(1 for s in SOURCES if s.get("role") != "discovery")


def archive_stats(archive_dir: Path | None = None) -> dict:
    """{"count": N, "since": date | None} for docs/archive/YYYY-MM-DD/ pages."""
    archive_dir = archive_dir or DOCS_DIR / "archive"
    days = []
    if archive_dir.exists():
        for d in archive_dir.iterdir():
            if d.is_dir() and (d / "index.html").exists():
                try:
                    days.append(date.fromisoformat(d.name))
                except ValueError:
                    pass
    return {"count": len(days), "since": min(days) if days else None}


def voices_count() -> int:
    try:
        voices = json.loads((DOCS_DIR / "voices_data.json").read_text(encoding="utf-8"))
    except Exception:
        return 0
    hidden = set()
    for name in ("voices_noindex.json", "voices_redirects.json"):
        try:
            data = json.loads((ROOT / "frontend" / name).read_text(encoding="utf-8"))
            hidden |= set(data if isinstance(data, list) else data.keys())
        except Exception:
            pass
    return sum(1 for v in voices if v.get("slug") and v["slug"] not in hidden)


def site_stats() -> dict:
    """Everything the templates need, with display strings ready to drop in."""
    arch = archive_stats()
    since = arch["since"]
    return {
        "source_count": source_count(),
        "edition_count": arch["count"],
        "editions_since": since.strftime("%B %Y") if since else "",
        "voices_count": voices_count(),
    }
