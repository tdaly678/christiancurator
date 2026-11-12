"""Voices pilot: page template, noindex rule, title fix, and in-place blocks.

Run: python3 -m pytest tests/test_voice_pilot.py
"""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_recent_articles as recent  # noqa: E402
import fix_voice_titles  # noqa: E402
from curator import voice_pilot as vp  # noqa: E402
from curator.voice_generator import render_bio_page, voice_page_title  # noqa: E402

PILOT = vp.load_pilot()
WRITERS = {w["slug"]: w for w in PILOT["writers"]}

TOPIC_NAMES = {"biblical-literacy": "Biblical Literacy", "mental-health": "Mental Health & Faith"}
VOICE_NAMES = {"jen-wilkin": "Jen Wilkin"}


def _entry(**kw):
    base = {
        "slug": "test-writer", "name": "Test Writer", "reviewed": False, "page_kind": "guide",
        "dek": "Editor at Example | Writes on Bible reading",
        "bio": "Test Writer is an editor at Example.",
        "bio_sources": [{"label": "Author page, Example", "url": "https://example.com/author/test/"}],
        "where_they_write": [{"outlet": "Example", "url": "https://example.com/author/test/"}],
        "start_here": [{"title": "A Piece", "url": "https://example.com/a", "outlet": "Example",
                        "date": "2026-05-14", "note": "Argues one thing."}],
        "topics": [{"slug": "biblical-literacy", "angle": "Reading habits."},
                   {"slug": "no-such-topic", "angle": "Dropped."}],
        "related": ["jen-wilkin", "missing-voice"],
        "same_as": ["https://example.com/author/test/"],
    }
    base.update(kw)
    return base


def _render(entry, recent_html=""):
    return vp.render_pilot_page(entry, recent_html=recent_html, voice_names=VOICE_NAMES,
                                topic_names=TOPIC_NAMES, last_updated="2026-11-12")


def _recent_items(n):
    return [{"date": f"2026-05-{i + 1:02d}", "title": f"Piece {i} — part two",
             "url": f"https://example.com/{i}", "source": "Example"} for i in range(n)]


# ── Title template ───────────────────────────────────────────────────────────

def test_voice_title_is_pronoun_free_and_dash_free():
    t = voice_page_title("Abby Silva")
    assert t == "Abby Silva: Articles, Bio, and Where They Write | Christian Curator"
    assert "—" not in t and "–" not in t


def test_generated_voice_page_uses_new_title():
    page = render_bio_page({"name": "New Writer", "slug": "new-writer", "bio": "x"}, 0)
    assert "<title>New Writer: Articles, Bio, and Where They Write | Christian Curator</title>" in page
    assert "— Voices —" not in page


@pytest.mark.parametrize("old,new", [
    ("<title>Jane Roe — Voices — Christian Curator</title>",
     "<title>Jane Roe: Articles, Bio, and Where They Write | Christian Curator</title>"),
    ("<title>Jane Roe: Articles, Bio, and Where They Write | Christian Curator</title>",
     "<title>Jane Roe: Articles, Bio, and Where They Write | Christian Curator</title>"),
])
def test_fix_voice_titles_rewrites_and_is_idempotent(old, new):
    html = f'<head>{old}<meta property="og:title" content="x" /></head>\n\n\n\n<p>a</p>'
    out = fix_voice_titles.fix_page(html)
    assert new in out
    assert f'content="{new[7:-8]}"' in out
    assert "\n\n\n" not in out
    assert fix_voice_titles.fix_page(out) == out


def test_fix_voice_titles_stub_gets_short_title():
    html = '<title>Andrew Spencer — Christian Curator</title><meta http-equiv="refresh" content="0; url=/voices/x/" />'
    assert "<title>Andrew Spencer | Christian Curator</title>" in fix_voice_titles.fix_page(html)


def test_fix_voice_titles_leaves_pilot_titles_alone():
    """Rewrapping a where-to-start title doubled it on /voices/david-powlison/ (Nov 12)."""
    page = _render(_entry(page_kind="where_to_start", name="David Powlison"))
    title = "Where to Start with David Powlison: Articles and Bio | Christian Curator"
    assert f"<title>{title}</title>" in page
    out = fix_voice_titles.fix_page(page)
    assert f"<title>{title}</title>" in out
    assert f'property="og:title" content="{title}"' in out


@pytest.mark.parametrize("slug", sorted(WRITERS))
def test_built_pilot_page_title_matches_data(slug):
    path = ROOT / "docs" / "voices" / slug / "index.html"
    if not path.exists():
        pytest.skip("page not built")
    html = path.read_text(encoding="utf-8")
    title = vp.page_title(WRITERS[slug])
    assert f"<title>{title}</title>" in html
    assert f'property="og:title" content="{title}"' in html


def test_no_voice_page_has_a_doubled_title():
    doubled = []
    for path in (ROOT / "docs" / "voices").glob("*/index.html"):
        m = re.search(r"<title>(.*?)</title>", path.read_text(encoding="utf-8"), re.DOTALL)
        if m and (m.group(1).count("Christian Curator") > 1 or m.group(1).count("Articles") > 1):
            doubled.append(path.parent.name)
    assert doubled == []


# ── Noindex rule ─────────────────────────────────────────────────────────────

def test_unreviewed_auto_list_is_noindexed():
    entry = _entry(bio="", start_here=[])
    assert vp.needs_noindex(entry)
    assert 'name="robots" content="noindex' in _render(entry)


def test_unreviewed_page_with_curated_content_is_indexable():
    assert not vp.needs_noindex(_entry())
    assert "noindex" not in _render(_entry())


def test_reviewed_auto_list_is_indexable():
    assert not vp.needs_noindex(_entry(bio="", start_here=[], reviewed=True))


def test_noindexed_writers_get_no_topic_backlinks():
    writers = [_entry(), _entry(slug="auto-only", name="Auto Only", bio="", start_here=[])]
    mapping = vp.topic_voice_map(writers)
    slugs = {w["slug"] for pairs in mapping.values() for w, _ in pairs}
    assert slugs == {"test-writer"}


# ── Page template ────────────────────────────────────────────────────────────

def test_page_sections_in_brief_order():
    recent_html = recent.render_section("From Our Daily Digest", "Recent Articles by Test Writer",
                                        _recent_items(2), limit=recent.VOICE_MAX_ITEMS)
    page = _render(_entry(), recent_html)
    label = 'class="cc-vp-label">'
    order = ['class="cc-vp-name"', 'class="cc-vp-dek"', label + "About<", "Last updated November 12, 2026",
             label + "Where they write<", label + "Start here<", recent.V_START,
             label + "Topics they return to<", label + "Related voices<",
             "Compiled from public sources. Corrections:"]
    positions = [page.index(marker) for marker in order]
    assert positions == sorted(positions)


def test_page_drops_unknown_topics_and_voices_and_links_sources():
    page = _render(_entry())
    assert "/topics/biblical-literacy/" in page and "no-such-topic" not in page
    assert "/voices/jen-wilkin/" in page and "missing-voice" not in page
    assert 'href="https://example.com/author/test/"' in page
    assert 'href="/about/#contact"' in page


def test_schema_is_profile_page_with_person_same_as():
    page = _render(_entry())
    m = re.search(r'<script type="application/ld\+json" data-cc-marker="CC-PERSON-SCHEMA">\n(.*?)\n  </script>',
                  page, re.DOTALL)
    data = json.loads(m.group(1))
    assert data["@type"] == "ProfilePage"
    assert data["mainEntity"]["@type"] == "Person"
    assert data["mainEntity"]["sameAs"] == ["https://example.com/author/test/"]


def test_where_to_start_page_heading_and_label():
    page = _render(_entry(page_kind="where_to_start", deceased=True))
    assert '<h1 class="cc-vp-name">Where to start with Test Writer</h1>' in page
    assert ">Where to read<" in page


def test_render_refuses_em_dash_copy():
    with pytest.raises(ValueError):
        _render(_entry(dek="Editor — writer"))


def test_leaves_out_photos_scores_and_badges():
    page = _render(_entry()).lower()
    for banned in ("<img", "cc-voice-avatar", "featured</", "followers", "subscribe to"):
        assert banned not in page


# ── Recent pieces: static HTML, max 10, in place ─────────────────────────────

def test_recent_section_caps_at_ten_and_strips_dashes():
    html = recent.render_section("From Our Daily Digest", "Recent", _recent_items(14),
                                 limit=recent.VOICE_MAX_ITEMS)
    assert html.count('class="cc-recent-item"') == 10
    assert "—" not in html
    assert "Example · May 1, 2026" in html


def test_recent_inject_replaces_in_place_without_growing():
    section = recent.render_section("From Our Daily Digest", "Recent", _recent_items(2))
    page = '<main>\n<p class="cc-voice-bio">x</p>\n<a class="cc-back-link" href="/voices/">b</a>\n</main>'
    once = recent.inject(page, section)
    assert once.count(recent.V_START) == 1
    again = recent.inject(once, section)
    assert again == once
    for _ in range(5):
        again = recent.inject(again, section)
    assert again == once


# ── Topic hub back-links ─────────────────────────────────────────────────────

def test_topic_block_inserts_before_related_topics_and_is_idempotent():
    page = "<section>synthesis</section>\n<!-- AEO-RELATED-TOPICS:START -->\n<nav></nav>\n<!-- AEO-RELATED-TOPICS:END -->"
    block = vp.render_topic_voices_block([(_entry(), "Reading habits.")])
    once = vp.inject_topic_voices(page, block)
    assert once.index(vp.TOPIC_START) < once.index("AEO-RELATED-TOPICS:START")
    assert '<a href="/voices/test-writer/">Test Writer</a>: Reading habits.' in once
    assert vp.inject_topic_voices(once, block) == once
    assert vp.inject_topic_voices(once, "") == page


def test_topic_block_needs_anchor():
    assert vp.inject_topic_voices("<p>no anchor</p>", "<!-- x -->") is None


# ── Pilot data file ──────────────────────────────────────────────────────────

def test_pilot_data_has_the_five_all_reviewed():
    # Tom approved all five on 2026-11-12; abby-silva was retired (posting account).
    assert set(WRITERS) == {"dawn-sherillporter", "alex-harris", "brandon-corley",
                            "chandler-vannoy", "david-powlison"}
    assert all(w["reviewed"] is True for w in WRITERS.values())


def test_pilot_data_never_uses_em_dashes():
    raw = (ROOT / "data" / "voices" / "pilot.json").read_text(encoding="utf-8")
    assert "—" not in raw


def test_every_bio_has_a_source_link():
    for w in WRITERS.values():
        if w["bio"]:
            assert w["bio_sources"], w["slug"]
            assert all(s["url"].startswith("https://") for s in w["bio_sources"])


def test_start_here_counts():
    assert len(WRITERS["david-powlison"]["start_here"]) == 5
    assert WRITERS["david-powlison"]["page_kind"] == "where_to_start"
    for slug in ("alex-harris", "brandon-corley", "chandler-vannoy"):
        assert len(WRITERS[slug]["start_here"]) == 3


def test_reviewed_pilot_pages_are_indexable_and_in_sitemap():
    noindex = set(json.loads((ROOT / "frontend" / "voices_noindex.json").read_text()))
    sitemap = (ROOT / "docs" / "sitemap-voices.xml").read_text()
    for slug, w in WRITERS.items():
        assert not vp.needs_noindex(w), slug
        assert slug not in noindex, slug
        assert f"/voices/{slug}/<" in sitemap, slug
        assert "noindex" not in (ROOT / "docs" / "voices" / slug / "index.html").read_text()


def test_retired_posting_account_redirects_to_voices():
    noindex = json.loads((ROOT / "frontend" / "voices_noindex.json").read_text())
    assert "abby-silva" in noindex
    assert "/voices/abby-silva/<" not in (ROOT / "docs" / "sitemap-voices.xml").read_text()
    stub = (ROOT / "docs" / "voices" / "abby-silva" / "index.html").read_text()
    assert 'url=/voices/"' in stub and 'rel="canonical" href="https://www.christiancurator.com/voices/"' in stub


@pytest.mark.parametrize("slug", sorted(WRITERS))
def test_built_pilot_pages_are_static_and_dash_free(slug):
    page = (ROOT / "docs" / "voices" / slug / "index.html").read_text(encoding="utf-8")
    assert "—" not in page
    assert 'data-cc-voice-pilot="reviewed"' in page
    if slug in ("dawn-sherillporter", "brandon-corley", "chandler-vannoy"):
        assert page.count('class="cc-recent-item"') >= 1
