"""Consistency checks for merged duplicate voice pages and the noindex list.

Run: python3 -m unittest discover -s tests
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from frontend import load_voices_by_name  # noqa: E402

REDIRECTS = ROOT / "frontend" / "voices_redirects.json"
NOINDEX = ROOT / "frontend" / "voices_noindex.json"
VOICES = ROOT / "docs" / "voices"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


class VoiceRedirectTests(unittest.TestCase):
    def setUp(self):
        self.redirects = _load(REDIRECTS)
        self.noindex = set(_load(NOINDEX))
        self.data = {v["slug"] for v in json.loads((ROOT / "docs" / "voices_data.json").read_text())}
        self.sitemap = (ROOT / "docs" / "sitemap-voices.xml").read_text()

    def test_survivors_are_live_and_losers_are_stubs(self):
        for loser, r in self.redirects.items():
            self.assertIn(r["to"], self.data, loser)
            self.assertNotIn(r["to"], self.redirects, f"{loser} redirects to another redirect")
            self.assertNotIn(loser, self.data, loser)
            self.assertIn(loser, self.noindex, loser)
            stub = (VOICES / loser / "index.html").read_text()
            self.assertIn(f'url=/voices/{r["to"]}/"', stub)
            self.assertIn("noindex", stub)

    def test_noindexed_voices_stay_out_of_sitemap(self):
        for slug in self.noindex:
            self.assertNotIn(f"/voices/{slug}/<", self.sitemap, slug)

    def test_old_bylines_link_to_survivor(self):
        by_name = load_voices_by_name()
        for r in self.redirects.values():
            if r.get("name"):
                self.assertNotIn(by_name[r["name"].lower()], self.redirects)


if __name__ == "__main__":
    unittest.main()
