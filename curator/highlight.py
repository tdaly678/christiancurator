"""Highlighted sources (S5, Nov 23 2026).

Tom: "I love this stuff from Burge, we should be highlighting him on curator
feed." A source in fetcher/sources.py with `"highlight": "research"` gets:

  - a reserved sublead for each new post: published in the last
    HIGHLIGHT_FRESH_DAYS days and never shown before (frontend/layout.py
    reserve_highlight()), so it also leads the email's Lead section;
  - no Catholic, mainline polity or off-mission cap in the scorer: data about
    American religion (Catholics, mainline, nones) is on mission;
  - the publisher's own headline, never a Claude rewrite
    (curator/title_rewriter.py keep_publisher_title()).

Only Ryan Burge (Graphs About Religion) is highlighted today. Add the key to
another source to turn it on there.

No API clients here, so render-only scripts can import it.
"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from fetcher.sources import SOURCES

HIGHLIGHT_FRESH_DAYS = 4  # Burge posts Monday and Thursday mornings
HIGHLIGHT_SOURCES = {s["name"]: s["highlight"] for s in SOURCES if s.get("highlight")}


def highlight_kind(a: dict) -> str | None:
    """The source's highlight kind ("research"), or None."""
    return a.get("highlight") or HIGHLIGHT_SOURCES.get(a.get("source_name") or "")


def is_highlighted(a: dict) -> bool:
    return bool(highlight_kind(a))


def age_days(a: dict, now: datetime | None = None) -> float | None:
    try:
        dt = parsedate_to_datetime(a.get("published") or "")
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - dt).total_seconds() / 86400


def needs_featured_slot(a: dict, now: datetime | None = None) -> bool:
    """A highlighted post on its first showing, published in the last
    HIGHLIGHT_FRESH_DAYS days."""
    if not is_highlighted(a) or a.get("previously_shown") or a.get("shown_yesterday"):
        return False
    age = age_days(a, now)
    return age is not None and age <= HIGHLIGHT_FRESH_DAYS
