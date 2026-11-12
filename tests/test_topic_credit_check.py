"""Curated topic entries must credit the author, outlet and title of the page they link to.

Run: python3 -m unittest tests.test_topic_credit_check
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_topic_quality import (  # noqa: E402
    _canon, _credited_authors, author_matches, page_metadata, scan_page, title_matches,
)

KELLER_URL = "https://www.thegospelcoalition.org/article/3-objections-to-the-doctrine-of-election/"


def entry(href, title, byline):
    return (f'<article class="cc-article-entry"><div class="cc-article-num">1</div><div class="cc-article-body">'
            f'<div class="cc-article-title"><a href="{href}" rel="noopener" target="_blank">{title}</a></div>'
            f'<div class="cc-article-byline">{byline}</div>'
            f'<div class="cc-article-annotation">Notes.</div></div></article>')


# The entry removed from /topics/predestination-free-will/ on Nov 12 2026.
COLE = entry(KELLER_URL, "Election, Free Will, and the Burden of Pastoral Ministry",
             'Darrell Cole · <span class="source">Christianity Today</span>')
KELLER_META = {_canon(KELLER_URL): {"title": "3 Objections to the Doctrine of Election", "authors": ["Tim Keller"]}}


def codes(page, meta=None):
    return [c for c, _ in scan_page("predestination-free-will", page, meta)[0]]


class CreditCheckTests(unittest.TestCase):
    def test_cole_entry_fails_offline_on_outlet_alone(self):
        self.assertEqual(codes(COLE), ["outlet-mismatch"])

    def test_cole_entry_fails_author_with_cached_metadata(self):
        self.assertIn("author-mismatch", codes(COLE, KELLER_META))

    def test_correct_credit_passes(self):
        ok = entry(KELLER_URL, "3 Objections to the Doctrine of Election",
                   'Tim Keller · <span class="source">The Gospel Coalition</span>')
        self.assertEqual(codes(ok, KELLER_META), [])

    def test_wholly_different_title_is_flagged(self):
        bad = entry(KELLER_URL, "Why Fasting Matters Today", 'Tim Keller · <span class="source">The Gospel Coalition</span>')
        self.assertEqual(codes(bad, KELLER_META), ["title-mismatch"])

    def test_paraphrased_title_passes(self):
        self.assertTrue(title_matches("Objections to Election, Answered", "3 Objections to the Doctrine of Election"))

    def test_uncached_url_is_not_judged_on_author_or_title(self):
        e = entry("https://www.desiringgod.org/articles/x", "Anything", 'Someone · <span class="source">Desiring God</span>')
        self.assertEqual(codes(e, KELLER_META), [])

    def test_redirected_link_is_not_a_miscredit(self):
        meta = {_canon(KELLER_URL): {"title": "Justin Taylor Posts Archive", "authors": ["Justin Taylor"],
                                     "final_url": "https://www.thegospelcoalition.org/blogs/justin-taylor/"}}
        ok = entry(KELLER_URL, "3 Objections", 'Tim Keller · <span class="source">The Gospel Coalition</span>')
        self.assertEqual(codes(ok, meta), [])

    def test_outlet_only_bylines_and_org_authors_are_not_people(self):
        self.assertEqual(_credited_authors('by <span class="source">9Marks</span>'), ([], "9Marks"))
        self.assertEqual(_credited_authors('The Gospel Coalition · <span class="source">The Gospel Coalition</span>')[0], [])
        names, outlet = _credited_authors('Mark Dever and David Coffin · <span class="source">TGC</span>')
        self.assertEqual(names, ["Mark Dever", "David Coffin"])
        e = entry("https://albertmohler.com/x", "The Briefing", 'Albert Mohler · <span class="source">AlbertMohler.com</span>')
        self.assertEqual(codes(e, {_canon("https://albertmohler.com/x"): {"title": "The Briefing", "authors": ["Domain"]}}), [])

    def test_author_match_uses_surname_and_ignores_accents(self):
        self.assertTrue(author_matches(["R. Albert Mohler Jr."], ["Albert Mohler"]))
        self.assertTrue(author_matches(["German Diaz"], ["Germán S. Díaz"]))
        self.assertFalse(author_matches(["Darrell Cole"], ["Tim Keller"]))

    def test_page_metadata_reads_og_title_and_author(self):
        page = ('<meta property="og:title" content="3 Objections to the Doctrine of Election" />'
                '<meta name="author" content="Tim Keller" />')
        self.assertEqual(page_metadata(page), {"title": "3 Objections to the Doctrine of Election",
                                               "authors": ["Tim Keller"]})


if __name__ == "__main__":
    unittest.main()
