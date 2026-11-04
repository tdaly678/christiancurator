"""Title rewriting is on for the daily product, in RealClear house voice (2026-11-04).

The daily workflow sets CC_REWRITE_TITLES=1 on the pipeline step. The rewrite
prompt asks for understated RealClearPolitics / RealClearReligion headlines
that make a claim, and every rewrite is gated by
headline_voice.rewrite_rejection(): a dated column, listicle, claimless label,
promo, emoji, issue number or shout falls back to the cleaned original.

Run: .venv/bin/python -m pytest tests/test_title_rewriter_voice.py
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from curator import title_rewriter as tr  # noqa: E402
from curator.headline_voice import (  # noqa: E402
    HARD_REJECT_DATED_COLUMN, headline_has_claim, rewrite_rejection,
)

WORKFLOW = ROOT / ".github" / "workflows" / "daily_run.yml"
WNG = "The World and Everything in It: November 3, 2026"


def _flat(text: str) -> str:
    return " ".join(text.split())


# ── Workflow flag ────────────────────────────────────────────────────────────

def _pipeline_step() -> str:
    text = WORKFLOW.read_text()
    start = text.index("- name: Run pipeline")
    end = text.index("- name:", start + 1)
    return text[start:end]


def test_workflow_enables_rewrites_on_pipeline_step():
    step = _pipeline_step()
    assert "CC_REWRITE_TITLES: '1'" in step
    assert step.index("env:") < step.index("CC_REWRITE_TITLES") < step.index("run: python3 main.py")


def test_flag_is_parsed_as_enabled(monkeypatch):
    import importlib
    monkeypatch.setenv("CC_REWRITE_TITLES", "1")
    mod = importlib.reload(tr)
    try:
        assert mod.REWRITE_TITLES_ENABLED is True
    finally:
        monkeypatch.delenv("CC_REWRITE_TITLES")
        importlib.reload(tr)


def test_comments_no_longer_say_experiments_only():
    for path in ("curator/title_rewriter.py", "curator/headline_voice.py"):
        text = (ROOT / path).read_text()
        assert "experiments only" not in text
        assert "not the daily product" not in text
        assert "stays off unless CC_REWRITE_TITLES" not in text
    assert "ON for the daily product" in (ROOT / "curator/title_rewriter.py").read_text()


# ── Prompt constraints ───────────────────────────────────────────────────────

PROMPT = _flat(tr.REWRITE_PROMPT)


def test_prompt_names_realclear_house_voice():
    assert "RealClear Media house voice" in PROMPT
    assert "RealClearPolitics" in PROMPT and "RealClearReligion" in PROMPT
    assert "understated" in PROMPT.lower()
    assert "Make a claim" in PROMPT


@pytest.mark.parametrize("rule", [
    "No exclamation points, emoji, em dashes or en dashes",
    "No issue, episode or volume numbers, and no dates",
    "No promo or launch copy",
    "No newsletter or first person voice",
    "No listicles",
    "Never return a dated show or column title",
    "The World and Everything in It: November 3, 2026",
    "drop the show name and the date",
    "Never return a bare label",
    "Do NOT invent facts",
])
def test_prompt_rules(rule):
    assert rule in PROMPT


def test_prompt_drops_punchy_style_that_fought_the_voice_engine():
    lower = PROMPT.lower()
    for phrase in ("punchy, direct, and compelling", "stop scrolling", "editorial edge", "here's what's at stake"):
        assert phrase not in lower
    for dash in ("\u2014", "\u2013"):
        assert dash not in tr.REWRITE_PROMPT


def test_prompt_formats():
    out = tr.REWRITE_PROMPT.format(title="T", summary="S")
    assert "Original title: T" in out and "Article summary: S" in out


# ── Gate ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("candidate", [
    WNG,
    "Works & Wonders (November 1)",
    "Monday, November 3, 2026",
])
def test_dated_column_rewrites_rejected(candidate):
    assert rewrite_rejection(candidate, WNG) == HARD_REJECT_DATED_COLUMN


def test_rewrite_keeping_dated_show_name_rejected():
    assert rewrite_rejection("The World and Everything in It: Court Hears Charter Case",
                             WNG) == "REWRITE_KEEPS_COLUMN_NAME"


@pytest.mark.parametrize("candidate,reason", [
    ("The Tyranny of Preferences", "DEMOTE_CLAIMLESS_SHORT"),
    ("5 Ways Pastors Can Use AI Wisely", "REWRITE_LISTICLE"),
    ("Seven Reasons Churches Are Shrinking", "REWRITE_LISTICLE"),
    ("Pastor Resigns After Abuse Report \U0001F64F", "HARD_REJECT_EMOJI"),
    ("New Commentary on Romans Is Out Now", "HARD_REJECT_PROMO"),
    ("Issue 12: Churches Weigh AI Tools", "HARD_REJECT_ISSUE_NUMBER"),
    ("Pastor Resigns After SHOCKING Abuse Report", "DEMOTE_ALL_CAPS"),
    ("Pastor Resigns After Abuse Report!", "DEMOTE_EXCLAIM"),
    ("What I'm Reading on Church Planting This Fall", "DEMOTE_FIRST_PERSON_META"),
    ("Review: A New Biography of Calvin Arrives", "REVIEW_SOFT"),
])
def test_off_voice_rewrites_rejected(candidate, reason):
    assert rewrite_rejection(candidate) == reason


@pytest.mark.parametrize("candidate", [
    "Supreme Court Weighs Faith-Based Charter School Case",
    "SBC Messengers Vote to Expel Church Over Women Pastors",
    "Why Evangelicals Are Leaving the Megachurch",
])
def test_realclear_rewrites_pass(candidate):
    assert rewrite_rejection(candidate, WNG) is None


def _article(title, source="World Magazine", summary="The Supreme Court heard a charter case."):
    return {"title": title, "source_name": source, "summary": summary}


def _fake_client(monkeypatch, reply):
    msg = SimpleNamespace(content=[SimpleNamespace(text=reply)])
    fake = SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: msg))
    monkeypatch.setattr(tr, "client", fake)


def test_dated_rewrite_falls_back_to_cleaned_original(monkeypatch):
    _fake_client(monkeypatch, "The World and Everything in It: November 4, 2026")
    a = tr.rewrite_title(_article(WNG))
    assert a["rewritten_title"] == WNG
    assert a["rewrite_rejected"] == HARD_REJECT_DATED_COLUMN
    assert not headline_has_claim(a)


def test_claimless_rewrite_falls_back_to_cleaned_original(monkeypatch):
    _fake_client(monkeypatch, "The Tyranny of Preferences")
    a = tr.rewrite_title(_article("Why Church Preferences Divide Congregations \u2014 Here's Why",
                                  source="Mere Orthodoxy"))
    assert a["rewritten_title"] == "Why Church Preferences Divide Congregations"
    assert a["rewrite_rejected"] == "DEMOTE_CLAIMLESS_SHORT"


def test_good_rewrite_of_dated_show_is_accepted(monkeypatch):
    _fake_client(monkeypatch, '"Supreme Court Weighs Faith-Based Charter School Case"')
    a = tr.rewrite_title(_article(WNG))
    assert a["rewritten_title"] == "Supreme Court Weighs Faith-Based Charter School Case"
    assert "rewrite_rejected" not in a
    assert headline_has_claim(a)


def test_rewrite_dashes_are_cleaned(monkeypatch):
    _fake_client(monkeypatch, "Churches Leave the PCA \u2014 Elders Cite Doctrine")
    a = tr.rewrite_title(_article("Some Churches Are Leaving", source="Baptist Press"))
    assert "\u2014" not in a["rewritten_title"] and "\u2013" not in a["rewritten_title"]


def test_no_summary_keeps_cleaned_original():
    a = tr.rewrite_title(_article("Texas Pastor Resigns | Baptist Press",
                                  source="Baptist Press", summary=""))
    assert a["rewritten_title"] == "Texas Pastor Resigns"


def test_api_error_keeps_cleaned_original(monkeypatch):
    def boom(**kw):
        raise RuntimeError("down")
    monkeypatch.setattr(tr, "client", SimpleNamespace(messages=SimpleNamespace(create=boom)))
    monkeypatch.setattr(tr, "record_failure", lambda *a, **k: None)
    a = tr.rewrite_title(_article("Pastor Resigns After Report \u2014 Board Responds",
                                  source="Baptist Press"))
    assert a["rewritten_title"] == "Pastor Resigns After Report, Board Responds"
