"""One rule for "is this page noindexed": the page's own robots meta tag.

Used by regenerate_sitemap() and scripts/check_voices.py, so a page whose HTML says
noindex is never listed in a sitemap, whatever frontend/voices_noindex.json says
(the list is a record of decisions, not the source of truth; Nov 15 2026).
"""
import re
from pathlib import Path

ROBOTS_NOINDEX_RE = re.compile(r'<meta\b[^>]*name="robots"[^>]*content="[^"]*noindex|'
                               r'<meta\b[^>]*content="[^"]*noindex[^"]*"[^>]*name="robots"', re.I)


def html_has_noindex(page: str) -> bool:
    return bool(ROBOTS_NOINDEX_RE.search(page))


def page_has_noindex(path: Path) -> bool:
    try:
        return html_has_noindex(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False
