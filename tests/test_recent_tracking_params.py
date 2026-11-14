"""utm_* parameters are stripped from Recent Articles and Latest links (Nov 14 2026).

9Marks feed links carry ?utm_source=rss&utm_medium=rss&utm_campaign=...; nothing
we link to from a topic or voice page should carry tracking parameters.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_recent_articles as bra  # noqa: E402

NINE = "https://www.9marks.org/article/church-membership/?utm_source=rss&utm_medium=rss&utm_campaign=church-membership"


def test_strip_tracking_drops_only_utm():
    assert bra.strip_tracking(NINE) == "https://www.9marks.org/article/church-membership/"
    assert bra.strip_tracking("https://x.org/a?id=7&utm_source=rss&page=2#top") == "https://x.org/a?id=7&page=2#top"
    assert bra.strip_tracking("https://x.org/a?UTM_Medium=rss&p=1") == "https://x.org/a?p=1"
    assert bra.strip_tracking("https://x.org/a?utm_source=rss#sec") == "https://x.org/a#sec"
    assert bra.strip_tracking("https://x.org/?p=58006") == "https://x.org/?p=58006"
    assert bra.strip_tracking("https://x.org/a") == "https://x.org/a"
    assert bra.strip_tracking("") == ""


def test_topic_items_and_rendered_links_are_clean():
    history = [{"url": NINE, "original_title": "Church Membership Matters", "source_name": "9Marks",
                "date_shown": "2026-11-13", "tags": []}]
    fresh = {"membership": [{"url": NINE + "&ref=x", "title": "Church Membership Matters",
                             "source": "9Marks", "date": "2026-11-12"}]}
    items = bra.topic_items("membership", history, fresh)
    assert [a["url"] for a in items] == ["https://www.9marks.org/article/church-membership/",
                                         "https://www.9marks.org/article/church-membership/?ref=x"]
    assert "utm_" not in bra.render_latest_line(items)
    raw = [{"url": NINE, "title": "Church Membership Matters", "source": "9Marks", "date": "2026-11-13"}]
    html = bra.render_section("Fresh From the Digest", "Recent Articles on Membership", raw)
    assert 'href="https://www.9marks.org/article/church-membership/"' in html and "utm_" not in html
