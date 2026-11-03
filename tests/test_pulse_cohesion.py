"""Pulse cohesion (2026-11-03): every sentence advances the theme in sentence 1.

On Nov 3 2026 the Pulse opened on election eve and church trust, moved to abuse
and pastoral power, then dropped in "First Things is running a piece on global
Christian martyrs" and forced a closing bridge. These tests lock the prompt
language that forbids that, alongside the rules it must keep.

Run: .venv/bin/python -m pytest tests/test_pulse_cohesion.py
"""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from curator import daily_summary  # noqa: E402

PROMPT = daily_summary.SUMMARY_PROMPT


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_every_sentence_must_advance_theme():
    flat = _flat(PROMPT)
    assert "Every sentence must advance the theme stated in sentence 1." in flat


def test_unrelated_articles_are_omitted_not_bridged():
    flat = _flat(PROMPT)
    assert ("If an article cannot honestly be tied to the theme, leave it out of the "
            "Pulse entirely.") in flat
    assert ("Never name-drop an article mid-paragraph and then invent a bridge back "
            "to the theme.") in flat
    assert "Never close with a sentence whose only job is to force a link" in flat


def test_theme_chosen_before_articles():
    assert "Choose your articles AFTER you choose the theme." in _flat(PROMPT)


def test_nov_3_failure_example_present():
    flat = _flat(PROMPT)
    assert "global Christian martyrs" in flat
    assert "should have been left out" in flat


def test_cohesion_rule_follows_theme_first_rule():
    i_theme = PROMPT.index("CRITICAL: State the main theme in the very first sentence.")
    i_cohesion = PROMPT.index("ONE THEME, EVERY SENTENCE")
    i_articles = PROMPT.index("TODAY'S ARTICLES (title")
    assert i_theme < i_cohesion < i_articles


def test_existing_style_rules_kept():
    flat = _flat(PROMPT)
    assert "2-paragraph dispatch (8 to 10 sentences total)" in flat
    assert "STUDY THIS EXAMPLE CAREFULLY" in flat
    assert "No em dashes" in flat
    assert '"paragraphs": ["paragraph 1 text", "paragraph 2 text"]' in PROMPT


def test_history_callbacks_must_serve_theme():
    assert "must advance today's theme" in _flat(daily_summary.HISTORY_SECTION_TEMPLATE)


def test_prompt_still_formats():
    out = PROMPT.format(article_list="- T | S | https://x.example", history_section="")
    assert "{" not in out.split("Respond with a JSON object")[0]
