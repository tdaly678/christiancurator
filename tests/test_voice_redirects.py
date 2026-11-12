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
            self.assertNotIn(loser, self.data, loser)
            self.assertIn(loser, self.noindex, loser)
            stub = (VOICES / loser / "index.html").read_text()
            self.assertIn("noindex", stub)
            if not r["to"]:
                # Retired posting account: points at the Voices index.
                self.assertIn('url=/voices/"', stub)
                continue
            self.assertIn(r["to"], self.data, loser)
            self.assertNotIn(r["to"], self.redirects, f"{loser} redirects to another redirect")
            self.assertIn(f'url=/voices/{r["to"]}/"', stub)

    def test_noindexed_voices_stay_out_of_sitemap(self):
        for slug in self.noindex:
            self.assertNotIn(f"/voices/{slug}/<", self.sitemap, slug)

    def test_old_bylines_link_to_survivor(self):
        by_name = load_voices_by_name()
        for r in self.redirects.values():
            if r.get("name") and not r["to"]:
                self.assertNotIn(r["name"].lower(), by_name)
            elif r.get("name"):
                self.assertNotIn(by_name[r["name"].lower()], self.redirects)

    def test_no_page_links_a_retired_voice(self):
        retired = [slug for slug, r in self.redirects.items() if not r["to"]]
        pages = [ROOT / "docs" / "index.html", ROOT / "docs" / "digest" / "index.html",
                 *sorted((ROOT / "docs" / "archive").glob("*/index.html")),
                 *sorted((ROOT / "docs" / "topics").glob("*/index.html"))]
        for page in pages:
            html = page.read_text(encoding="utf-8", errors="replace")
            for slug in retired:
                self.assertNotIn(f"/voices/{slug}/", html, f"{page.relative_to(ROOT)} links {slug}")


class RetireBylineFormatTests(unittest.TestCase):
    """retire_posting_accounts.py rewrites every byline format the site has used."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import retire_posting_accounts as rpa
        self.rpa = rpa

    def _sub(self, html, author):
        by_name = {"joshua mitchell": "joshua-mitchell"}
        return self.rpa.anchor_re("chloe-hoyle").sub(lambda m: self.rpa.replace_byline(m, author, by_name), html)

    def test_homepage_byline_with_middot(self):
        html = ('<div class="cc-src"><a href="/voices/chloe-hoyle/" class="cc-author-link">'
                '<strong>Chloe Hoyle</strong></a> &middot; First Things</div>')
        self.assertEqual(self._sub(html, "Joshua Mitchell"),
                         '<div class="cc-src"><a href="/voices/joshua-mitchell/" class="cc-author-link">'
                         '<strong>Joshua Mitchell</strong></a> &middot; First Things</div>')
        self.assertEqual(self._sub(html, ""), '<div class="cc-src"> First Things</div>')

    def test_april_archive_byline_without_strong(self):
        html = '<a href="/voices/chloe-hoyle/" class="cc-author-link cc-article-author">Chloe Hoyle</a>'
        self.assertEqual(self._sub(html, "Ephraim Radner"),
                         '<span class="cc-author-link cc-article-author">Ephraim Radner</span>')

    def test_unreadable_pages_are_retried(self):
        calls = []

        def fake(url):
            calls.append(url)
            return "R. R. Reno" if len(calls) > 1 else None

        orig, self.rpa.fetch_page_byline = self.rpa.fetch_page_byline, fake
        try:
            out = self.rpa.retry_unreadable(["https://firstthings.com/x/"], pause=0)
        finally:
            self.rpa.fetch_page_byline = orig
        self.assertEqual(out, {"https://firstthings.com/x/": "R. R. Reno"})


if __name__ == "__main__":
    unittest.main()
