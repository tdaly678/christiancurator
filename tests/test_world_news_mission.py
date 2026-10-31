"""Evangelical mission gate for general world-news feeds (Tom, 2026-10-31).

Run: python3 -m unittest discover -s tests
"""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curator import scorer  # noqa: E402
from curator.mission import has_faith_hook, is_off_mission  # noqa: E402
from frontend.layout import build_homepage_layout  # noqa: E402

# Live on the homepage News board, 2026-10-31.
OFF_MISSION = [
    ("Wall Street Journal", "How Iran Battered U.S. Bases and Caused Billions in Damage"),
    ("BBC News", "Spain transport minister says he won't resign over high-speed rail disaster"),
    ("The New York Times", "What to Know About Fighting Between Ethiopia and Rebels in Tigray"),
    ("The New York Times", "Russian News Outlet That Defied Kremlin Will Shut Down: 'They Killed Us'"),
    ("BBC News", "They strangled us, says founder of Russian newspaper shut under pressure from authorities"),
    ("Wall Street Journal", "Kim Jong Un Makes Surprise Trip to China, Crosses New Bridge"),
    ("Wall Street Journal", "Oil Prices Rise After Hormuz Tanker Attack, Houthi Claims Stoke Supply Fears"),
]
ON_MISSION = [
    ("BBC News", "Gunmen kill 30 worshippers in attack on Nigerian church"),
    ("The New York Times", "Supreme Court Sides With Religious Charity in Unemployment Tax Case"),
    ("The Guardian", "Nine killed and 40 injured after gunmen open fire at church funeral in Jordan"),
    ("The New York Times", "U.S. to Send Dozens Back to Afghanistan, Despite Risk of Persecution"),
    ("Wall Street Journal", "China Sentences House Church Pastor to Seven Years"),
]


def art(source, title, **kw):
    a = {"source_name": source, "source_type": "world_news", "title": title, "summary": "",
         "url": f"https://example.com/{abs(hash(title))}", "final_score": 9.0,
         "tags": ["news"], "perspective": "news"}
    a.update(kw)
    return a


class FaithHook(unittest.TestCase):
    def test_off_mission_examples(self):
        for source, title in OFF_MISSION:
            self.assertFalse(has_faith_hook(title), title)
            self.assertTrue(is_off_mission(art(source, title)), title)

    def test_positive_controls(self):
        for source, title in ON_MISSION:
            self.assertTrue(has_faith_hook(title), title)
            self.assertFalse(is_off_mission(art(source, title)), title)

    def test_summary_can_supply_the_hook(self):
        a = art("BBC News", "Villagers flee after overnight raid",
                summary="Gunmen burned a Catholic church and abducted a priest in Benue state.")
        self.assertFalse(is_off_mission(a))

    def test_no_false_hooks(self):
        for t in ["Christchurch council approves budget", "Talks held in good faith, minister says",
                  "Military mission ends in Mali"]:
            self.assertFalse(has_faith_hook(t), t)

    def test_christian_outlets_never_gated(self):
        a = art("Christianity Today", "How Iran Battered U.S. Bases", source_type="christian")
        self.assertFalse(is_off_mission(a))


class ScorerFilter(unittest.TestCase):
    def _articles(self):
        return [art(s, t) for s, t in OFF_MISSION + ON_MISSION]

    def test_off_mission_never_reaches_claude_and_no_top_story_exemption(self):
        captured = []

        class Msg:
            def __init__(self, n):
                self.content = [mock.Mock(text="[" + ",".join(['{"relevant": true}'] * n) + "]")]

        def create(**kw):
            text = kw["messages"][0]["content"]
            captured.append(text)
            return Msg(text.count("Title: "))

        with mock.patch.object(scorer.client.messages, "create", side_effect=create):
            kept = scorer.filter_world_news_batch(self._articles())
        titles = {a["title"] for a in kept}
        self.assertEqual(titles, {t for _, t in ON_MISSION})
        for _, t in OFF_MISSION:
            self.assertNotIn(t, captured[0])
        self.assertNotIn("top_story", scorer.WORLD_NEWS_FILTER_PROMPT)

    def test_claude_rejection_is_respected(self):
        class Msg:
            content = [mock.Mock(text='[' + ','.join(['{"relevant": false, "top_story": true}'] * 5) + ']')]

        with mock.patch.object(scorer.client.messages, "create", return_value=Msg()):
            kept = scorer.filter_world_news_batch(self._articles())
        self.assertEqual(kept, [])

    def test_api_error_falls_back_to_keyword_gate(self):
        with mock.patch.object(scorer, "_api_call_with_retry", side_effect=RuntimeError("down")), \
                mock.patch.object(scorer, "record_failure"):
            kept = scorer.filter_world_news_batch(self._articles())
        self.assertEqual({a["title"] for a in kept}, {t for _, t in ON_MISSION})


class LayoutBackstop(unittest.TestCase):
    def test_off_mission_cached_items_stay_off_board_and_lead(self):
        articles = [art(s, t, final_score=9.5) for s, t in OFF_MISSION]
        articles += [art(s, t, final_score=5.0) for s, t in ON_MISSION]
        articles += [art("Christianity Today", f"Church story {i}", source_type="christian",
                         final_score=6.0, tags=["church life"], perspective="neutral")
                     for i in range(6)]
        layout = build_homepage_layout(articles)
        shown = [layout["lead"]] + layout["subleads"]
        for col in layout["board"]:
            shown += col["articles"]
        shown += layout["worth_your_time"]
        shown_titles = {a["title"] for a in shown if a}
        for _, t in OFF_MISSION:
            self.assertNotIn(t, shown_titles)
        news = next(c for c in layout["board"] if c["key"] == "news")
        self.assertTrue({a["title"] for a in news["articles"]} & {t for _, t in ON_MISSION})


if __name__ == "__main__":
    unittest.main()
