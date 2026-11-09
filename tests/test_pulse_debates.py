"""Pulse as a survey of evangelical debates (2026-11-08).

Tom: "The pulse seems to have skewed pretty negative and overly focused on
scandals. Move it more positive, less newspaper headlines and more about the
kinds of debates (philosophical, theological, praxis) going on in the Christian
publishing world." These tests lock the prompt framing and the source
selection that feeds it.

Run: .venv/bin/python -m pytest tests/test_pulse_debates.py
"""
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from curator import daily_summary as ds  # noqa: E402

PROMPT = ds.SUMMARY_PROMPT


def _flat(text: str) -> str:
    return " ".join(text.split())


def _art(title, source="Src", score=7.0, depth=5.0, perspective="neutral",
         tags=None, cluster="unique", **kw):
    return {"title": title, "source_name": source, "url": f"https://x.example/{title}",
            "final_score": score, "depth": depth, "perspective": perspective,
            "tags": tags or ["theology"], "topic_cluster": cluster, **kw}


# ── Prompt framing ───────────────────────────────────────────────────────────

def test_prompt_frames_pulse_as_debate_survey():
    flat = _flat(PROMPT)
    assert "surveying the live conversations in evangelical publishing" in flat
    assert "not a news roundup" in flat
    for kind in ("theological questions", "philosophical and cultural arguments",
                 "praxis (church life, ministry, discipleship, family, mission)"):
        assert kind in flat


def test_prompt_names_positions_and_who_argues_them():
    flat = _flat(PROMPT)
    assert "Name the positions being argued and who is arguing them" in flat
    assert "Never invent a position or a disagreement" in flat


def test_prompt_prefers_essays_over_news():
    assert "Lean on essays, opinion, reviews and long-form pieces" in _flat(PROMPT)


def test_prompt_tone_hopeful_and_scandal_never_leads():
    flat = _flat(PROMPT)
    assert "hopeful and constructive, never alarmist" in flat
    assert ("Scandal, abuse, lawsuit, resignation and crisis stories must not lead "
            "the Pulse.") in flat
    assert "clearly the dominant story of the day" in flat
    assert "one sober clause at most" in flat
    assert "never a scandal or a crisis" in flat


def test_prompt_keeps_voice_and_promo_rules():
    flat = _flat(PROMPT)
    assert "Understated RealClear voice" in flat
    assert "no promo language" in flat
    assert "no exclamation points" in flat


def test_framing_precedes_example_and_articles():
    i_what = PROMPT.index("WHAT THE PULSE IS")
    i_tone = PROMPT.index("TONE:")
    i_example = PROMPT.index("---EXAMPLE START---")
    i_articles = PROMPT.index("TODAY'S ARTICLES (title")
    assert i_what < i_tone < i_example < i_articles


def test_example_has_no_scandal_language():
    example = PROMPT[PROMPT.index("---EXAMPLE START---"):PROMPT.index("---EXAMPLE END---")]
    assert not ds.SCANDAL_RE.search(example)


def test_example_keeps_prior_length():
    example = PROMPT[PROMPT.index("---EXAMPLE START---") + 19:
                     PROMPT.index("---EXAMPLE END---")]
    sentences = [s for s in ds._SENTENCE_SPLIT_RE.split(" ".join(example.split())) if s]
    assert 8 <= len(sentences) <= 10


# ── Selection ────────────────────────────────────────────────────────────────

def test_scandal_detection():
    assert ds.is_scandal(_art("Pastor resigns after misconduct allegations"))
    assert ds.is_scandal(_art("Whistleblower: ministry flagged grooming cases"))
    assert ds.is_scandal(_art("What Led to the Magazine's Crisis?"))
    assert not ds.is_scandal(_art("A Charged Debate Over Infant Baptism"))
    assert not ds.is_scandal(_art("Why the Ascension Matters for Anthropology"))


def test_essays_outrank_higher_importance_news():
    news = [_art(f"Denomination votes on item {i}", score=9.0, depth=2.0,
                 perspective="news", tags=["news"]) for i in range(8)]
    essays = [_art(f"On the doctrine of grace part {i}", score=6.5, depth=8.0)
              for i in range(8)]
    picked = ds.select_pulse_candidates(news + essays)
    assert picked[0]["title"].startswith("On the doctrine")
    assert sum(ds.is_news_report(a) for a in picked) <= ds.PULSE_MAX_NEWS
    assert all(e in picked for e in essays)


def test_non_dominant_scandal_is_excluded():
    pool = [_art("Top essay on prayer", score=9.5, depth=8.0)] + [
        _art(f"Essay {i}", score=6.0, depth=6.0) for i in range(6)]
    pool.append(_art("Pastor resigns amid lawsuit", score=8.0, depth=3.0,
                     perspective="news", tags=["news"]))
    titles = [a["title"] for a in ds.select_pulse_candidates(pool)]
    assert "Pastor resigns amid lawsuit" not in titles


def test_dominant_scandal_kept_once():
    pool = [_art(f"Essay {i}", score=6.0, depth=6.0) for i in range(6)]
    for src in ("RNS", "CT", "WORLD"):
        pool.append(_art(f"{src}: Ministry abuse report released", source=src,
                         score=8.0, depth=3.0, perspective="news",
                         tags=["news"], cluster="ministry_abuse_report"))
    picked = ds.select_pulse_candidates(pool)
    assert sum(ds.is_scandal(a) for a in picked) == 1


def test_top_story_scandal_counts_as_dominant():
    top = _art("Seminary president ousted", score=9.9, depth=3.0)
    pool = [top] + [_art(f"Essay {i}", score=6.0, depth=6.0) for i in range(6)]
    assert top in ds.select_pulse_candidates(pool)


def test_selection_respects_limit_and_zero_scores():
    pool = [_art(f"Essay {i}", score=6.0, depth=6.0) for i in range(30)]
    pool.append(_art("Zero", score=0, depth=9.0))
    picked = ds.select_pulse_candidates(pool)
    assert len(picked) == ds.PULSE_MAX_ITEMS
    assert all(a["title"] != "Zero" for a in picked)


def test_missing_depth_falls_back_to_importance():
    assert ds.pulse_rank(_art("x", score=6.0, depth=None)) == 6.0


def test_format_marks_kind_author_and_cleans_excerpt():
    a = _art("On Grace", source="Mere Orthodoxy", author="Jake Meador",
             summary="<p>Grace &amp; nature — again.</p> The post On Grace "
                     "appeared first on Mere Orthodoxy.")
    line = ds.format_pulse_article(a)
    assert "| Mere Orthodoxy, Jake Meador | essay |" in line
    assert "Grace & nature" in line
    assert "—" not in line and "appeared first" not in line
    news = _art("Board votes", perspective="news", tags=["news"])
    assert "| news |" in ds.format_pulse_article(news)
    assert ds.pulse_kind(_art("Pastor sued", tags=["news"])) == "news (scandal)"


def test_byline_not_doubled_when_author_is_source():
    a = _art("x", source="Russell Moore", author="Russell Moore")
    assert "| Russell Moore | essay |" in ds.format_pulse_article(a)
