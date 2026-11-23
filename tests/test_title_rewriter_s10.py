"""S10 (Nov 23 2026): title-rewriter options Tom approved from the S8 report.

1. Titles ending in "?" keep the publisher title (KEEP_QUESTION), never sent.
2. A question ends in "?" or opens with Why, How or What; nothing else.
3. XIV, ETS, IVP and UFC are acronyms, not shouting.
4. One summary line per run; unknown-entity rejections name the tokens.

Run: .venv/bin/python -m pytest tests/test_title_rewriter_s10.py
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
from curator.headline_voice import voice_adjustments  # noqa: E402


def _art(title, summary="A writer considers the question at length.",
         url="https://example.org/2026/11/piece", source="Example"):
    return {"title": title, "original_title": title, "summary": summary, "url": url,
            "source_name": source}


def _client(monkeypatch, reply=None, calls=None):
    def create(**kw):
        if calls is not None:
            calls.append(kw)
        if reply is None:
            raise AssertionError("Claude should not be called")
        return SimpleNamespace(content=[SimpleNamespace(text=reply)])
    monkeypatch.setattr(tr, "client", SimpleNamespace(messages=SimpleNamespace(create=create)))


# ── 1. Question titles are skipped, not sent ────────────────────────────────

@pytest.mark.parametrize("title", [
    "What Will We Remember in the Afterlife?",
    "Is the Church Ready for AI?",
    "Should Christians Celebrate Halloween?  ",
])
def test_question_title_is_kept(title):
    assert tr.keep_publisher_title(_art(title)) == "KEEP_QUESTION"


def test_question_title_is_skipped_not_sent(monkeypatch):
    _client(monkeypatch)
    stats = {}
    a = tr.rewrite_title(_art("What Will We Remember in the Afterlife?"), stats=stats)
    assert a["rewritten_title"] == "What Will We Remember in the Afterlife?"
    assert a["rewrite_skipped"] == "KEEP_QUESTION"
    assert "rewrite_rejected" not in a
    assert stats == {"skipped": 1}


@pytest.mark.parametrize("title", [
    "Why Paper Books Endure",
    "How the Reformers Read Romans",
    "When Democrats Show Up for Men",
])
def test_statement_without_question_mark_is_still_sent(title):
    assert tr.keep_publisher_title(_art(title)) is None


def test_other_keep_reasons_win_over_question():
    a = _art("Is the Church Ready for AI?", url="https://erlc.com/erlc-podcast/ready-for-ai/")
    assert tr.keep_publisher_title(a) == "KEEP_PODCAST"


# ── 2. Narrowed question detection ──────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "Why paper books endure", "How Churches Grow", "What the Creeds Teach",
    "Pastors Ask a Hard Question?",
])
def test_is_question(title):
    assert tr._is_question(title)


@pytest.mark.parametrize("title", [
    "When Democrats Show Up for Men",
    "Where the Church Meets the Poor",
    "Who Gets to Define Evangelical",
    "Which Bible Translation Pastors Trust",
    "Is Coming: A New Hymnal",
    "Are Churches Shrinking Fast",
    "Can Be Done: Rural Church Planting",
    "Could Revival Begin in the Pews",
    "Do Justice and Love Mercy",
    "Does Not Compute: Faith and Code",
    "Did Luther Mean It",
    "Will and Testament in Christian Estate Planning",
    "Would-Be Pastors Face Debt",
    "Should Have Known: A Memoir",
    "Was Gone, Now Found",
    "Were the Puritans Joyful",
    "Has Been Faithful: A Retrospective",
    "Have Mercy on Us",
])
def test_other_openers_without_question_mark_are_statements(title):
    assert not tr._is_question(title)


def test_modality_uses_narrowed_test():
    art = _art("When Democrats Show Up for Men",
               "Democrats are courting men voters, and churches notice men returning.")
    assert tr.fact_rejection("Democrats Court Men Voters", art) != "REWRITE_CHANGES_MODALITY"
    art = _art("Why paper books endure", "Digital reading has not displaced the printed page.")
    assert tr.fact_rejection("Readers Choose Paper Books Over Digital Alternatives",
                             art) == "REWRITE_CHANGES_MODALITY"


# ── 3. Acronyms ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title", [
    "Pope Leo XIV Addresses Bishops on Migration",
    "ETS Scholars Debate Inerrancy in San Diego",
    "IVP Releases a New Commentary on Romans",
    "UFC Fighter Credits Christ After Title Win",
])
def test_new_acronyms_do_not_shout(title):
    assert "DEMOTE_ALL_CAPS" not in voice_adjustments(title)


def test_other_caps_still_shout():
    assert "DEMOTE_ALL_CAPS" in voice_adjustments("Pastor Resigns After SHOCKING Abuse Report")


# ── 4. Logging ──────────────────────────────────────────────────────────────

def test_unknown_entity_log_names_the_token(monkeypatch, capsys):
    _client(monkeypatch, "Tim Keller Says Churches Rethink Membership")
    a = tr.rewrite_title(_art("Rethinking Church Membership",
                              "Membership matters more than many churches think."))
    assert a["rewrite_rejected"] == "REWRITE_UNKNOWN_ENTITY"
    out = capsys.readouterr().out
    assert "REWRITE_UNKNOWN_ENTITY: Tim, Keller" in out


def test_run_summary_line(monkeypatch, capsys):
    replies = iter(["Pastors Weigh Sabbath Rest",
                    "Tim Keller Says Churches Rethink Membership"])
    monkeypatch.setattr(tr, "client", SimpleNamespace(messages=SimpleNamespace(
        create=lambda **kw: SimpleNamespace(content=[SimpleNamespace(text=next(replies))]))))
    arts = [
        _art("Pastor, Take Your Sabbath Rest", "Pastors weigh sabbath rest and burnout."),
        _art("Rethinking Church Membership", "Membership matters more than many churches think."),
        _art("What Will We Remember in the Afterlife?"),
        _art("No Summary Here", summary=""),
    ]
    tr.rewrite_titles(arts, enabled=True)
    out = capsys.readouterr().out
    assert ("Title rewrites: 2 sent, 2 skipped, 1 accepted, 1 rejected, 0 errors") in out
