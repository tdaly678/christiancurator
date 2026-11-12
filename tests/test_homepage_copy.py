"""Homepage copy quick wins (2026-11-01): Pulse line, card blurbs, live counts."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frontend.layout import pulse_line
from frontend.site_stats import archive_stats, site_stats
from frontend.text import complete_blurb, first_sentence, split_sentences


# ── pulse_line ───────────────────────────────────────────────────────────

LONG_FIRST = ("The Southern Baptist Convention's executive committee voted on Tuesday to "
              "send the proposed amendment on women pastors back to messengers for a second "
              "reading next June, setting up another floor fight in Orlando.")


def test_pulse_line_keeps_whole_first_sentence_past_twenty_words():
    summary = {"paragraphs_plain": [LONG_FIRST + " Second sentence here."]}
    line = pulse_line(summary)
    assert line == LONG_FIRST
    assert len(line.split()) > 20
    assert not line.endswith("…")


def test_pulse_line_falls_back_to_html_and_strips_tags():
    summary = {"paragraphs_html": ["<p>The <strong>PCA</strong> met. More follows.</p>"]}
    assert pulse_line(summary) == "The PCA met."


def test_pulse_line_ignores_abbreviations_and_initials():
    summary = {"paragraphs_plain": ["Dr. Moore and J. I. Packer shaped the U.S. Senate debate. Next."]}
    assert pulse_line(summary) == "Dr. Moore and J. I. Packer shaped the U.S. Senate debate."


def test_pulse_line_removes_em_dashes():
    summary = {"paragraphs_plain": ["Two stories lead — one on the PCA. Then more."]}
    line = pulse_line(summary)
    assert "—" not in line and line == "Two stories lead, one on the PCA."


def test_pulse_line_empty():
    assert pulse_line(None) == ""
    assert pulse_line({}) == ""
    assert pulse_line({"paragraphs_plain": [""]}) == ""


# ── complete_blurb ───────────────────────────────────────────────────────

def test_blurb_fits_unchanged():
    assert complete_blurb("Short and complete.", 160) == "Short and complete."


def test_blurb_keeps_whole_sentences():
    text = ("What the pro-life movement owes women post-Roe, and whether evangelical churches "
            "are providing enough support. Explore biblical perspectives and practical responses.")
    out = complete_blurb(text, 160)
    assert out == ("What the pro-life movement owes women post-Roe, and whether evangelical "
                   "churches are providing enough support.")


def test_blurb_cuts_after_full_clause_with_ellipsis():
    text = ("Evangelicals debate whether contemplative practices are biblical, whether they "
            "borrow from mysticism, and whether churches should teach them at all to new believers")
    out = complete_blurb(text, 120)
    assert out == ("Evangelicals debate whether contemplative practices are biblical, "
                   "whether they borrow from mysticism…")
    assert out[:-1] in text and text[len(out) - 1] == ","


def test_blurb_never_cuts_mid_word():
    text = "One very long sentence without any clause breaks that keeps going well past the limit"
    out = complete_blurb(text, 30)
    assert out == text  # whole sentence beats a mid-word cut


def test_blurb_unescapes_entities_and_drops_dashes():
    out = complete_blurb("Faith &amp; work — a guide.", 160)
    assert out == "Faith & work, a guide."


def test_split_sentences_basic():
    assert split_sentences("One. Two? Three!") == ["One.", "Two?", "Three!"]
    assert first_sentence("") == ""


# ── site stats ───────────────────────────────────────────────────────────

def test_archive_stats_counts_day_pages(tmp_path):
    for name in ("2026-03-22", "2026-04-01", "not-a-date"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "index.html").write_text("x")
    (tmp_path / "2026-05-01").mkdir()  # no index.html, not an edition
    stats = archive_stats(tmp_path)
    assert stats == {"count": 2, "since": date(2026, 3, 22)}


def test_site_stats_live_counts_are_positive():
    stats = site_stats()
    assert stats["source_count"] > 0
    assert stats["edition_count"] > 0
    assert stats["voices_count"] > 0


# ── masthead claim (Tom, 2026-11-12) ─────────────────────────────────────

def test_masthead_claim_names_no_source_count():
    root = Path(__file__).resolve().parent.parent
    for path in (root / "frontend" / "template.html", root / "docs" / "index.html"):
        html = path.read_text(encoding="utf-8")
        assert '<p class="cc-masthead-claim">A daily ranked front page from across the evangelical web.</p>' in html
        assert "evangelical sources.</p>" not in html
