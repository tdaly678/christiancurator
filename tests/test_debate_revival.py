"""The Debate revival (S2, Nov 22 2026): candidates on max(importance, depth),
pairing after the lead block, the relaxed shared-name rule, history fields and
the job summary. No live Claude calls: the client is mocked.
"""
import json
from types import SimpleNamespace

import curator.point_counterpoint as pc
from curator.point_counterpoint import (build_point_counterpoint, debate_candidates,
                                        debate_summary_lines, validate_pair,
                                        write_debate_summary)
from frontend.layout import build_homepage_layout, outbound_urls
from output import history_row

THESES = {"thesis_a": "The SBC should amend its constitution to bar women pastors.",
          "thesis_b": "Writing the Law amendment into the constitution would split cooperation."}


def art(url, title, source, perspective="neutral", importance=5.0, depth=5.0, **kw):
    return {"url": url, "title": title, "source_name": source, "perspective": perspective,
            "importance": importance, "final_score": importance, "score": importance,
            "depth": depth, "tags": kw.pop("tags", ["theology"]), **kw}


# ── validate_pair: the relaxed shared-name rule ─────────────────────────────

ESSAY_A = art("https://9marks.org/law", "Why Southern Baptists Need the Law Amendment in Dallas",
              "9Marks", "supportive", 5, 7)
ESSAY_B = art("https://baptistnews.com/law", "The Law Amendment Would Hurt Southern Baptists in Dallas",
              "Baptist News Global", "neutral", 5, 7)


def test_shared_names_with_stated_theses_now_pair():
    assert validate_pair(ESSAY_A, ESSAY_B, THESES) is None


def test_shared_names_without_theses_still_rejected():
    assert validate_pair(ESSAY_A, ESSAY_B).startswith("same story")


def test_news_report_plus_reaction_still_rejected():
    news = {**ESSAY_B, "perspective": "news"}
    assert validate_pair(ESSAY_A, news, THESES).startswith("same story")


def test_same_stance_and_same_source_still_rejected():
    assert validate_pair(ESSAY_A, {**ESSAY_B, "perspective": "supportive"}, THESES) == "same stance"
    assert validate_pair(ESSAY_A, {**ESSAY_B, "source_name": "9Marks"}, THESES) == "same source"


def test_oct30_junk_pairs_still_rejected_with_theses():
    # Live Oct 30 2026: Pew's release vs Christian Post's write-up (both neutral),
    # and two news reports of the Highland Park UMC fight.
    pew = art("https://pew.org/r", "Religion Remains Stable in the U.S., With Mixed Signals for Young Adults",
              "Pew Research", "neutral", summary="Pew Research Center data show stability.")
    cp = art("https://cp.com/r", "Religious identification, service attendance remains steady: Pew",
             "The Christian Post", "neutral", summary="A new Pew Research Center survey.")
    umc1 = art("https://cp.com/u", "UMC Bishop appoints new pastor to Texas megachurch", "The Christian Post", "news")
    umc2 = art("https://rns.org/u", "UMC bishop removes ministers from Dallas' Highland Park", "Religion News Service", "news")
    assert validate_pair(pew, cp, THESES) == "both straight reporting"
    assert validate_pair(umc1, umc2, THESES) is not None


# ── candidates ──────────────────────────────────────────────────────────────

def test_candidates_use_the_stronger_axis_and_list_argued_pieces_first():
    essay = art("https://e/1", "Essay", "Mere Orthodoxy", "critical", importance=4, depth=7)
    news = art("https://n/1", "News", "RNS", "news", importance=8, depth=3)
    weak = art("https://w/1", "Weak", "Blog", "supportive", importance=5, depth=5)
    shown = art("https://s/1", "Shown", "CT", "supportive", importance=9, depth=9, shown_yesterday=True)
    media = art("https://m/1", "Media", "Pod", "supportive", importance=9, depth=9, role="media")
    got = debate_candidates([news, weak, essay, shown, media])
    assert [a["url"] for a in got] == ["https://e/1", "https://n/1"]


class _Client:
    def __init__(self, payload):
        self.payload = payload
        self.prompt = ""
        self.messages = self

    def create(self, **kw):
        self.prompt = kw["messages"][0]["content"]
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(self.payload))])


def test_build_point_counterpoint_with_mocked_claude(monkeypatch):
    a = {**ESSAY_A}
    b = {**ESSAY_B}
    c = art("https://ct.com/c", "A Third Essay on Law", "Christianity Today", "supportive", 5, 7)
    payload = [
        # Candidates are ordered argued first: [0] 9Marks, [1] CT (both supportive), [2] BNG.
        {"point_index": 0, "counterpoint_index": 2, "topic": "Should the SBC adopt the Law amendment?", **THESES},
        {"point_index": 0, "counterpoint_index": 1, "topic": "x", **THESES},
    ]
    client = _Client(payload)
    monkeypatch.setattr(pc, "_get_client", lambda: client)
    pairs = build_point_counterpoint([b, a, c])
    assert "[0] Why Southern Baptists" in client.prompt
    assert [(p["point"]["url"], p["counterpoint"]["url"]) for p in pairs] == [(a["url"], b["url"])]
    assert pairs[0]["thesis_a"] == THESES["thesis_a"]
    assert pc.LAST_RUN["candidates"] == 3 and pc.LAST_RUN["proposed"] == 2
    assert pc.LAST_RUN["accepted"] == 1
    assert [n["reason"] for n in pc.LAST_RUN["rejected"]] == ["same stance"]


def test_claude_failure_is_recorded(monkeypatch):
    def boom():
        raise RuntimeError("no credit")
    monkeypatch.setattr(pc, "_get_client", boom)
    monkeypatch.setattr(pc, "record_failure", lambda *a, **k: None)
    assert build_point_counterpoint([ESSAY_A, ESSAY_B]) == []
    assert "no credit" in pc.LAST_RUN["error"]


# ── layout: pairing after the lead block ────────────────────────────────────

def _pool():
    lead = art("https://lead/1", "Lead Essay Argues for Sabbath Rest", "Desiring God", "supportive", 9, 9)
    titles = ["Sabbath Keeping Shapes a Restless Church", "Elders Should Shepherd Before They Govern",
              "Hymns Teach Doctrine Better Than Sermons", "Lament Belongs in Sunday Worship",
              "Hospitality Is a Form of Evangelism"]
    sub = [art(f"https://sub/{i}", t, f"Outlet{i}", "neutral", 8 - i * 0.1, 6)
           for i, t in enumerate(titles)]
    rival = art("https://rival/1", "Rival Essay Rejects the Sublead Claim", "Rival Outlet", "critical", 5, 7)
    filler = [art(f"https://f/{i}", t, f"F{i}", "news", 4, 3, tags=["news"])
              for i, t in enumerate(["Court Hears Ohio School Case", "Survey Finds Fewer Weddings",
                                     "Seminary Names New President", "Floods Hit Kerala Parishes",
                                     "Publisher Cuts Print Run", "Mission Board Reports Growth"])]
    return lead, sub, rival, [lead, *sub, rival, *filler]


def _pairing(a, b):
    return {"point": a, "counterpoint": b, "topic": "Q?", "thesis_a": "Sabbath rest is commanded.",
            "thesis_b": "The fourth commandment does not bind Christians the same way."}


def test_pair_touching_a_sublead_renders_and_the_slot_backfills():
    lead, sub, rival, pool = _pool()
    before = build_homepage_layout(pool)
    assert sub[0] in before["subleads"]
    layout = build_homepage_layout(pool, [_pairing(sub[0], rival)])
    assert len(layout["debate"]) == 1
    assert layout["lead"]["url"] == lead["url"]
    assert sub[0] not in layout["subleads"] and len(layout["subleads"]) == 3
    urls = outbound_urls(layout)
    assert len(urls) == len(set(urls))


def test_pair_touching_the_lead_is_dropped_with_a_note():
    lead, sub, rival, pool = _pool()
    layout = build_homepage_layout(pool, [_pairing(lead, rival)])
    assert layout["debate"] == []
    assert layout["debate_notes"][0]["reason"] == "a side is the Lead"


def test_layout_validation_failures_are_noted():
    lead, sub, rival, pool = _pool()
    same = {**rival, "source_name": sub[1]["source_name"]}
    pool = [a for a in pool if a is not rival] + [same]
    layout = build_homepage_layout(pool, [_pairing(sub[1], same)])
    assert layout["debate"] == []
    assert layout["debate_notes"][0]["reason"] == "same source"


# ── job summary and history ─────────────────────────────────────────────────

def test_summary_lists_every_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(pc, "LAST_RUN", {"candidates": 20, "proposed": 2, "accepted": 0, "error": "",
                                         "rejected": [{"reason": "same stance", "a": "A | x", "a_source": "S1",
                                                       "b": "B", "b_source": "S2"}]})
    layout = {"debate": [], "debate_notes": [{"reason": "a side is the Lead", "a": "C", "a_source": "S3",
                                              "b": "D", "b_source": "S4"}]}
    lines = debate_summary_lines(layout)
    text = "\n".join(lines)
    assert "Candidates sent to Claude: 20" in text and "Pairs on the page: 0." in text
    assert "| same stance | A / x (S1) | B (S2) |" in text
    assert "a side is the Lead" in text
    out = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))
    write_debate_summary(layout)
    assert "## The Debate" in out.read_text()
    assert "—" not in text and "–" not in text


def test_history_rows_keep_perspective_and_opposing_pair():
    row = history_row({"url": "https://x/1", "title": "T", "perspective": "critical",
                       "opposing_pair": True}, "2026-11-22")
    assert row["perspective"] == "critical" and row["opposing_pair"] is True
    row = history_row({"url": "https://x/2", "title": "T"}, "2026-11-22")
    assert row["perspective"] is None and "opposing_pair" not in row
