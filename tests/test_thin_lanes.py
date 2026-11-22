"""Thin lanes (S2, Nov 22 2026): Worth Your Time drops to depth 5 when fewer
than 3 pieces reach depth 6, and Watch and Listen renders with 2 picks.
Page and email must handle the smaller counts.
"""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from curator.email_sender import _email_layout, _render_watch_listen, _render_worth_your_time
from curator.lanes import select_watch_and_listen, select_worth_your_time

NOW = datetime(2026, 11, 22, 10, tzinfo=timezone.utc)


def essay(i, depth, src=None):
    return {"url": f"https://e.example/{i}", "title": f"Essay {i} Argues a Point",
            "source_name": src or f"Writer{i}", "depth": depth, "final_score": 5}


def media(i, src, fmt="podcast", days_old=1):
    return {"url": f"https://m.example/{i}", "title": f"Episode {i}", "source_name": src,
            "media_format": fmt, "role": "media",
            "published": format_datetime(NOW - timedelta(days=days_old))}


# ── Worth Your Time ─────────────────────────────────────────────────────────

def test_three_at_depth_six_keep_the_strict_bar():
    arts = [essay(1, 7), essay(2, 6), essay(3, 6), essay(4, 5)]
    picks = select_worth_your_time(arts, exclude_urls=set())
    assert [a["url"] for a in picks] == [f"https://e.example/{i}" for i in (1, 2, 3)]


def test_fewer_than_three_at_six_drops_to_five_deeper_first():
    arts = [essay(1, 5), essay(2, 6.5), essay(3, 5.5), essay(4, 4)]
    picks = select_worth_your_time(arts, exclude_urls=set())
    assert [a["depth"] for a in picks] == [6.5, 5.5, 5]


def test_floor_none_keeps_the_strict_bar():
    arts = [essay(1, 5), essay(2, 6.5)]
    assert len(select_worth_your_time(arts, exclude_urls=set(), floor_depth=None)) == 1


def test_floor_still_skips_shown_and_one_per_source():
    arts = [essay(1, 5, "Same"), essay(2, 5, "Same"), {**essay(3, 5), "previously_shown": True}]
    assert [a["url"] for a in select_worth_your_time(arts, exclude_urls=set())] == ["https://e.example/1"]


# ── Watch and Listen ────────────────────────────────────────────────────────

def test_two_media_picks_render():
    picks = select_watch_and_listen([media(1, "Mere Fidelity"), media(2, "Truth Unites (Gavin Ortlund)", "video")],
                                    now=NOW)
    assert len(picks) == 2


def test_one_media_pick_is_still_omitted():
    assert select_watch_and_listen([media(1, "Mere Fidelity")], now=NOW) == []


# ── templates with small counts ─────────────────────────────────────────────

def test_email_handles_one_pick_and_two_media_items():
    layout = {"lead": None, "subleads": [], "board": [], "debate": [], "research": [], "siblings": {},
              "worth_your_time": [{**essay(1, 5), "rewritten_title": "Essay One Argues a Point"}],
              "watch_listen": [media(1, "Mere Fidelity"), media(2, "Truth Unites (Gavin Ortlund)", "video")]}
    trimmed = _email_layout([], layout=layout)
    assert len(trimmed["worth_your_time"]) == 1 and len(trimmed["watch_listen"]) == 2
    wyt = _render_worth_your_time(trimmed)
    wl = _render_watch_listen(trimmed)
    assert "Worth Your Time" in wyt and wyt.count("https://e.example/1") == 1
    assert "Watch and Listen" in wl and "Episode 1" in wl and "Episode 2" in wl


def test_homepage_template_renders_small_lanes():
    from pathlib import Path

    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "frontend")))
    env.tests["contains"] = lambda value, item: item in (value or [])
    for name in ("strip_html", "article_anchor", "pub_title", "format_author_links"):
        env.filters[name] = lambda v, *a, **k: str(v or "")
    layout = {"lead": None, "subleads": [], "board": [], "debate": [], "research": [], "siblings": {},
              "worth_your_time": [essay(1, 5)],
              "watch_listen": [media(1, "Mere Fidelity"), media(2, "Truth Unites (Gavin Ortlund)", "video")]}
    html = env.get_template("template.html").render(layout=layout, stats={})
    assert html.count('class="cc-wl-item"') == 2
    assert html.count('class="cc-wyt-item"') == 1
