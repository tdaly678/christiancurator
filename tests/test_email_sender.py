"""Email subject, preheader, trims, UTM links, Debate filter and Pulse fallback
(curator/email_sender.py).

Run: python3 -m unittest discover -s tests
"""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from curator import email_sender as es  # noqa: E402


def art(title, source="Source", url=None, **kw):
    return {"title": title, "source_name": source,
            "url": url or f"https://example.com/{abs(hash(title))}", **kw}


def layout(**kw):
    base = {
        "lead": art("The lead story", "The Gospel Coalition"),
        "subleads": [art("Sublead one", "Desiring God"), art("Sublead two", "Ligonier"),
                     art("Sublead three", "9Marks")],
        "debate": [],
        "board": [{"key": k, "label": k, "articles": [art(f"{k} {i}") for i in range(6)]}
                  for k in ("news", "commentary", "church")],
        "worth_your_time": [art(f"Deep {i}") for i in range(5)],
        "watch_listen": [art(f"Media {i}", media_format=f) for i, f in
                         enumerate(["video", "video", "podcast", "podcast", "video"])],
        "research": [],
    }
    base.update(kw)
    return base


class Subject(unittest.TestCase):
    def test_lead_only_no_count(self):
        self.assertEqual(es.build_subject("Short lead"), "Short lead")

    def test_cut_on_word_boundary(self):
        s = es.build_subject("Southern Baptists vote to study women pastors amendment again at "
                             "next summer's annual meeting in Orlando")
        self.assertLessEqual(len(s), es.SUBJECT_MAX)
        self.assertTrue(s.endswith("…"))
        self.assertNotIn("more stor", s)


class Preheader(unittest.TestCase):
    def test_pulse_first_sentence(self):
        summary = {"paragraphs_plain": ["Grief is the thread today. Second sentence here."]}
        self.assertEqual(es.build_preheader(layout(), summary), "Grief is the thread today.")

    def test_long_pulse_clipped(self):
        summary = {"paragraphs_plain": ["word " * 60 + "."]}
        self.assertLessEqual(len(es.build_preheader(layout(), summary)), es.PREHEADER_MAX)

    def test_sublead_fallback_skips_lead(self):
        p = es.build_preheader(layout(), None)
        self.assertEqual(p, "Also: Sublead one | Sublead two")
        self.assertNotIn("lead story", p)

    def test_fallback_pulse_not_used(self):
        p = es.build_preheader(layout(), es.fallback_pulse(layout()))
        self.assertTrue(p.startswith("Also: "))


class Trims(unittest.TestCase):
    def test_email_caps(self):
        e = es._email_layout([], layout=layout())
        self.assertTrue(all(len(c["articles"]) == 3 for c in e["board"]))
        self.assertEqual(len(e["worth_your_time"]), 3)
        self.assertEqual([a["media_format"] for a in e["watch_listen"]], ["video", "podcast"])

    def test_homepage_layout_untouched(self):
        page = layout()
        es._email_layout([], layout=page)
        self.assertEqual(len(page["board"][0]["articles"]), 6)
        self.assertEqual(len(page["worth_your_time"]), 5)
        self.assertEqual(len(page["watch_listen"]), 5)


class Debate(unittest.TestCase):
    def pair(self, **kw):
        return {"topic": "T", "label_a": "Point", "label_b": "Counterpoint",
                "a": art("A"), "b": art("B"), **kw}

    def test_scorer_fallback_dropped(self):
        self.assertEqual(es._email_debate([self.pair(kind="scorer")]), [])

    def test_claude_pair_needs_both_theses_when_recorded(self):
        self.assertEqual(es._email_debate([self.pair(kind="claude", thesis_a="X", thesis_b="")]), [])
        ok = self.pair(kind="claude", thesis_a="X", thesis_b="Not X")
        self.assertEqual(es._email_debate([ok]), [ok])

    def test_cached_pair_without_thesis_fields_kept(self):
        old = self.pair(kind="claude")
        self.assertEqual(es._email_debate([old]), [old])


class Links(unittest.TestCase):
    def test_site_links_get_utm(self):
        u = es._site_link("https://www.christiancurator.com/#cc-email-box", "subscribe")
        self.assertIn(f"utm_campaign=daily_{date.today().isoformat()}", u)
        self.assertIn("utm_content=subscribe", u)
        self.assertTrue(u.endswith("#cc-email-box"))

    def test_publisher_links_clean(self):
        url = "https://www.thegospelcoalition.org/article/x/"
        self.assertEqual(es._site_link(url, "lead"), url)

    def test_rendered_email(self):
        with mock.patch.object(es, "_get_spotlight_topic", return_value=None):
            out = es.build_email_html([], layout=layout())
        self.assertIn("utm_content=cta", out)
        self.assertIn("utm_content=masthead", out)
        self.assertNotIn("example.com/" + "?utm", out)
        self.assertNotIn("utm_", out.split("https://example.com", 1)[1].split('"', 1)[0])
        # CTA sits after the board and before Worth Your Time.
        self.assertLess(out.index("church 2"), out.index("utm_content=cta"))
        self.assertLess(out.index("utm_content=cta"), out.index("Worth Your Time"))
        # Fallback Pulse fills the opener when the Claude summary is missing.
        self.assertIn("Today&rsquo;s lead: The lead story (The Gospel Coalition).", out)
        self.assertIn("Also: Sublead one | Sublead two", out)

    def test_pulse_internal_links_tagged(self):
        summary = {"paragraphs_html": ['See <a href="https://www.christiancurator.com/daily/2026-10-29/">'
                                       'yesterday</a> and <a href="https://example.com/a">this</a>.'],
                   "slug": "2026-10-30"}
        out = es._render_pulse(summary)
        self.assertIn("/daily/2026-10-29/?utm_source=cc_email", out)
        self.assertIn('href="https://example.com/a"', out)
        self.assertIn("/daily/2026-10-30/?utm_source", out)


if __name__ == "__main__":
    unittest.main()
