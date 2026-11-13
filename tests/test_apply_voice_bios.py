"""Tests for scripts/apply_voice_bios.py (overnight Nov 12 2026)."""
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import apply_voice_bios as avb  # noqa: E402

ROW = {
    "slug": "jane-doe", "decision": "bio", "name": "Jane Doe",
    "bio": "Jane Doe is pastor of First Church, according to its staff page (checked November 2026).",
    "role": "Pastor", "affiliation": "First Church", "website": "https://first.example/staff/",
    "books": ["A Real Book"], "deceased": False,
    "bio_sources": ["https://first.example/staff/", "https://first.example/staff/"],
}


def test_check_row_refuses_unsourced_and_dashed_rows():
    assert avb.check_row(ROW) is None
    assert avb.check_row({**ROW, "bio_sources": []}) == "no bio_sources"
    assert avb.check_row({**ROW, "bio": "Jane Doe — pastor."}) == "dash in bio"
    assert avb.check_row({**ROW, "role": "Pastor – Teacher"}) == "dash in role"
    assert avb.check_row({**ROW, "bio": ""}) == "empty bio"
    assert avb.check_row({"slug": "x", "decision": "noindex"}) is None
    assert avb.check_row({"slug": "x", "decision": "maybe"}).startswith("unknown decision")


def test_update_record_drops_unsourced_fields():
    entry = {"slug": "jane-doe", "name": "Jane Doe", "bio": "old", "role": "Old",
             "education": "Invented U", "faqs": [{"q": "?", "a": "!"}], "denomination": "X",
             "tradition": "Y", "known_for": "Z", "current_role": "W",
             "books": [{"title": "Unsourced", "amazon_url": "u"}]}
    out = avb.update_record(entry, ROW)
    assert out["bio"] == ROW["bio"] and out["role"] == "Pastor"
    assert out["education"] == ""
    for key in ("faqs", "denomination", "tradition", "known_for", "current_role"):
        assert key not in out
    assert [b["title"] for b in out["books"]] == ["A Real Book"]
    assert out["bio_sources"] == ["https://first.example/staff/"]
    assert out["name"] == "Jane Doe"


def test_refresh_card_updates_role_and_teaser_only_for_slug():
    html = ('<a href="/voices/jane-doe/" class="cc-voice-card"><div class="cc-voice-card-role">Old</div>\n'
            '<div class="cc-voice-card-teaser">old teaser</div></a>'
            '<a href="/voices/other/" class="cc-voice-card"><div class="cc-voice-card-role">Keep</div>\n'
            '<div class="cc-voice-card-teaser">keep</div></a>')
    out = avb.refresh_card(html, {"slug": "jane-doe", "role": "Pastor", "bio": ROW["bio"]})
    assert ">Pastor<" in out and "old teaser" not in out
    assert ">Keep<" in out and ">keep<" in out


def test_refresh_books_and_meta_box_show_only_sourced_facts():
    soup = BeautifulSoup(
        '<main><p class="cc-voice-bio">b</p><div class="cc-voice-meta">'
        '<div class="cc-meta-item"><span class="cc-meta-label">Education</span>'
        '<span class="cc-meta-value">Invented U</span></div></div>'
        '<div class="cc-voice-section"><div class="cc-section-label">Notable Books</div>'
        '<div class="cc-books-list"><a class="cc-book-item">Unsourced</a></div></div></main>', "html.parser")
    entry = avb.update_record({"slug": "jane-doe", "name": "Jane Doe"}, {**ROW, "books": []})
    avb.refresh_meta_box(soup, entry)
    avb.refresh_books(soup, entry)
    text = soup.get_text(" ")
    assert "Invented U" not in text and "Unsourced" not in text and "Notable Books" not in text
    assert "First Church" in text and "first.example/staff" in text


def test_clip_cuts_on_a_word():
    assert avb.clip("one two three four", 12) == "one two..."
    assert avb.clip("short", 50) == "short"
