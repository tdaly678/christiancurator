"""
title_rewriter.py: uses Claude to rewrite article titles in RealClear house voice.

Goal: understated news curation headlines in the RealClearPolitics /
RealClearReligion style that state a claim, never clickbait or promo copy.
The original title is preserved; the rewritten version is stored separately.

ON for the daily product: .github/workflows/daily_run.yml sets
CC_REWRITE_TITLES=1 on the "Run pipeline" step, so main.py rewrites titles
after scoring. Without the flag (local runs, tests) articles keep the cleaned
publisher headline. Every display path reads `rewritten_title or title`.

Every rewrite is gated by headline_voice.rewrite_rejection() (hard rejects,
dated column check, listicle and claimless-label rules, voice demotions). A
rewrite that fails falls back to the cleaned original, display_title().

Fact guards (Nov 22 2026, S1 3.4): a rewrite may not say more than the piece.
  - keep_publisher_title(): roundups, podcast episodes, newsletters and
    titles ending in "?" (KEEP_QUESTION, S10) are never sent to Claude; they
    keep the cleaned publisher title.
  - fact_rejection() discards a rewrite that
      REWRITE_CHANGES_MODALITY    turns a question ("What will we remember in
                                  the afterlife?", "Why paper books endure")
                                  into a statement (a question ends in "?"
                                  or opens with Why, How or What)
      REWRITE_UNCREDITED_OPINION  adds should / must / ought to a piece without
                                  crediting it ("..., Writer Argues", "X Says")
      REWRITE_INVENTED_NOUN       adds a noun such as "white paper", "report",
                                  "study" or "groups" that the original title
                                  and summary never use
      REWRITE_UNKNOWN_ENTITY      names a person, body or work (acronym,
                                  initials, or a capitalized word outside
                                  common vocabulary) absent from the original
                                  title, summary, byline and outlet
"""

import os
import re
import time
import anthropic
from dotenv import load_dotenv

from curator.ai_health import record_failure
from curator.headline_voice import (
    NEWS_VERBS, display_title, hard_reject, hard_reject_description, rewrite_rejection,
    strip_dashes,
)
from curator.highlight import is_highlighted
from curator.media_kind import looks_like_audio_video

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

REWRITE_TITLES_ENABLED = os.environ.get("CC_REWRITE_TITLES", "").strip() == "1"

REWRITE_PROMPT = """\
You are a headline editor for Christian Curator, a news curation front page for \
evangelical readers written in RealClear Media house voice (RealClearPolitics, \
RealClearReligion). RealClear headlines are understated and plain. They state what \
happened or what the writer argues, in the words of a wire editor, and let the \
claim carry the weight.

Rewrite the article title using these rules:
- Make a claim: a subject and a verb that say what happened, what changed, or what \
the writer argues. A question is fine only when it names a real dispute.
- Understated, not punchy: no hype, no teasers, no cliffhangers, no "here's why"
- Use specific nouns and verbs from the article (not "discusses," "explores," or "looks at")
- Name the person, church, court or body when the summary does
- Between 5 and 12 words
- Title Case, no ALL CAPS words except acronyms such as SBC or PCA
- No exclamation points, emoji, em dashes or en dashes
- No issue, episode or volume numbers, and no dates
- No promo or launch copy (out now, now available, pre-order, giveaway, subscribe)
- No newsletter or first person voice (my week, what I'm reading, a note to readers)
- No listicles ("5 Ways", "7 Reasons", "10 Things")
- No review labels ("Review:", "A Review of")
- Keep the original's form: if the original is a question or a "Why" / "How" \
title, the headline stays a question or a "Why" / "How" headline
- When the piece argues an opinion, credit it to the writer ("..., Writer Argues", \
"Pastor Says ..."); never state the writer's opinion as fact
- Never add a document or group the summary does not name: no "white paper", \
"report", "study", "survey", "statement", "groups", "leaders" or "coalition" \
unless the original title or summary uses that word
- Never add a person, church, outlet or organization the original title or summary \
does not name
- Never return a dated show or column title such as \
"The World and Everything in It: November 3, 2026" or "Works & Wonders (November 1)". \
For a dated show or briefing, drop the show name and the date and headline the \
single most important news item in the summary.
- Never return a bare label such as "The Tyranny of Preferences"; say what it claims
- Do NOT invent facts, names, numbers or topics not in the original title or summary
- If the original title already makes a clear claim in this voice, return it unchanged
- Return ONLY the headline, nothing else

Examples of the voice to aim for:
  Original: "Reflections on the Role of the Church in Modern Society"
  RealClear: "Churches Are Losing Their Civic Role, Pastor Argues"

  Original: "The World and Everything in It: November 3, 2026"
  (summary leads with a Supreme Court hearing on a religious charter school)
  RealClear: "Supreme Court Weighs Faith-Based Charter School Case"

  Original: "5 Things Every Pastor Should Know About AI"
  RealClear: "Pastors Should Treat AI Sermon Tools With Caution, Writer Argues"

  Original: "What will we remember in the afterlife?"
  RealClear: "What Will Believers Remember in the Afterlife?"

Original title: {title}
Article summary: {summary}
"""

MAX_RETRIES = 4
RETRY_DELAYS = [5, 15, 30, 60]


def _looks_like_headline(text: str) -> bool:
    """Return False if the model's response looks like a meta-reply rather than a rewritten title."""
    if not text:
        return False
    # Too long to be a headline (>120 chars), or contains phrases typical of a confused/refusal response
    if len(text) > 120:
        return False
    lower = text.lower()
    refusal_phrases = [
        "i need to see", "could you provide", "article summary", "please provide",
        "i cannot", "i'm unable", "i don't have", "you've included",
    ]
    return not any(p in lower for p in refusal_phrases)


_QUOTES = "\"“”"


def _unwrap_quotes(text: str) -> str:
    """Remove one pair of double quotes that wraps the whole reply.

    Only a wrapping pair is removed. A headline that opens or closes with a
    quoted phrase ('"The Elect Lady" in 2 John ...') keeps both of its quote
    marks; a plain str.strip('"') used to cut the opening one and leave the
    closing one dangling.
    """
    t = (text or "").strip()
    if (len(t) >= 2 and t[0] in _QUOTES and t[-1] in _QUOTES
            and not any(c in _QUOTES for c in t[1:-1])):
        return t[1:-1].strip()
    return t


def _fallback_title(article: dict) -> str:
    """The cleaned publisher title shown when a rewrite is skipped or rejected."""
    return display_title(article["title"], article.get("source_name")) or article["title"]


# ── Fact guards ──────────────────────────────────────────────────────────────

# Nouns a rewrite may not introduce: they assert a document, a study or a
# collective actor the piece may not have ("ERLC ... in New White Paper" for a
# podcast, "Christian Groups Denounce" for one editorial).
INVENTED_NOUNS = (
    "white paper", "report", "reports", "study", "studies", "survey", "surveys",
    "poll", "polls", "research", "researchers", "data", "statement", "statements",
    "resolution", "letter", "petition", "lawsuit", "ruling", "guidelines",
    "group", "groups", "leaders", "coalition", "lawmakers", "experts", "scholars",
    "publisher", "publishers", "organizations", "activists", "critics", "advocates",
    "readers", "theologians",
)
_INVENTED_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in sorted(INVENTED_NOUNS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE)

# A title is a question when it ends in "?" or opens with Why, How or What
# (S10, Nov 23 2026). "When Democrats Show Up for Men" or "Is Coming" style
# openers without a "?" are statements.
_QUESTION_OPEN_RE = re.compile(r"^\s*(?:why|how|what)\b", re.IGNORECASE)
_NORMATIVE_RE = re.compile(
    r"\b(?:should|must|ought|need\s+to|needs\s+to|have\s+to|has\s+to)\b", re.IGNORECASE)
_CREDIT_RE = re.compile(
    r"\b(?:argues?|says?|writes?|contends?|urges?|warns?|asks?|insists?|claims?|"
    r"believes?|thinks?|suggests?|calls?|maintains?|according\s+to)\b",
    re.IGNORECASE)

# Words a headline may use without the source naming them: function words,
# attribution verbs and the site's everyday nouns. Any other capitalized word
# in a rewrite that the source lacks must appear in lowercase in today's
# summaries (common vocabulary, build_vocab()), or it is taken for a name.
_BASE_VOCAB = frozenset("""
    a an the and but or nor for of in on at to by as vs via up per from with without
    over under into onto after before about against among amid between through during
    is are was were be been being am has have had do does did can could will would
    should shall may might must not no new old more most less least many much few
    why how what when where who whom whose which this that these those it its they
    their them he his she her we our you your i my one two three four five first
    also just even only ever never all every some any own other others both each
    still yet not so than then there here out off down back
    argues argue says say writes write warns warn urges urge asks ask contends
    insists claims calls call weighs weigh faces face sees see finds find makes make
    takes take shows show offers offer explains explain remains remain still now
    again case cases way ways writer writers author pastor pastors church churches
    christian christians christianity faith faithful believers believer evangelical
    evangelicals god jesus christ gospel bible biblical scripture theology
    theologian theological prayer worship ministry life lives people world culture
""".split())
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z.'\-]*[A-Za-z]|[A-Z]")
_WORDS_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")


def _stem(word: str) -> str:
    w = word.lower().strip(".'")
    w = re.sub(r"'s$", "", w)
    for suf in ("ies", "es", "s", "ed", "ing", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def _source_text(article: dict) -> str:
    # The byline and outlet count as named in the piece ("..., Mathis Argues").
    parts = [article.get("original_title") or "", article.get("title") or "",
             article.get("summary") or "", article.get("description") or "",
             article.get("author") or "", article.get("source_name") or ""]
    return " ".join(re.sub(r"<[^>]+>", " ", p) for p in parts)


def build_vocab(articles: list[dict]) -> set[str]:
    """Stems of words that appear in lowercase in today's summaries and feed
    text: common vocabulary, so a capitalized rewrite word in it is not taken
    for a name. Names are capitalized in running text, so they never enter."""
    vocab = set()
    for a in articles:
        raw = (a.get("summary") or "") + " " + (a.get("full_content") or "")[:20000]
        text = re.sub(r"<[^>]+>", " ", raw)
        for w in re.findall(r"\b[a-z][a-z'\-]+\b", text):
            vocab.add(_stem(w))
    return vocab


def _is_question(title: str) -> bool:
    t = (title or "").strip()
    return t.endswith("?") or bool(_QUESTION_OPEN_RE.match(t))


def keep_publisher_title(article: dict) -> str | None:
    """Why the publisher's title is kept without a rewrite, or None.

    Roundups, podcast episodes and newsletters are presented under their own
    titles: a rewrite of one of them states a claim the piece never makes.
    Titles ending in "?" are kept too (KEEP_QUESTION): a rewrite could only
    restate the question or answer it.
    """
    title = article.get("original_title") or article.get("title") or ""
    # Highlighted research sources (Burge) keep their own headlines: past
    # rewrites added claims ("Study Finds") and drifted from day to day.
    if is_highlighted(article):
        return "KEEP_HIGHLIGHT"
    if looks_like_audio_video(article):
        return "KEEP_PODCAST"
    reason = hard_reject(title) or hard_reject_description(article.get("summary") or "")
    if reason in ("HARD_REJECT_ROUNDUP", "HARD_REJECT_PROMO"):
        return "KEEP_ROUNDUP"
    if re.search(r"\bnewsletter\b|\bround-?up\b|\ba la carte\b", title, re.IGNORECASE):
        return "KEEP_NEWSLETTER"
    # A question the publisher asked stays the publisher's question (S10).
    if title.strip().endswith("?"):
        return "KEEP_QUESTION"
    return None


def _entity_tokens(candidate: str, vocab: set[str]) -> list[str]:
    """Words in the rewrite that look like names: acronyms, initials, internal
    capitals, or capitalized words outside common vocabulary."""
    out = []
    for tok in _TOKEN_RE.findall(candidate):
        for part in tok.split("-"):
            part = part.strip(".'")
            if not part or not part[0].isupper():
                continue
            letters = re.sub(r"[^A-Za-z]", "", part)
            if len(letters) >= 2 and letters.isupper():          # ERLC, SBC
                out.append(part)
            elif "." in part or re.search(r"[a-z][A-Z]", part):  # C.S, McDonald
                out.append(part)
            else:
                low = re.sub(r"'s$", "", part.lower())
                stem = _stem(part)
                if (low not in _BASE_VOCAB and stem not in _BASE_VOCAB and stem not in vocab
                        and low not in NEWS_VERBS):
                    out.append(part)
    return out


def unknown_entities(candidate: str, article: dict, vocab: set[str] | None = None) -> list[str]:
    """Name-like words in the rewrite that the source never uses."""
    source_low = _source_text(article).lower()
    words = _WORDS_RE.findall(_source_text(article))
    source_stems = {_stem(w) for w in words} | {_stem(p) for w in words for p in w.split("-") if p}
    vocab = (vocab or set()) | build_vocab([article])
    return [tok for tok in _entity_tokens(candidate, vocab)
            if tok.lower() not in source_low and _stem(tok) not in source_stems]


def fact_rejection(candidate: str, article: dict, vocab: set[str] | None = None) -> str | None:
    """Why a rewrite says more than the piece does, or None (see module doc)."""
    source = _source_text(article)
    source_low = source.lower()
    words = _WORDS_RE.findall(source)
    source_stems = {_stem(w) for w in words} | {_stem(p) for w in words for p in w.split("-") if p}
    original = article.get("original_title") or article.get("title") or ""

    if _is_question(display_title(original)) and not _is_question(candidate):
        return "REWRITE_CHANGES_MODALITY"

    if (_NORMATIVE_RE.search(candidate) and not _NORMATIVE_RE.search(original)
            and not _CREDIT_RE.search(candidate)):
        return "REWRITE_UNCREDITED_OPINION"

    for m in _INVENTED_RE.finditer(candidate):
        noun = m.group(1).lower()
        if (not re.search(r"\b" + re.escape(noun) + r"\b", source_low)
                and not all(_stem(w) in source_stems for w in noun.split())):
            return "REWRITE_INVENTED_NOUN"

    if unknown_entities(candidate, article, vocab):
        return "REWRITE_UNKNOWN_ENTITY"
    return None


def accept_rewrite(article: dict, candidate: str, vocab: set[str] | None = None) -> str:
    """Return the headline to show: the rewrite if it passes the voice gate, else the fallback.

    The candidate is cleaned first (quotes, dashes, emoji, service tails), then
    checked with headline_voice.rewrite_rejection() and fact_rejection(). A
    rejection is logged and recorded on the article as rewrite_rejected.
    """
    cleaned = strip_dashes(display_title(_unwrap_quotes(candidate),
                                         article.get("source_name")))
    if not _looks_like_headline(cleaned):
        article["rewrite_rejected"] = "META_REPLY"
        return _fallback_title(article)
    reason = rewrite_rejection(cleaned, article["title"]) or fact_rejection(cleaned, article, vocab)
    if reason:
        detail = reason
        if reason == "REWRITE_UNKNOWN_ENTITY":
            detail += ": " + ", ".join(unknown_entities(cleaned, article, vocab))
        print(f"  Rewrite rejected ({detail}): '{cleaned}' for '{article['title']}'")
        article["rewrite_rejected"] = reason
        return _fallback_title(article)
    return cleaned


def _count(stats: dict | None, key: str) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + 1


def rewrite_title(article: dict, vocab: set[str] | None = None,
                  stats: dict | None = None) -> dict:
    """Rewrite a single article title using Claude, with retry on 529 overload.

    `stats`, when given, counts the outcome: skipped (kept or nothing to
    ground on), sent (a Claude call made), then accepted, rejected or errors.
    """
    keep = keep_publisher_title(article)
    if keep:
        article["rewritten_title"] = _fallback_title(article)
        article["rewrite_skipped"] = keep
        _count(stats, "skipped")
        return article
    summary = article.get("summary") or ""
    # Strip HTML tags from summary for cleaner context
    summary_text = re.sub(r"<[^>]+>", "", summary).strip()[:300]

    # Skip rewrite entirely if there's nothing to ground it on
    if not summary_text:
        article["rewritten_title"] = _fallback_title(article)
        _count(stats, "skipped")
        return article

    _count(stats, "sent")

    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=60,
                messages=[{"role": "user", "content": REWRITE_PROMPT.format(title=article["title"], summary=summary_text)}],
            )
            article["rewritten_title"] = accept_rewrite(article, message.content[0].text, vocab)
            _count(stats, "rejected" if article.get("rewrite_rejected") else "accepted")
            return article
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt <= MAX_RETRIES:
                print(f"  Title rewrite overloaded (attempt {attempt}/{MAX_RETRIES}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"  Title rewrite error for '{article['title']}': {e}")
                record_failure("title_rewriter", e)
                article["rewritten_title"] = _fallback_title(article)
                _count(stats, "errors")
                return article
        except Exception as e:
            print(f"  Title rewrite error for '{article['title']}': {e}")
            record_failure("title_rewriter", e)
            article["rewritten_title"] = _fallback_title(article)
            _count(stats, "errors")
            return article
    article["rewritten_title"] = _fallback_title(article)
    _count(stats, "errors")
    return article


def rewrite_titles(articles: list[dict], enabled: bool | None = None) -> list[dict]:
    """Rewrite titles for all articles, only when enabled.

    The daily workflow enables it with CC_REWRITE_TITLES=1. When disabled,
    articles are returned untouched and keep the cleaned publisher headline.
    """
    if enabled is None:
        enabled = REWRITE_TITLES_ENABLED
    if not enabled:
        return articles
    vocab = build_vocab(articles)
    stats = {"sent": 0, "skipped": 0, "accepted": 0, "rejected": 0, "errors": 0}
    out = [rewrite_title(a, vocab, stats) for a in articles]
    print(summary_line(stats))
    return out


def summary_line(stats: dict) -> str:
    """One line per run, so the rejection log is read against the totals."""
    return ("  Title rewrites: {sent} sent, {skipped} skipped, {accepted} accepted, "
            "{rejected} rejected, {errors} errors".format(**{
                k: stats.get(k, 0) for k in ("sent", "skipped", "accepted", "rejected", "errors")}))
