"""Tests for scripts/sweep_topic_dashes.py (S2 item 10: punctuation-only topic copy sweep)."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "sweep_topic_dashes", Path(__file__).resolve().parent.parent / "scripts" / "sweep_topic_dashes.py")
sweep_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sweep_mod)
fix_text, sweep = sweep_mod.fix_text, sweep_mod.sweep


def test_paired_aside_becomes_commas():
    assert fix_text("Topical preaching addresses subjects—marriage, anxiety—by drawing on texts.") == \
        "Topical preaching addresses subjects, marriage, anxiety, by drawing on texts."


def test_single_dash_before_conjunction_is_comma():
    assert fix_text("Baptism is one of two ordinances Jesus commanded — and evangelicals disagree.") == \
        "Baptism is one of two ordinances Jesus commanded, and evangelicals disagree."


def test_single_dash_before_explanation_is_colon():
    assert fix_text("Mission belongs primarily to God — the church participates.") == \
        "Mission belongs primarily to God: the church participates."


def test_ranges_and_compounds_become_hyphens():
    assert fix_text("Acts 17:2–3 and the Luther–Owen pattern") == "Acts 17:2-3 and the Luther-Owen pattern"


def test_quoted_text_is_left_alone():
    s = "He wrote “this is the end — or not” in 1520."
    assert fix_text(s) == s


def test_publisher_link_text_and_builder_blocks_untouched():
    html = ('<p>One — two.</p><a href="https://example.org/x">Pastor, Don’t Quit—Learn to Lament</a>'
            '<!-- CC-TOPIC-TOP:START --><p>A — b</p><!-- CC-TOPIC-TOP:END -->')
    out = sweep(html)
    assert "<p>One: two.</p>" in out
    assert "Quit—Learn" in out
    assert "<p>A — b</p>" in out


def test_outlet_suffix_label_becomes_parentheses():
    html = '<a href="https://www.thegospelcoalition.org/essay/x/">Justification — TGC Essay</a>'
    assert sweep(html) == '<a href="https://www.thegospelcoalition.org/essay/x/">Justification (TGC Essay)</a>'


def test_idempotent():
    html = "<p>Prayer is the most basic act — and the most mysterious.</p>"
    assert sweep(sweep(html)) == sweep(html)
