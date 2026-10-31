"""Evangelical focus: mainline polity/personnel headlines are capped (Tom, 2026-10-31).

Run: python3 -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curator.lanes import select_worth_your_time  # noqa: E402
from curator.point_counterpoint import validate_pair  # noqa: E402
from curator.scorer import is_mainline_polity  # noqa: E402


class MainlinePolity(unittest.TestCase):
    def test_capped(self):
        for t in [
            # Live 2026-10-30 (Christian Post), scored 8.3 and reached the board.
            "UMC Bishop appoints new pastor to Texas megachurch that voted to disaffiliate",
            "Highland Park United Methodist gets new senior pastor appointed by bishop",
            "North Texas Annual Conference approves budget cuts",
            "ELCA Churchwide Assembly elects presiding bishop",
            "Presbyterian Church (USA) General Assembly delegates approve divestment",
            "Episcopal diocese consecrates new bishop",
        ]:
            self.assertTrue(is_mainline_polity(t), t)

    def test_not_capped(self):
        for t in [
            "Methodist Church Cuts Ties With Asbury Over Sexual Ethics Dispute",
            "What Can We Learn from the 100 Largest United Methodist Churches?",
            "More than 7,600 churches have left the UMC, new count shows",
            "Global Methodist Church elects first bishops",
            "Pastor's Long Shot: Can a Methodist Minister Flip Kansas Blue?",
            # Baptist and Presbyterian news is core coverage.
            "SBC Executive Committee elects new president",
            "PCA General Assembly votes on overture",
            "EPC presbytery installs new pastor",
            "John Wesley's Methodist revival and the Great Awakening",
        ]:
            self.assertFalse(is_mainline_polity(t), t)

    def test_debate_rejects_mainline(self):
        a = {"title": "UMC bishop appoints pastor to Highland Park", "source_name": "The Christian Post",
             "perspective": "critical", "url": "https://a.example/1"}
        b = {"title": "Why local churches should choose their pastors", "source_name": "WORLD",
             "perspective": "supportive", "url": "https://b.example/2"}
        self.assertEqual(validate_pair(a, b), "off evangelical focus")

    def test_worth_your_time_skips_capped(self):
        arts = [{"url": f"https://x.example/{i}", "source_name": f"S{i}", "depth": 8,
                 "final_score": 3, "mainline_capped": i == 0} for i in range(3)]
        picks = select_worth_your_time(arts, exclude_urls=set())
        self.assertNotIn("https://x.example/0", {a["url"] for a in picks})


if __name__ == "__main__":
    unittest.main()
