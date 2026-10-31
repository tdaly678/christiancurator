"""
RealClear-style headline voice rules (first slice: hard rejects only).

A sample of 1,423 RealClear headlines (2012 to 2026) had zero emoji, zero issue
numbers and zero launch promos. Titles that look like newsletter issues, product
promos or link roundups are not headlines, so score_articles() drops them before
Claude scoring. Spec: .christian-orchestrator/realclear-headline-voice-2026-10-31.md

hard_reject(title) returns one of these reason codes, or None:

  HARD_REJECT_EMOJI         any emoji (pictographs, symbols and dingbats, flags,
                            emoji presentation selector U+FE0F)
  HARD_REJECT_ISSUE_NUMBER  "#432", "Issue 12", "Vol. 3", "Ep. 7" / "Episode 7",
                            "No. 45" (two or more digits, so "the No. 1 threat"
                            still passes)
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

Checks run in the order above; the first match wins. Curly quotes and
apostrophes are normalized to straight ones before matching.
"""

import re

HARD_REJECT_EMOJI = "HARD_REJECT_EMOJI"
HARD_REJECT_ISSUE_NUMBER = "HARD_REJECT_ISSUE_NUMBER"
HARD_REJECT_PROMO = "HARD_REJECT_PROMO"
HARD_REJECT_ROUNDUP = "HARD_REJECT_ROUNDUP"

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


def normalize_title(title: str) -> str:
    """Straighten curly quotes and apostrophes and collapse whitespace."""
    return " ".join((title or "").translate(_SMART_QUOTES).split())


def hard_reject(title: str) -> str | None:
    """Return a HARD_REJECT_* reason code if the title is not a headline, else None."""
    t = normalize_title(title)
    if not t:
        return None
    if EMOJI_RE.search(t):
        return HARD_REJECT_EMOJI
    if ISSUE_NUMBER_RE.search(t):
        return HARD_REJECT_ISSUE_NUMBER
    if _PROMO_CS_RE.search(t) or _PROMO_RE.search(t):
        return HARD_REJECT_PROMO
    if _ROUNDUP_RE.search(t):
        return HARD_REJECT_ROUNDUP
    return None
