"""Favicon files and <link rel="icon"> on every page (S1 report, section 6)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from frontend.favicon import FAVICON_LINKS, FAVICON_START, add_favicon


def test_icon_files_exist():
    for name in ("favicon.ico", "favicon-32x32.png", "apple-touch-icon.png"):
        assert (ROOT / "docs" / name).stat().st_size > 0, name


def test_add_favicon_after_viewport_and_idempotent():
    html = ('<html><head>\n  <meta charset="utf-8" />\n'
            '  <meta content="width=device-width" name="viewport"/>\n  <title>x</title>\n</head><body></body></html>')
    out = add_favicon(html)
    assert out.index(FAVICON_START) > out.index('name="viewport"')
    assert out.index(FAVICON_START) < out.index("<title>")
    assert add_favicon(out) == out


def test_add_favicon_without_viewport_goes_after_head():
    out = add_favicon("<html><head><title>x</title></head><body></body></html>")
    assert out.startswith("<html><head>" + FAVICON_LINKS)


def test_templates_link_the_icons():
    for name in ("template.html", "digest_template.html", "archive_template.html", "daily_template.html"):
        assert FAVICON_LINKS in (ROOT / "frontend" / name).read_text(encoding="utf-8"), name


def test_published_pages_link_the_icons():
    for rel in ("index.html", "404.html", "about/index.html", "topics/index.html",
                "topics/baptism/index.html", "voices/index.html"):
        assert FAVICON_START in (ROOT / "docs" / rel).read_text(encoding="utf-8"), rel
