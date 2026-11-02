"""Pulse copy never ships with em or en dashes (Tom's standing writing rule)
and never runs past 4 whole sentences."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from curator import daily_summary  # noqa: E402
from curator.daily_summary import limit_pulse_sentences, sanitize_pulse  # noqa: E402
from frontend.text import split_sentences  # noqa: E402


def test_sanitize_pulse_strips_em_dashes():
    text = ("TGC says the threat is doctrinal — bad theology quietly replacing good. "
            "A judge ordered access to detainees—[World](https://example.com) had it.")
    out = sanitize_pulse(text)
    assert "—" not in out and "–" not in out
    assert "doctrinal, bad theology" in out
    assert "[World](https://example.com)" in out


def test_sanitize_pulse_en_dash_ranges_become_hyphens():
    assert sanitize_pulse("Romans 9–11 matters – a lot.") == "Romans 9-11 matters, a lot."


def test_sanitize_pulse_handles_empty():
    assert sanitize_pulse("") == "" and sanitize_pulse(None) == ""


def test_prompt_asks_for_three_to_four_sentences():
    prompt = daily_summary.SUMMARY_PROMPT
    assert "3 to 4 complete sentences, never more than 4" in prompt
    assert "8 to 10 sentences" not in prompt
    example = prompt.split("---EXAMPLE START---")[1].split("---EXAMPLE END---")[0]
    assert len(split_sentences(" ".join(example.split()))) <= 4


def test_limit_keeps_short_pulse_unchanged():
    paras = ["One thing happened. Two things happened.", "Three things happened."]
    assert limit_pulse_sentences(paras) == paras


def test_limit_trims_to_four_whole_sentences_across_paragraphs():
    paras = ["First claim here. Second claim here. Third claim here.",
             "Fourth claim here. Fifth claim here. Sixth claim here."]
    out = limit_pulse_sentences(paras)
    assert out == ["First claim here. Second claim here. Third claim here.",
                   "Fourth claim here."]
    assert len(split_sentences(" ".join(out))) == 4


def test_limit_drops_paragraphs_past_the_cap():
    paras = ["A one. B two. C three. D four. E five.", "F six."]
    assert limit_pulse_sentences(paras) == ["A one. B two. C three. D four."]


def test_limit_never_cuts_mid_clause_and_keeps_end_punctuation():
    paras = ["Dr. Moore spoke, and the U.S. Senate listened. Was it enough? "
             "The PCA said no! Others agreed. Nobody else did."]
    out = limit_pulse_sentences(paras)
    assert out == ["Dr. Moore spoke, and the U.S. Senate listened. Was it enough? "
                   "The PCA said no! Others agreed."]
    assert out[0][-1] in ".!?"


def test_limit_does_not_split_inside_markdown_links():
    paras = ["[Why I Left. A Story](https://example.com/a.b?c=1) ran today. "
             "[World](https://wng.org/x.y) had it. Third. Fourth one. Fifth one."]
    out = limit_pulse_sentences(paras)
    assert out == ["[Why I Left. A Story](https://example.com/a.b?c=1) ran today. "
                   "[World](https://wng.org/x.y) had it. Third. Fourth one."]


def test_limit_handles_empty():
    assert limit_pulse_sentences([]) == []
    assert limit_pulse_sentences(["", "  "]) == []


def test_pulse_prompt_has_no_em_dashes_outside_the_ban():
    prompt = daily_summary.SUMMARY_PROMPT + daily_summary.HISTORY_SECTION_TEMPLATE
    lines = [l for l in prompt.splitlines() if "—" in l or "–" in l]
    assert lines == ["- No em dashes (—) or en dashes (–) anywhere. Use commas, periods, colons or parentheses"]
