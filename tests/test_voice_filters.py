"""Regression tests for voice-page junk prevention.

Run: python3 -m unittest discover -s tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curator.voice_filters import (  # noqa: E402
    is_voice_worthy, junk_reason, name_junk_reason, source_creates_voices,
)
from curator.voice_generator import extract_new_authors, name_to_slug  # noqa: E402


def worthy(name: str) -> bool:
    return is_voice_worthy(name_to_slug(name), name)


class VoiceWorthyTests(unittest.TestCase):
    def test_real_people_pass(self):
        for name in ["Kevin DeYoung", "Jen Wilkin", "D. A. Carson", "Carl R. Trueman",
                     "Russell Moore", "Martin Luther King, Jr.", "Rosaria Butterfield",
                     "Esau McCaulley", "N. T. Wright", "Tish Harrison Warren"]:
            self.assertTrue(worthy(name), name)

    def test_wire_and_staff_bylines_blocked(self):
        for name in ["Staff", "Associated Press", "Reuters", "Editorial Board", "News Desk",
                     "Guardian staff and agencies", "AFP", "The Editors", "RELEVANT Staff",
                     "Christianity Today Editors", "BBC News", "Bloomberg Opinion"]:
            self.assertFalse(worthy(name), name)

    def test_co_bylines_blocked(self):
        for name in ["Brad Green and Ardel Caneday", "Brad Green & Ardel Caneday",
                     "Brad Green, Ardel Caneday", "Brad Green; Ardel Caneday",
                     "Annie Kelly with Alaina Demopoulos", "Brad Green/Ardel Caneday"]:
            self.assertFalse(worthy(name), name)

    def test_handles_emails_urls_blocked(self):
        for name in ["@jdgreear", "aloprete", "jli1", "john smith", "jp@ct.com",
                     "www.example.com", "https://example.org/author", "example.com"]:
            self.assertFalse(worthy(name), name)

    def test_org_names_blocked(self):
        for name in ["The Gospel Coalition", "Ligonier Ministries", "Relevant Media Group",
                     "Southern Baptist Theological Seminary", "Crossway Publishing",
                     "Gentle Reformation", "Moody Radio"]:
            self.assertFalse(worthy(name), name)

    def test_slug_rules(self):
        self.assertIsNotNone(junk_reason("presented-by-annie-kelly-with-alaina-demopoulos"))
        self.assertIsNone(junk_reason("kevin-deyoung"))
        self.assertIsNone(name_junk_reason("Kevin DeYoung"))


class SourceGateTests(unittest.TestCase):
    def test_world_news_never_creates_voices(self):
        self.assertFalse(source_creates_voices({"source_type": "world_news"}))
        self.assertFalse(source_creates_voices({"creates_voices": False}))
        self.assertTrue(source_creates_voices({"source_type": "christian"}))

    def test_extract_new_authors(self):
        articles = [
            {"source_type": "world_news", "author": "Jason Horowitz"},
            {"source_type": "christian", "creates_voices": False, "author": "Jane Analyst"},
            {"source_type": "christian", "author": "Brad Green and Ardel Caneday"},
            {"source_type": "christian", "author": "Brad Green, Ardel Caneday"},
            {"source_type": "christian", "author": "jake@example.com (Jake Meador)"},
            {"source_type": "christian", "author": "Kevin DeYoung"},
            {"source_type": "christian", "author": "Kevin DeYoung"},
        ]
        got = [a["slug"] for a in extract_new_authors(articles, existing_slugs=set())]
        self.assertEqual(got, ["jake-meador", "kevin-deyoung"])


if __name__ == "__main__":
    unittest.main()
