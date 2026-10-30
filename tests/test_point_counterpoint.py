"""Quality bar for The Debate pairs (curator/point_counterpoint.validate_pair).

Run: python3 -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curator.point_counterpoint import validate_pair  # noqa: E402


def art(title, source, perspective=None, summary="", url=None):
    return {"title": title, "source_name": source, "perspective": perspective,
            "summary": summary, "url": url or f"https://example.com/{abs(hash(title))}"}


THESES = {"thesis_a": "Complementarian polity protects the church.",
          "thesis_b": "Restricting women from the pulpit wastes gifts the Spirit gives."}


class RejectWeakPairs(unittest.TestCase):
    def test_same_study_two_outlets(self):
        # Live 2026-10-30: Pew's own release vs. Christian Post's write-up of it.
        a = art("Religion Remains Stable in the U.S., With Mixed Signals for Young Adults",
                "Pew Research", "neutral",
                "Pew Research Center's Religious Landscape data show stability in 2026.")
        b = art("Religious identification, service attendance remains steady after years of decline: Pew",
                "The Christian Post", "neutral",
                "A new Pew Research Center survey finds identification is steady.")
        self.assertIsNotNone(validate_pair(a, b))

    def test_two_news_reports_of_one_fight(self):
        a = art("UMC Bishop appoints new pastor to Texas megachurch that voted to disaffiliate",
                "The Christian Post", "news")
        b = art("Highland Park UMC fight escalates as bishop names new pastor",
                "Religion News Service", "news")
        self.assertIsNotNone(validate_pair(a, b))

    def test_same_story_without_perspective(self):
        a = art("Southern Baptists vote on Law amendment in Dallas", "Baptist Press",
                summary="Messengers to the SBC annual meeting in Dallas considered the Law amendment.")
        b = art("SBC messengers weigh Law amendment again", "Religion News Service",
                summary="The Law amendment returned to the SBC floor in Dallas.")
        self.assertIsNotNone(validate_pair(a, b))

    def test_same_stance(self):
        a = art("Why the church needs creeds", "Mere Orthodoxy", "supportive")
        b = art("In defense of confessional Christianity", "The Gospel Coalition", "supportive")
        self.assertEqual(validate_pair(a, b), "same stance")

    def test_same_source(self):
        a = art("Yes to women deacons", "Christianity Today", "supportive")
        b = art("No to women deacons", "Christianity Today", "critical")
        self.assertEqual(validate_pair(a, b), "same source")

    def test_claude_pair_needs_theses(self):
        a = art("The case for complementarian elders", "9Marks", "supportive")
        b = art("Why our church ordains women", "Christianity Today", "critical")
        self.assertEqual(validate_pair(a, b, {"point_index": 0, "counterpoint_index": 1}),
                         "no stated theses")


class AcceptRealDebates(unittest.TestCase):
    def test_opposed_opinion_pieces(self):
        a = art("The case for complementarian elders", "9Marks", "supportive")
        b = art("Why our church ordains women", "Christianity Today", "critical")
        self.assertIsNone(validate_pair(a, b, THESES))

    def test_opposed_takes_on_one_study_are_fine(self):
        # Same Pew study, but one argues revival and one argues decline.
        a = art("The quiet revival among college-age Christians is real", "World", "supportive",
                "Pew Research Center numbers on 18 to 22 year olds point to revival.")
        b = art("Stop announcing a Gen Z revival the numbers do not show", "Religion News Service", "critical",
                "Pew Research Center numbers on 23 to 26 year olds point to decline.")
        self.assertIsNone(validate_pair(a, b))


if __name__ == "__main__":
    unittest.main()
