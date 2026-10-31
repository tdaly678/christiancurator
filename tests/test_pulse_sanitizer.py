"""Pulse copy never ships with em or en dashes (Tom's standing writing rule)."""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from curator import daily_summary  # noqa: E402
from curator.daily_summary import sanitize_pulse  # noqa: E402


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


def test_pulse_prompt_has_no_em_dashes_outside_the_ban():
    prompt = daily_summary.SUMMARY_PROMPT + daily_summary.HISTORY_SECTION_TEMPLATE
    lines = [l for l in prompt.splitlines() if "—" in l or "–" in l]
    assert lines == ["- No em dashes (—) or en dashes (–) anywhere. Use commas, periods, colons or parentheses"]
