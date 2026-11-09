"""
RealClear-style headline voice rules: hard rejects, voice_score, display_title.

A sample of 1,423 RealClear headlines (2012 to 2026) had zero emoji, zero issue
numbers and zero launch promos. Titles that look like newsletter issues, product
promos or link roundups are not headlines, so score_articles() drops them before
Claude scoring. Spec: .christian-orchestrator/realclear-headline-voice-2026-10-31.md

hard_reject(title) returns one of these reason codes, or None:

  HARD_REJECT_EMOJI         any emoji (pictographs, symbols and dingbats, flags,
                            emoji presentation selector U+FE0F)
  HARD_REJECT_ISSUE_NUMBER  "#432", "Issue 12", "Vol. 3", "Ep. 7" / "Episode 7",
                            "No. 45" (two or more digits, so "the No. 1 threat"
                            still passes). A leading "Episode 839: <claim>" or
                            "Ep. 12: <claim>" is display noise, not an issue
                            number: when the rest is 4+ words and not just guest
                            names, the prefix is ignored and the rest is checked
                            (display_title() strips it). "Ep. 112: On Calvin"
                            and "Episode 9 with Russell Moore" still reject.
  HARD_REJECT_PROMO         promo collocates only, never bare "launch" or "sale"
                            (so "SpaceX Launch" and "Church Sale" stay news):
                            '"X" is HERE' / 'book is here' / 'is here!', out now,
                            now available, pre-order, giveaway, book/course/album
                            launch, launch day/week/team, on sale, % off,
                            subscribe now/today, register now/today, registration
                            is open
  HARD_REJECT_ROUNDUP       Quick Things, Weekly Roundup, Things I'm Reading,
                            Friday Five, Open Thread, Link Roundup, and "Links"
                            only as the whole title or its lead word ("Links:",
                            "Weekend Links"), so "Missing Links in Theology" passes

  HARD_REJECT_DATED_COLUMN  a dated column: the title ends in a calendar date
                            set off by "(", ":", a dash or a comma, or is only
                            a weekday date ("Works & Wonders (November 1)",
                            "Works & Wonders: October 25", "Weekend A La Carte
                            (October 24)"). Allow-listed by source
                            (DATED_ALLOW): World Magazine "The World and
                            Everything in It: <date>" and Albert Mohler's
                            weekday-date Briefing. Those pass, but
                            is_dated_briefing() bars them from the lead slot,
                            and headline_has_claim() keeps them off the
                            board and out of every email headline slot
                            unless rewritten_title carries a real claim
  HARD_REJECT_REVIEW_META   review meta copy: "lives up to its title / the hype
                            / its billing / its name / its promise"

Checks run in the order above; the first match wins. Curly quotes and
apostrophes are normalized to straight ones before matching.

voice_score(title) (slice 2) returns a net int adjustment, starting from 0.
score_articles() adds voice_score / 10 to final_score under the "voice" key, so
-30 is -3.0 on the 10-point importance scale. Upward moves count against the
MAX_TOTAL_BOOST budget like other boosts; demotions are uncapped penalties.

  DEMOTE_ALL_CAPS            -30  a word of 3+ capitals outside quotes that is
                                  not an acronym (ACRONYMS below, or a 3 to 5
                                  letter token with no vowel, such as CBMW)
  DEMOTE_EXCLAIM             -25  "!" outside quotes
  DEMOTE_FIRST_PERSON_META   -20  newsletter meta voice: "My Week", "This Week I",
                                  "What I'm Reading", "Things I Loved", "A Note to
                                  Readers". Substantive first person ("Why I Left
                                  the PCA") is not demoted
  DEMOTE_LENGTH              -10  under 3 or over 14 words
  REVIEW_SOFT                -20  review framing: a leading "Review:" / "A Review:",
                                  "a review of", "New and Notable"
  DEMOTE_CLAIMLESS_SHORT     -15  2 to 5 words, no ":" or "?", no verb, no claim
                                  noun (CLAIM_NOUNS: myth, danger, case, crisis,
                                  ...), and either starts with "The" or reads
                                  "Noun of Noun" ("Tyranny of Preferences"). A
                                  label, not a headline: build_homepage_layout()
                                  keeps it out of the lead, subleads and email
  BOOST_NEWS_VERB            +10  a subject followed by a strong news verb
                                  (NEWS_VERBS: Urges, Votes, Dies, Resigns, ...;
                                  base form after a plural: "Churches Leave")
  BOOST_ISSUE_QUESTION        +5  opens with Why/How/What/Is/Can/Do/Will/Should
                                  (4+ words, not meta voice)

Quoted spans ("..." and '...') are ignored by the caps and exclamation checks,
so a quoted book title or slogan never costs the headline.

display_title(title, source=None) is the conservative display cleanup. It
never invents wording; it only removes or swaps characters:
  - strips emoji
  - em dash clause breaks become commas; en dashes become hyphens in ranges
    (2025-2026) and commas when spaced as a clause break
  - strips a trailing " | Outlet" / " · Outlet" tail, and " - Outlet" when the
    tail matches the source name
  - strips service tails: "here's how", "here's why", "what you need to know",
    "read more", "continue reading"
  - Title Cases an ALL CAPS shout (acronyms kept); otherwise publisher casing
    is preserved

display_byline(author, source) returns "Author, Outlet" (or whichever exists).
strip_dashes(text) is the shared no-em-dash sanitizer, also used by the Pulse.

rewrite_rejection(candidate, original) gates Claude title rewrites. Title
rewriting is on for the daily product (CC_REWRITE_TITLES=1 in
.github/workflows/daily_run.yml). A rewrite must pass hard_reject() with no
source allow-list, must not be a dated column (headline_has_claim()), a
listicle, or a claimless label, must not keep a dated original's column name,
and must not trigger a caps, "!", meta voice, length or review demotion.
Otherwise curator.title_rewriter falls back to the cleaned display_title().
"""

import re

HARD_REJECT_EMOJI = "HARD_REJECT_EMOJI"
HARD_REJECT_ISSUE_NUMBER = "HARD_REJECT_ISSUE_NUMBER"
HARD_REJECT_PROMO = "HARD_REJECT_PROMO"
HARD_REJECT_ROUNDUP = "HARD_REJECT_ROUNDUP"
HARD_REJECT_DATED_COLUMN = "HARD_REJECT_DATED_COLUMN"
HARD_REJECT_REVIEW_META = "HARD_REJECT_REVIEW_META"

_SMART_QUOTES = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "′": "'", "″": '"',
})

EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # mahjong, cards, enclosed, pictographs, emoticons, transport, supplemental
    "\U0001F1E6-\U0001F1FF"  # regional indicators (flags)
    "☀-➿"          # misc symbols and dingbats
    "⬀-⯿"          # arrows and stars (e.g. U+2B50 star)
    "⌚⌛⏩-⏺"
    "️"                 # emoji presentation selector
    "]"
)

ISSUE_NUMBER_RE = re.compile(
    r"#\d+"
    r"|\bIssue\s*#?\d+"
    r"|\bVol\.?\s*\d+"
    r"|\bEp(?:isode)?\.?\s*#?\d+"
    r"|\bNo\.\s*\d{2,}",
    re.IGNORECASE,
)

# Leading "Episode 839:" / "Ep. 12 -" / "EP 7 |" prefix; group 1 is the rest.
_EPISODE_PREFIX_RE = re.compile(
    r"^\s*Ep(?:isode)?\.?\s*#?\d+\s*[:|\-–—.]\s*(.+)$", re.IGNORECASE)
_NAME_JOINERS = frozenset({"and", "with", "&", "feat", "feat.", "ft", "ft."})
_COMMON_WORDS = frozenset(
    "a an the and but or nor for of in on at to by as vs via up per "
    "is are was were be how why what when who where which can do does will "
    "should your you our we my not no".split())


def _episode_claim(title: str) -> str | None:
    """Return the claim after a leading episode prefix, or None.

    None means there is no prefix, or what follows is too thin to be a
    headline: under 4 words, or only capitalized names joined by and/with.
    """
    m = _EPISODE_PREFIX_RE.match(title)
    if not m:
        return None
    rest = m.group(1).strip()
    words = [w for w in rest.split() if any(c.isalnum() for c in w)]
    if len(words) < 4:
        return None
    content = [w for w in words if w.lower().strip(",") not in _NAME_JOINERS]
    names_only = all(w[:1].isupper() and w.lower().strip(",.") not in _COMMON_WORDS
                     for w in content)
    return None if names_only else rest


_PROMO_CS_RE = re.compile(r"\bis HERE\b")  # shouting "HERE" is the promo tell
_PROMO_RE = re.compile(
    r"(?:[\"']|\b(?:book|course|album|podcast|season|edition|study))\s+is\s+here\b"
    r"|\bis\s+here\s*!"
    r"|\bout\s+now\b"
    r"|\bnow\s+available\b"
    r"|\bpre-?orders?\b"
    r"|\bgiveaway\b"
    r"|\b(?:book|course|album|podcast)\s+launch\b"
    r"|\blaunch\s+(?:day|week|team)\b"
    r"|\bon\s+sale\b"
    r"|\d+\s*%\s*off\b"
    r"|\bsubscribe\s+(?:now|today)\b"
    r"|\bregister\s+(?:now|today)\b"
    r"|\bregistration\s+(?:is\s+)?(?:now\s+)?open\b",
    re.IGNORECASE,
)

_ROUNDUP_RE = re.compile(
    r"\bquick\s+things\b"
    r"|\bweekly\s+round-?up\b"
    r"|\blinks?\s+round-?up\b"
    r"|\bthings\s+i'?m\s+reading\b"
    r"|\bfriday\s+five\b"
    r"|\bopen\s+thread\b"
    r"|^\s*(?:(?:weekly|weekend|friday|saturday|sunday)\s+)?links?\b\s*(?:[:\-–—|]|$)",
    re.IGNORECASE,
)


_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?"
          r"|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_WEEKDAY = r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day"
_DATE = rf"{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?"

# A date that closes the title, set off by "(", ":", a dash or a comma, or a
# title that is only a (weekday) date.
_DATED_COLUMN_RE = re.compile(
    rf"(?:^|[(:\-–—,]\s*)(?:{_WEEKDAY},?\s+)?{_DATE}\s*\)?\s*$", re.IGNORECASE)

# Dated shows that are real daily news briefings: (source, title pattern).
DATED_ALLOW = (
    ("World Magazine", re.compile(r"^The World and Everything in It: ")),
    ("Albert Mohler", re.compile(rf"^{_WEEKDAY},?\s+{_DATE}\s*$", re.IGNORECASE)),
)

_REVIEW_META_RE = re.compile(
    r"\blives up to (?:its|the|their) (?:title|hype|billing|name|promise)\b", re.IGNORECASE)


def is_dated_briefing(title: str, source: str | None) -> bool:
    """True for an allow-listed dated daily briefing (WORLD, Mohler).

    These skip HARD_REJECT_DATED_COLUMN and may sit on the board or in Watch
    and Listen, but never take the lead slot.
    """
    t = normalize_title(title)
    src = (source or "").strip()
    return any(src == s and rx.search(t) for s, rx in DATED_ALLOW)


def is_dated_column_title(title: str) -> bool:
    """True when the title is a dated column label, allow-listed or not.

    "The World and Everything in It: November 3, 2026" passes hard_reject() for
    World Magazine but still makes no news claim, so it is not a headline.
    """
    return bool(_DATED_COLUMN_RE.search(normalize_title(title)))


def shown_headline(article: dict) -> str:
    """The title every display path shows: rewritten_title or title."""
    return article.get("rewritten_title") or article.get("title") or ""


def headline_has_claim(article: dict) -> bool:
    """False when the headline a reader would see is only a dated column label.

    A rewrite (title_rewriter, or a display_title cleanup) that drops the date
    and states the news counts as a claim; an unchanged dated title does not.
    Such items are kept out of the lead block, the board and every email
    headline slot (frontend.layout).
    """
    return not is_dated_column_title(shown_headline(article))


def normalize_title(title: str) -> str:
    """Straighten curly quotes and apostrophes and collapse whitespace."""
    return " ".join((title or "").translate(_SMART_QUOTES).split())


def hard_reject(title: str, source: str | None = None) -> str | None:
    """Return a HARD_REJECT_* reason code if the title is not a headline, else None.

    `source` is the source_name; it only matters for the dated-column allow-list.
    """
    t = normalize_title(title)
    if not t:
        return None
    if EMOJI_RE.search(t):
        return HARD_REJECT_EMOJI
    if ISSUE_NUMBER_RE.search(_episode_claim(t) or t):
        return HARD_REJECT_ISSUE_NUMBER
    if _PROMO_CS_RE.search(t) or _PROMO_RE.search(t):
        return HARD_REJECT_PROMO
    if _ROUNDUP_RE.search(t):
        return HARD_REJECT_ROUNDUP
    if _DATED_COLUMN_RE.search(t) and not is_dated_briefing(t, source):
        return HARD_REJECT_DATED_COLUMN
    if _REVIEW_META_RE.search(t):
        return HARD_REJECT_REVIEW_META
    return None


# ── Slice 2: voice_score ─────────────────────────────────────────────────────

DEMOTE_ALL_CAPS = -30
DEMOTE_EXCLAIM = -25
DEMOTE_FIRST_PERSON_META = -20
DEMOTE_LENGTH = -10
REVIEW_SOFT = -20
DEMOTE_CLAIMLESS_SHORT = -15
BOOST_NEWS_VERB = 10
BOOST_ISSUE_QUESTION = 5

MIN_WORDS = 3
MAX_WORDS = 14

# All-caps tokens that are acronyms, not shouting. A 3 to 5 letter token with
# no vowel (CBMW, NRB) is also treated as an acronym.
ACRONYMS = frozenset("""
    SBC PCA PCUSA ERLC NAE TGC ACNA LCMS ELCA UMC GMC EPC OPC ARP CRC RCA UCC
    TEC NAMB IMB CBF CBMW CCEF IFB ECO EFCA FIRE ADF NIV ESV KJV NKJV NASB CSB
    NLT AI US USA UN UK EU GOP DNC RNC SCOTUS COVID NATO FAQ RSS HTML JSON API
    FBI CIA IRS DOJ ICE CEO CFO LGBT LGBTQ LGBTQIA DEI IVF HHS CDC FDA WHO NPR
    BBC CNN NBC CBS ABC PBS NYT WSJ AP NY DC LA TV PDF URL CEO PhD ISIS IDF NFL
    NBA MLB NCAA BYU UCLA USC MIT NASA PTSD ADHD OCD HIV AIDS IVF RFRA HB SB
    YWAM IVCF CRU BSF RTS SBTS SEBTS MBTS NOBTS SWBTS DTS TEDS WTS ACU BJU CCCU
""".split())

_QUOTED_RE = re.compile(r"\"[^\"]*\"|(?<![A-Za-z])'[^']*'(?![A-Za-z])")
_CAPS_TOKEN_RE = re.compile(r"\b[A-Z]{3,}\b")
_VOWELS = set("AEIOUY")

_META_RE = re.compile(
    r"^\s*(?:my|this|the)\s+week\b"
    r"|\bthis\s+week,?\s+(?:i|we)\b"
    r"|\b(?:what\s+)?i'?m\s+(?:reading|watching|listening|loving|into)\b"
    r"|\b(?:things|books|links|stuff)\s+i\s+(?:loved|read|liked|enjoyed|found)\b"
    r"|\bi'?ve\s+been\s+(?:reading|watching|listening)\b"
    r"|^\s*my\s+(?:favorite|top|weekly|monthly|reading|month|year|summer|fall|"
    r"winter|spring|latest|new\s+(?:book|podcast|course))\b"
    r"|^\s*(?:a\s+)?(?:personal\s+)?(?:note|update|letter)\s+(?:to|for)\s+(?:my\s+)?(?:readers|subscribers)\b"
    r"|^\s*dear\s+(?:readers|friends|subscribers)\b"
    r"|^\s*(?:an?\s+)?update\s+from\s+(?:me|us|the\s+author)\b",
    re.IGNORECASE,
)

NEWS_VERBS = frozenset("""
    urges votes dies resigns rejects elects appoints defends accuses warns sues
    bans approves condemns ousts fires denies charges rules blocks signs passes
    expels removes suspends retires admits confirms backs endorses opposes
    overturns upholds strikes files arrests kills attacks wins loses leaves
    joins names hires closes cuts seeks demands pledges vows unveils reverses
    disaffiliates disfellowships apologizes indicts convicts sentences acquits
    halts launches announces reveals calls slams blasts quits
""".split())



_REVIEW_SOFT_RE = re.compile(
    r"^(?:a\s+)?review:|\ba review of\b|\bnew and notable\b", re.IGNORECASE)

# A short title naming one of these makes a claim ("The Myth of St. Francis",
# "Dangers of Christian Nationalism"), so it is not claimless. "tyranny" is
# deliberately absent: "Tyranny of Preferences" is the case this rule targets.
CLAIM_NOUNS = frozenset("""
    myth myths danger dangers case failure crisis death end return problem
    lie lies cost rise fall decline collapse future
""".split())

# Words that make a short title a sentence or clause rather than a label.
_VERBISH = frozenset("""
    is are was were be been being am has have had do does did can could will
    would should shall may might must isn't aren't wasn't won't can't don't
    doesn't didn't who that which
""".split())


def _is_verbish(word: str) -> bool:
    w = word.lower()
    return (w in _VERBISH or w in NEWS_VERBS or w in NEWS_VERBS_PLURAL
            or (len(w) > 4 and w.endswith(("ing", "ed"))))


def is_claimless_short(title: str) -> bool:
    """True for a 2 to 5 word label with no verb and no claim noun.

    Must start with "The" or read "Noun of Noun". Colons and question marks
    signal a claim or question, so those titles are never claimless.
    """
    t = normalize_title(title)
    if not t or ":" in t or "?" in t:
        return False
    words = _words(t)
    if not 2 <= len(words) <= 5:
        return False
    lower = [w.lower() for w in words]
    if any(w in CLAIM_NOUNS for w in lower) or any(_is_verbish(w) for w in words):
        return False
    starts_the = lower[0] == "the"
    noun_of_noun = (len(words) >= 3 and lower[1] == "of" and words[0][:1].isupper()
                    and lower[0] not in _NOT_SUBJECT)
    return starts_the or noun_of_noun


def _base_form(verb: str) -> str:
    if verb.endswith("ies"):
        return verb[:-3] + "y"
    if verb.endswith(("ches", "shes", "sses", "xes")):
        return verb[:-2]
    return verb[:-1]


# Plural subjects take the base form: "Churches Leave", "Pastors Vote".
NEWS_VERBS_PLURAL = frozenset(_base_form(v) for v in NEWS_VERBS)

_QUESTION_OPENERS = frozenset(
    "why how what is are can could do does did will would should".split())

# Words that cannot be the subject of a news verb ("The Ends of", "How Grace Wins").
_NOT_SUBJECT = frozenset(
    "the a an of in on for to and or my our his her their its your why how what "
    "when where who which this that these those".split())

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")


def _unquoted(title: str) -> str:
    return _QUOTED_RE.sub(" ", title)


def _is_acronym(token: str) -> bool:
    return token in ACRONYMS or (token.isupper() and len(token) <= 5 and not (set(token) & _VOWELS))


def _has_shout_caps(title: str) -> bool:
    return any(not _is_acronym(t) for t in _CAPS_TOKEN_RE.findall(_unquoted(title)))


def _words(title: str) -> list[str]:
    return _WORD_RE.findall(title)


def voice_adjustments(title: str) -> dict[str, int]:
    """Return {rule_name: delta} for each voice rule the title triggers."""
    t = normalize_title(title)
    if not t:
        return {}
    out = {}
    if _has_shout_caps(t):
        out["DEMOTE_ALL_CAPS"] = DEMOTE_ALL_CAPS
    if "!" in _unquoted(t):
        out["DEMOTE_EXCLAIM"] = DEMOTE_EXCLAIM
    meta = bool(_META_RE.search(t))
    if meta:
        out["DEMOTE_FIRST_PERSON_META"] = DEMOTE_FIRST_PERSON_META
    words = _words(t)
    if len(words) < MIN_WORDS or len(words) > MAX_WORDS:
        out["DEMOTE_LENGTH"] = DEMOTE_LENGTH
    if _REVIEW_SOFT_RE.search(t):
        out["REVIEW_SOFT"] = REVIEW_SOFT
    if is_claimless_short(t):
        out["DEMOTE_CLAIMLESS_SHORT"] = DEMOTE_CLAIMLESS_SHORT
    # Subject + news verb: the verb is not the first word and follows a
    # capitalized word or a number ("Pastor Resigns", "SBC Votes", "3 Churches Leave").
    for prev, word in zip(words, words[1:]):
        w = word.lower()
        is_verb = w in NEWS_VERBS or (w in NEWS_VERBS_PLURAL and prev.lower().endswith("s"))
        if (is_verb and prev.lower() not in _NOT_SUBJECT
                and (prev[0].isupper() or prev[0].isdigit())):
            out["BOOST_NEWS_VERB"] = BOOST_NEWS_VERB
            break
    if (words and words[0].lower() in _QUESTION_OPENERS
            and len(words) >= 4 and not meta):
        out["BOOST_ISSUE_QUESTION"] = BOOST_ISSUE_QUESTION
    return out


def voice_score(title: str) -> int:
    """Net RealClear voice adjustment for a title (0 = neutral)."""
    return sum(voice_adjustments(title).values())


# ── Slice 2: display_title / display_byline ──────────────────────────────────

_SMALL_WORDS = frozenset(
    "a an the and but or nor for of in on at to by as vs via up per".split())

_SERVICE_TAIL_RE = re.compile(
    r"\s*[:,.\-–—|]?\s*\(?(?:here['’]?s\s+(?:how|why|what)|what\s+you\s+need\s+to\s+know"
    r"|read\s+more|continue\s+reading)\)?\s*[.!:»>…]*\s*$",
    re.IGNORECASE,
)
_PIPE_TAIL_RE = re.compile(r"\s+[|·]\s+([^|·]+)$")


# Scandal, abuse, lawsuit, resignation and crisis words. The Pulse admits such a
# story only when it dominates the day (curator/daily_summary.py), and the email
# subject never leads with one (curator/email_sender.py).
SCANDAL_RE = re.compile(
    r"\b(abuse[sd]?|abusive|grooming|misconduct|scandals?|lawsuits?|sues|sued|"
    r"suing|resign(?:s|ed|ation)?|steps? down|stepped down|ousted|fired|"
    r"crisis|allegations?|alleged(?:ly)?|accus(?:ed|es|ations?)|whistleblower|"
    r"cover[- ]?up|indict(?:ed|ment)|arrested|pleads? guilty|"
    r"convicted|sentenced|investigation|molest\w*|assault\w*|"
    r"embezzl\w*|fraud)\b",
    re.I,
)


def strip_dashes(text: str) -> str:
    """Replace em and en dashes so copy never ships with them.

    Em dash clause breaks become ", "; a dash that ends or opens the text is
    dropped. En dashes between digits become "-" (ranges); a spaced en dash is
    a clause break (", "); any other en dash becomes "-".
    """
    if not text:
        return text
    s = re.sub(r"(\d)\s*–\s*(\d)", r"\1-\2", text)
    s = re.sub(r"\s+–\s+", " — ", s)
    s = s.replace("–", "-")
    s = re.sub(r"^\s*—\s*", "", s)
    s = re.sub(r"\s*—\s*$", "", s)
    s = re.sub(r"\s*([,;:.!?])?\s*—\s*", lambda m: (m.group(1) or ",") + " ", s)
    s = re.sub(r"\s+([,;:])", r"\1", s)
    s = re.sub(r",\s*,", ",", s)
    return re.sub(r"[ \t]{2,}", " ", s)


def _is_shout(title: str) -> bool:
    letters = [w for w in _words(title) if any(c.isalpha() for c in w)]
    caps = [w for w in letters if w.upper() == w]
    return len(letters) >= 3 and len(caps) == len(letters) and \
        any(not _is_acronym(re.sub(r"[^A-Z]", "", w)) for w in caps)


def _title_case(title: str) -> str:
    """Light Title Case for an ALL CAPS shout; acronyms stay upper case."""
    first = True

    def fix(m):
        nonlocal first
        w = m.group(0)
        head, _, tail = w.partition("'")
        if _is_acronym(head):
            out = head + ("'" + tail.lower() if _ else "")
        elif not first and w.lower() in _SMALL_WORDS:
            out = w.lower()
        else:
            out = w[:1].upper() + w[1:].lower()
        first = False
        return out
    return re.sub(r"[A-Za-z][A-Za-z']*", fix, title)


def display_title(title: str, source: str | None = None) -> str:
    """Conservative display cleanup of a publisher title. Never adds words."""
    if not title:
        return title or ""
    t = EMOJI_RE.sub("", title)
    t = " ".join(t.split())
    t = _episode_claim(t) or t
    m = _PIPE_TAIL_RE.search(t)
    if m and len(_words(m.group(1))) <= 6 and len(_words(t[:m.start()])) >= 3:
        t = t[:m.start()]
    if source:
        src = re.escape(source.strip())
        t2 = re.sub(rf"\s+[\-–—:]\s+{src}\s*$", "", t, flags=re.IGNORECASE)
        if len(_words(t2)) >= 3:
            t = t2
    t2 = _SERVICE_TAIL_RE.sub("", t)
    if t2 != t and len(_words(t2)) >= 3:
        t = t2
    t = strip_dashes(t)
    if _is_shout(t):
        t = _title_case(t)
    t = " ".join(t.split()).strip(" ,;:-")
    return t or title


def display_byline(author: str | None, source: str | None) -> str:
    """'Author, Outlet' when both exist, else whichever exists, else ''."""
    a = " ".join((author or "").split())
    s = " ".join((source or "").split())
    if a and s and a.lower() != s.lower():
        return f"{a}, {s}"
    return a or s


def apply_display_title(article: dict) -> bool:
    """Set article["display_title"] when cleanup changes the title.

    Every display path reads `rewritten_title or title`, so the cleaned title is
    also written to rewritten_title unless a rewrite already exists. Claude
    rewriting (curator.title_rewriter) is on for the daily product via
    CC_REWRITE_TITLES=1 in .github/workflows/daily_run.yml and runs after this
    cleanup; rewrite_rejection() gates its output. Returns True if changed.
    """
    original = article.get("title") or ""
    cleaned = display_title(original, article.get("source_name"))
    if not cleaned or cleaned == original:
        return False
    article["display_title"] = cleaned
    if not article.get("rewritten_title") or article.get("rewritten_title") == original:
        article["rewritten_title"] = cleaned
    return True


# ── Rewrite gate: Claude rewrites must pass the same voice rules ─────────────

# Listicle openers ("5 Ways to Pray", "Ten Things Every Pastor Should Know").
# Used only to gate Claude rewrites; publisher titles are not rejected for it.
_LISTICLE_RE = re.compile(
    r"^\s*(?:the\s+)?(?:\d+|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
    r"|fifteen|twenty)\s+(?:\w+\s+)?(?:ways|things|reasons|tips|lessons|signs|steps"
    r"|questions|books|habits|truths|keys|mistakes|myths|secrets|facts|rules"
    r"|takeaways|quotes|prayers|verses)\b",
    re.IGNORECASE,
)

# Voice rules a rewrite may not trigger. A publisher title that trips one is
# only demoted; a rewrite that trips one is discarded.
REWRITE_FORBIDDEN_RULES = (
    "DEMOTE_ALL_CAPS", "DEMOTE_EXCLAIM", "DEMOTE_FIRST_PERSON_META",
    "DEMOTE_LENGTH", "REVIEW_SOFT", "DEMOTE_CLAIMLESS_SHORT",
)


def is_listicle(title: str) -> bool:
    """True for a numbered list headline ("7 Reasons Churches Fail")."""
    return bool(_LISTICLE_RE.search(normalize_title(title)))


def _column_label(title: str) -> str:
    """The show or column name before a closing date, or "" when not dated."""
    t = normalize_title(title)
    m = _DATED_COLUMN_RE.search(t)
    if not m:
        return ""
    label = t[:m.start()].strip(" (:-,")
    return label if len(_words(label)) >= 2 else ""


def rewrite_rejection(candidate: str, original: str = "") -> str | None:
    """Return why a Claude rewrite fails the RealClear voice, or None if it passes.

    Reuses the publisher-title machinery: hard_reject() with no source (so the
    DATED_ALLOW briefing allow-list never covers a rewrite), the dated column
    check behind headline_has_claim(), the claimless-label rule and the voice
    demotions. Also bars listicles and a rewrite that keeps the show or column
    name of a dated original ("The World and Everything in It").
    """
    t = normalize_title(candidate)
    if not t:
        return "EMPTY"
    reason = hard_reject(t)
    if reason:
        return reason
    if not headline_has_claim({"title": t}):
        return HARD_REJECT_DATED_COLUMN
    if is_listicle(t):
        return "REWRITE_LISTICLE"
    label = _column_label(original)
    if label and label.lower() in t.lower():
        return "REWRITE_KEEPS_COLUMN_NAME"
    for rule in voice_adjustments(t):
        if rule in REWRITE_FORBIDDEN_RULES:
            return rule
    return None
