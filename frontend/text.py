"""
text.py: sentence-safe copy helpers for page chrome (2026-11-01).

Card blurbs and the masthead Pulse line must never stop mid-word or mid-phrase.
complete_blurb() keeps whole sentences; when even the first sentence is over
the limit it cuts after a full clause (",", ";", ":") and adds an ellipsis, or
else returns the whole first sentence. No em or en dashes reach the page.

No third-party imports, so the standalone scripts in scripts/ can use it.
"""

import html
import re

# Tokens that end in "." without ending a sentence ("Dr. Moore", "U.S. Senate").
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "st", "rev", "fr", "jr", "sr", "prof", "gen", "gov",
    "sen", "rep", "pres", "vs", "etc", "e.g", "i.e", "u.s", "u.k", "u.n", "no",
    "vol", "ed", "inc", "co", "mt", "ft",
}
# A sentence ends at . ! or ? (optionally followed by a closing quote or
# bracket) and the next sentence starts with a capital, digit or quote.
_BOUNDARY = re.compile(r"""([.!?]['"’”)\]]?)\s+(?=['"‘“(\[]?[A-Z0-9])""")


def clean_copy(text: str) -> str:
    """Unescape entities, drop tags, collapse whitespace, remove em/en dashes."""
    from curator.headline_voice import strip_dashes  # stdlib-only module
    s = re.sub(r"<[^>]+>", "", html.unescape(text or ""))
    s = " ".join(s.split())
    return strip_dashes(s).strip()


def split_sentences(text: str) -> list[str]:
    """Split plain text into sentences, ignoring common abbreviations and initials."""
    text = " ".join((text or "").split())
    if not text:
        return []
    out, start = [], 0
    for m in _BOUNDARY.finditer(text):
        end = m.end(1)
        token = text[start:end].rsplit(" ", 1)[-1].rstrip("'\"’”)]")
        word = token.rstrip(".!?").lower()
        if token.endswith(".") and (word in _ABBREVIATIONS or re.fullmatch(r"[a-z]", word)):
            continue
        out.append(text[start:end].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def first_sentence(text: str) -> str:
    sentences = split_sentences(text)
    return sentences[0] if sentences else ""


def complete_blurb(text: str, limit: int = 160) -> str:
    """Return `text` cut to at most `limit` characters without breaking a phrase.

    1. The whole text when it fits.
    2. Else as many whole sentences as fit.
    3. Else the first sentence up to its last full clause, plus an ellipsis.
    4. Else the whole first sentence, even over the limit.
    """
    text = clean_copy(text)
    if len(text) <= limit:
        return text
    sentences = split_sentences(text)
    kept = ""
    for s in sentences:
        candidate = f"{kept} {s}".strip()
        if len(candidate) > limit:
            break
        kept = candidate
    if kept:
        return kept
    first = sentences[0] if sentences else text
    cut = max(first.rfind(p, 0, limit) for p in (",", ";", ":"))
    if cut > limit // 3:
        return first[:cut].rstrip() + "…"
    return first
