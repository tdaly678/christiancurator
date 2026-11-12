"""First Things bylines come from the article page, never the posting account.

Run: python3 -m unittest tests.test_first_things_bylines
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fetcher.rss_fetcher import apply_page_bylines, page_byline  # noqa: E402
from fetcher.sources import SOURCES  # noqa: E402

# Trimmed from https://firstthings.com/a-dreadful-humility/ (Nov 2026): the
# feed's dc:creator and pagePostAuthor say "Abby Silva"; the writer is Radner.
FT_PAGE = """<html><head>
<meta name="author" content="Ephraim Radner" />
<script type="application/ld+json">{"@graph":[{"@type":"Article",
"author":{"@type":"Person","name":"Ephraim Radner"}}]}</script>
<script>var dataLayer=[{"pagePostAuthor":"Abby Silva"}];</script>
</head><body></body></html>"""


class PageBylineTests(unittest.TestCase):
    def test_meta_author_wins_over_posting_account(self):
        self.assertEqual(page_byline(FT_PAGE), "Ephraim Radner")

    def test_json_ld_fallback_joins_multiple_authors(self):
        page = ('<script type="application/ld+json">{"author":[{"@type":"Person","name":"A One"},'
                '{"@type":"Person","name":"B Two"}]}</script>')
        self.assertEqual(page_byline(page), "A One and B Two")

    def test_attribute_order_and_entities(self):
        self.assertEqual(page_byline('<meta content="Vincent Phillip Mu&ntilde;oz" name="author">'),
                         "Vincent Phillip Muñoz")

    def test_no_byline_or_profile_url_is_empty(self):
        self.assertEqual(page_byline("<html></html>"), "")
        self.assertEqual(page_byline('<meta name="author" content="https://example.com/staff">'), "")


class ApplyPageBylinesTests(unittest.TestCase):
    def test_feed_author_is_replaced_and_never_kept(self):
        arts = [
            {"url": "https://firstthings.com/a/", "author": "Abby Silva"},
            {"url": "https://firstthings.com/b/", "author": "Chloe Hoyle"},
            {"url": "https://firstthings.com/c/", "author": "Paul Howard"},
        ]
        pages = {"https://firstthings.com/a/": "Ephraim Radner",
                 "https://firstthings.com/b/": "",      # page names nobody
                 "https://firstthings.com/c/": None}    # page unreadable
        health = {}
        apply_page_bylines(arts, health, fetch=pages.get)
        self.assertEqual([a["author"] for a in arts], ["Ephraim Radner", "", ""])
        self.assertEqual(health["byline_from_page"], {"resolved": 1, "no_byline": 1, "failed": 1})

    def test_first_things_opts_in(self):
        ft = [s for s in SOURCES if s["name"] == "First Things"]
        self.assertEqual(len(ft), 1)
        self.assertTrue(ft[0].get("byline_from_page"))


if __name__ == "__main__":
    unittest.main()
