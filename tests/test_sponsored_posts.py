"""Sponsored and vendor guest posts are dropped at ingest; real guest posts stay.

Run: python3 -m unittest tests.test_sponsored_posts
"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fetcher import rss_fetcher  # noqa: E402
from fetcher.sponsored import is_sponsored, sponsored_disclosure  # noqa: E402

# Opening lines of real careynieuwhof.com posts, checked Nov 12 2026.
SPONSORED = [
    "<p><em>This post is in partnership with Subsplash, written by Jeff Harvey, Senior Content Manager.</em></p>",
    "<p><em>This post is in partnership with VisitorReach, written by Poncho Lowder, Founder and CTO, "
    "and Kalye Antonyuk, Content Marketing.</em></p><p>A practical approach to using AI...</p>",
    "<p>This post is in partnership with Global Christian Relief, written by Brian Orme, CEO of Global "
    "Christian Relief</p><p>Father Boutros and I sat in front of a large wooden board...</p>",
    "<p><em>This is a guest post by Josh Burnett, Founder of Church.Tech.</em></p><p>Your sermon...</p>",
    "<p>This is a guest post by Marc Estes, CEO of VisitorReach.</p>",
    "<p>Sponsored by Gloo. Churches everywhere are asking...</p>",
    "<p>This is a sponsored post. Thanks to our partners at ...</p>",
]

KEPT = [
    # Real guest post by a pastor (careynieuwhof.com/bigger-than-the-game/).
    "<p>This is a guest post by Andy Searles, Pastor of Church Together just outside Orlando, a chaplain "
    "for an MLS soccer team, and a leader within the Pro Soccer Chaplains Association.</p>",
    # A pastor who also founded something is still a pastor.
    "<p>This is a guest post by Jane Doe, lead pastor and founder of Grace Fellowship.</p>",
    "<p>This is a guest post by Sam Lee, a church planter in Denver.</p>",
    # Partnership language deep in an ordinary article never counts.
    "<p>" + "Our church has been thinking about mission for years. " * 10
    + "We planted a church in partnership with local congregations.</p>",
    "<p>Thabiti Anyabwile helped plant a congregation in 2017 in partnership with local churches.</p>",
    # Emily P. Freeman, Nov 2026: a denial is not a disclosure.
    "<p>This is not a sponsored post, just me having a conversation with a writer I respect.</p>",
    "",
]


class DisclosureTests(unittest.TestCase):
    def test_sponsored_openings_are_caught(self):
        for body in SPONSORED:
            with self.subTest(body=body[:60]):
                self.assertIsNotNone(sponsored_disclosure(body))

    def test_real_guest_posts_and_ordinary_text_survive(self):
        for body in KEPT:
            with self.subTest(body=body[:60]):
                self.assertIsNone(sponsored_disclosure(body))

    def test_summary_is_checked_when_content_is_empty(self):
        self.assertTrue(is_sponsored({"full_content": "", "summary": SPONSORED[0]}))
        self.assertFalse(is_sponsored({"full_content": KEPT[0], "summary": KEPT[0]}))


FEED = """<?xml version="1.0"?><rss version="2.0"
xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><title>CN</title>
<item><title>Sermon Impact</title><link>https://careynieuwhof.com/sermon-end-sunday/</link>
<content:encoded><![CDATA[<p>This is a guest post by Josh Burnett, Founder of Church.Tech.</p>]]></content:encoded></item>
<item><title>Bigger Than the Game</title><link>https://careynieuwhof.com/bigger-than-the-game/</link>
<content:encoded><![CDATA[<p>This is a guest post by Andy Searles, Pastor of Church Together.</p>]]></content:encoded></item>
<item><title>Episode 841</title><link>https://careynieuwhof.com/episode-841/</link>
<description>Lysa TerKeurst on control.</description></item>
</channel></rss>"""


class FetchFeedTests(unittest.TestCase):
    def test_fetch_feed_drops_sponsored_items_and_logs_them(self):
        resp = mock.Mock(status_code=200, content=FEED.encode())
        source = {"name": "Carey Nieuwhof", "url": "https://careynieuwhof.com/feed/", "category": "church life"}
        with mock.patch.object(rss_fetcher, "_get_feed", return_value=resp):
            articles, health = rss_fetcher.fetch_feed(source)
        self.assertEqual([a["title"] for a in articles], ["Bigger Than the Game", "Episode 841"])
        self.assertEqual(health["sponsored_dropped"], ["Sermon Impact"])


if __name__ == "__main__":
    unittest.main()
