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


def pulse(first, *rest, **kw):
    return {"paragraphs_plain": [" ".join((first,) + rest)], **kw}


class Subject(unittest.TestCase):
    """Subject follows the Daily Pulse, never the lead headline (2026-11-09)."""

    def check_voice(self, s):
        self.assertLessEqual(len(s), es.SUBJECT_MAX)
        for bad in ("…", "...", "—", "–", "!"):
            self.assertNotIn(bad, s)
        self.assertFalse(s.endswith("."))

    def test_claude_subject_preferred(self):
        s = es.build_subject(pulse("Writers are arguing about friendship.",
                                   subject="What the local church owes lonely people."))
        self.assertEqual(s, "What the local church owes lonely people")

    def test_claude_subject_cleaned(self):
        s = es.build_subject(pulse("x.", subject="Friendship and the church \u2014 a new look!"))
        self.assertEqual(s, "Friendship and the church, a new look")

    def test_bad_claude_subject_falls_through_to_pulse(self):
        for bad in ("Pastor resigns amid abuse allegations at megachurch",
                    "\U0001F525 What the local church owes lonely people",
                    "Short one",
                    "x" * 120):
            s = es.build_subject(pulse("Evangelical writers are arguing about what the "
                                       "local church owes lonely people.", subject=bad))
            self.assertEqual(s, "Evangelical writers are arguing about what the local "
                                "church owes lonely people")

    def test_long_first_sentence_shortened_by_clause_not_ellipsis(self):
        s = es.build_subject(pulse(
            "Evangelical writers are pressing this week on what faithful church membership "
            "actually requires, and the answers are pulling in different directions.",
            "David Mathis argues something."))
        self.assertEqual(s, "Evangelical writers are pressing on what faithful church "
                            "membership requires")
        self.check_voice(s)

    def test_lead_in_dropped_when_still_too_long(self):
        s = es.build_subject(pulse(
            "Today the church is asking whether its public witness has become "
            "indistinguishable from political power, and whether that trade has cost "
            "something it cannot get back."))
        self.assertEqual(s, "Whether its public witness has become indistinguishable "
                            "from political power")

    def test_scandal_opening_never_leads(self):
        s = es.build_subject(pulse(
            "Today the church is reckoning, again, with what happens when spiritual "
            "authority becomes a predator's cover.", "A pastor was convicted.",
            themes=["pastoral accountability", "protecting the vulnerable"]))
        self.assertEqual(s, "Today's conversation: pastoral accountability")
        s = es.build_subject(pulse("A megachurch pastor was convicted of fraud and abuse "
                                   "in a case that shook the denomination."))
        self.assertTrue(s.startswith("Christian Curator · "))

    def test_missing_pulse_falls_back_to_dated_masthead(self):
        day = date(2026, 11, 9)
        self.assertEqual(es.build_subject(None, today=day),
                         "Christian Curator · November 9, 2026")
        self.assertEqual(es.build_subject({}, today=day),
                         "Christian Curator · November 9, 2026")
        self.assertEqual(es.build_subject(es.fallback_pulse(layout()), today=day),
                         "Christian Curator · November 9, 2026")

    def test_never_uses_lead_headline(self):
        lay = layout(lead=art("Colorado Forces Catholic Preschools to Choose Between "
                              "Faith and Funding in Landmark Ruling"))
        post = mock.Mock(return_value=mock.Mock(status_code=201, json=lambda: {"id": 1}))
        with mock.patch.object(es, "BREVO_API_KEY", "k"), \
             mock.patch.object(es, "BREVO_SENDER_EMAIL", "a@b.c"), \
             mock.patch.object(es, "build_email_html", return_value="<html></html>"), \
             mock.patch.object(es, "save_email_html", return_value="x"), \
             mock.patch.object(es.requests, "post", post):
            es.send_email([], daily_summary=pulse("The church is asking what prayer "
                                                  "is for, and writers disagree."),
                          layout=lay)
        self.assertEqual(post.call_args_list[0].kwargs["json"]["subject"],
                         "The church is asking what prayer is for, and writers disagree")

    def test_recent_pulse_openings(self):
        cases = {
            "It's election eve, and the church is being asked to account for itself on "
            "two fronts at once: who it votes for, and whether it can be trusted.":
                "The church is being asked to account for itself on two fronts at once",
            "The church is talking today about whether it actually knows what it claims "
            "to know.":
                "The church is talking about whether it knows what it claims to know",
            "The pro-life movement is having a reckoning, and the church doesn't agree "
            "on what it means.":
                "The pro-life movement is having a reckoning",
        }
        for opening, want in cases.items():
            s = es.build_subject(pulse(opening))
            self.assertEqual(s, want)
            self.check_voice(s)


class Preheader(unittest.TestCase):
    def test_pulse_second_sentence(self):
        summary = {"paragraphs_plain": ["Grief is the thread today. Second sentence here."]}
        self.assertEqual(es.build_preheader(layout(), summary), "Second sentence here.")

    def test_skips_scandal_sentence(self):
        summary = pulse("Grief is the thread.", "A pastor was convicted on 27 counts.",
                        "Writers are asking how lament heals.")
        self.assertEqual(es.build_preheader(layout(), summary),
                         "Writers are asking how lament heals.")

    def test_long_pulse_clipped(self):
        summary = {"paragraphs_plain": ["First. " + "word " * 60 + "."]}
        self.assertLessEqual(len(es.build_preheader(layout(), summary)), es.PREHEADER_MAX)

    def test_headline_fallback_without_pulse(self):
        p = es.build_preheader(layout(), None)
        self.assertEqual(p, "Leading: The lead story | Sublead one")

    def test_fallback_pulse_not_used(self):
        p = es.build_preheader(layout(), es.fallback_pulse(layout()))
        self.assertTrue(p.startswith("Leading: "))


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
        self.assertIn("Leading: The lead story | Sublead one", out)

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
