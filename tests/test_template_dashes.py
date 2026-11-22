"""Writing rules: no em or en dashes in templates, topic data or page heads (S1 item 10)."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from curator.daily_summary import find_related_days
from frontend.topics_data import TOPICS
from scripts.fix_page_head_dashes import fix_html

DASH_RE = re.compile(r"[–—]|&mdash;|&ndash;|&#821[12];")
TEMPLATES = ["template.html", "digest_template.html", "archive_template.html", "daily_template.html"]


def test_templates_have_no_dashes():
    for name in TEMPLATES:
        text = (ROOT / "frontend" / name).read_text(encoding="utf-8")
        assert not DASH_RE.search(text), name


def test_topic_data_has_no_dashes():
    for t in TOPICS:
        for key in ("name", "hook", "summary", "seo_title", "seo_description"):
            assert not DASH_RE.search(t.get(key) or ""), (t["slug"], key)


def test_related_day_previews_drop_dashes():
    history = [{"slug": "2026-11-01", "date": "November 1, 2026", "themes": ["prayer"],
                "excerpt": "The church is asking what prayer costs — and whether it works."}]
    out = find_related_days(["Prayer"], history, "2026-11-20")
    assert out and not DASH_RE.search(out[0]["excerpt"])
    assert out[0]["excerpt"] == "The church is asking what prayer costs, and whether it works."


ARCHIVE_HEAD = (
    "<head>\n<title>Christian Curator — Daily Digest, November 20, 2026</title>\n"
    '<meta name="description" content="The best evangelical Christian writing curated for '
    'November 20, 2026 — theology, culture, church life, and more." />\n'
    '<meta property="og:title" content="Christian Curator — Daily Digest, November 20, 2026" />\n'
    "</head><body>\n"
    '<p><a href="/">Christian Curator</a> &mdash; Curated perspectives, updated daily.</p>\n'
    "<p>Body text — left alone.</p></body>"
)

DAILY_HEAD = (
    "<head><title>November 20, 2026 — Christian Curator Daily Pulse</title>\n"
    '<meta name="description" content="Model text — kept as written." />\n'
    '"headline": "November 20, 2026 — What the Christian World Is Talking About",\n'
    "</head><body>Pulse — kept.</body>"
)


def test_fix_html_archive_head():
    out = fix_html(ARCHIVE_HEAD)
    assert "<title>Daily Digest, November 20, 2026 | Christian Curator</title>" in out
    assert "November 20, 2026: theology, culture" in out
    assert 'content="Daily Digest, November 20, 2026 | Christian Curator"' in out
    assert "&middot; Curated perspectives" in out
    assert "Body text — left alone." in out
    assert fix_html(out) == out


def test_fix_html_daily_head_keeps_model_text():
    out = fix_html(DAILY_HEAD)
    assert "<title>November 20, 2026 | Christian Curator Daily Pulse</title>" in out
    assert '"November 20, 2026 | What the Christian World Is Talking About"' in out
    assert "Model text — kept as written." in out
    assert "Pulse — kept." in out
