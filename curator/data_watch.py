"""
data_watch.py: the topic data watch (daily, after the pipeline renders).

Finds survey and data stories in the day's pool, matches them to topic pages,
and keeps those pages current without hand edits. No Claude call; every
decision is a rule in this file so the same input gives the same output.

Steps (run by scripts/run_data_watch.py):
  1. detect_signals(): a story is a data story when it names a research
     publisher (PUBLISHERS), carries a figure in its title or summary
     ("62%", "2 in 3"), or uses a strong data word (survey, poll, quiz,
     statistics). Weak words (study, report, data) count only with the
     scorer's "data" tag. "Bible study" never counts.
  2. trend_score(): the scorer's final_score, plus outlets covering the same
     story (dedup also_from, shared topic_cluster) and a bump when the story
     was placed on the digest. No social-listening API.
  3. match_topic_slugs(): curator.topic_classifier (all 70 topics, its usual
     threshold), plus whole-word title hits on frontend.topic_matcher's
     curated keywords, plus WATCH_TOPICS keywords. Only slugs that have a
     page under docs/topics/ are kept.
  4. For eligible stories (on the digest, or final_score >= ACT_MIN_SCORE),
     fetch the story page once and look for figures. A figure is only kept
     when its whole sentence is found on the fetched page, names a known
     research publisher (in the sentence, the page, or the story), mentions
     the topic, and reads like a finding. Anything else is "link only".
  5. Apply, fail closed:
       - every digest story matched to a topic goes to the Fresh From the
         Digest block (scripts/build_recent_articles.py reads `fresh` from
         the state file);
       - topics with a data file (WATCH_TOPICS[...]["data_file"]) get a row in
         that file's `watch` list and their builder reruns; the builder shows
         watch rows as a cited text table and never charts them;
       - every other topic gets a marker-bounded "Latest Figures" block
         (quoted sentence, source link, publisher), inserted once and then
         refreshed in place. "Last updated" and the Article dateModified move
         only when the block's content changed.

License status is decided by publisher (PUBLISHERS). Nothing the data watch
writes is ever charted: ask-first and cite-only rows are text by rule, and
reuse rows need a person to fill in question wording, sample and field dates
before they can join a chart in the data file's `rows`.
"""

from __future__ import annotations

import hashlib
import html as html_mod
import re
from datetime import date, timedelta
from pathlib import Path

from curator.original_titles import article_original_title

REPO_ROOT = Path(__file__).resolve().parent.parent
TOPICS_DIR = REPO_ROOT / "docs" / "topics"

# --------------------------------------------------------------------------- config

# Research publishers and the license status their figures get.
#   reuse       terms allow republishing or our own chart with attribution
#               (Pew: attribution plus disclaimer; Lifeway, Gallup: own chart, cite)
#   ask-first   written permission needed before charting (Barna, ABS, Burge)
#   cite-only   quote and link only (no terms found, or proprietary data)
# Order matters only for display; the first publisher named in a sentence wins.
PUBLISHERS: list[dict] = [
    {"name": "Lifeway Research", "license": "reuse",
     "pattern": r"\blifeway research\b|\blifeway\b", "hosts": ["research.lifeway.com", "lifewayresearch.com"]},
    {"name": "Pew Research Center", "license": "reuse",
     "pattern": r"\bpew research\b|\bpew\b", "hosts": ["pewresearch.org"]},
    {"name": "Gallup", "license": "reuse",
     "pattern": r"\bgallup\b", "hosts": ["news.gallup.com", "gallup.com"]},
    {"name": "Barna Group", "license": "ask-first",
     "pattern": r"\bbarna\b", "hosts": ["barna.com"]},
    {"name": "American Bible Society", "license": "ask-first",
     "pattern": r"\bamerican bible society\b|\bstate of the bible\b", "hosts": ["americanbible.org"]},
    {"name": "Ryan Burge", "license": "ask-first",
     "pattern": r"\bryan burge\b|\bgraphs about religion\b", "hosts": ["graphsaboutreligion.com"]},
    {"name": "YouVersion", "license": "cite-only",
     "pattern": r"\byouversion\b", "hosts": ["youversion.com"]},
    {"name": "Wycliffe", "license": "cite-only",
     "pattern": r"\bwycliffe\b", "hosts": ["wycliffe.org", "wycliffe.net"]},
    {"name": "Publishers Weekly", "license": "cite-only",
     "pattern": r"\bpublishers weekly\b", "hosts": ["publishersweekly.com"]},
    {"name": "ECPA", "license": "cite-only",
     "pattern": r"\becpa\b|\bevangelical christian publishers association\b", "hosts": ["ecpa.org"]},
    {"name": "Circana", "license": "cite-only",
     "pattern": r"\bcircana\b|\bbookscan\b", "hosts": ["circana.com"]},
    {"name": "PRRI", "license": "cite-only",
     "pattern": r"\bprri\b|\bpublic religion research institute\b", "hosts": ["prri.org"]},
]
for _p in PUBLISHERS:
    _p["re"] = re.compile(_p["pattern"], re.I)

LICENSE_STATUSES = ("reuse", "cite-only", "ask-first", "permission-granted")
CHARTABLE = {"reuse", "permission-granted"}  # documented here; the data watch itself never charts

# Topics with data-watch extras. `keywords` add recall on top of the classifier
# and also decide whether a sentence is about the topic. `data_file` + `builder`
# mark a structured page: rows go to the file's `watch` list and the builder
# (a module in scripts/ with main(argv) -> int) rerenders the page.
# Add a topic here to give it extra keywords or a data file; any topic page
# can receive Latest Figures without an entry.
WATCH_TOPICS: dict[str, dict] = {
    "biblical-literacy": {
        "keywords": [
            "biblical literacy", "bible literacy", "biblical illiteracy", "bible reading",
            "read the bible", "reads the bible", "reading the bible", "bible engagement",
            "scripture engagement", "scripture engaged", "state of the bible", "bible knowledge",
            "bible quiz", "bible sales", "bibles sold", "bible app", "youversion", "scripture reading",
            "read scripture", "reads scripture", "bible translation",
        ],
        "sentence_keywords": ["bible", "bibles", "scripture", "biblical"],
        "data_file": "data/biblical-literacy/surveys.json",
        "builder": "build_biblical_literacy_viz",
    },
}

# Catch-all topics: the classifier hands them almost any Christian story, so
# the data watch only uses them when the title carries one of these terms.
NARROW_TOPICS: dict[str, list[str]] = {
    "evangelicalism": ["evangelical", "evangelicals", "evangelicalism", "southern baptist",
                       "southern baptists", "sbc", "nae", "post-evangelical"],
}

ACT_MIN_SCORE = 6.0      # stories not on the digest need this final_score to be fetched
MAX_FETCH = 8            # page fetches per run (keeps the 5 AM run short)
MAX_FETCH_ATTEMPTS = 2   # a page that fails twice is not retried
MAX_FIGURES_PER_TOPIC = 5
FIGURE_MAX_AGE_DAYS = 365
FRESH_MAX_AGE_DAYS = 30
SEEN_MAX_AGE_DAYS = 60
HISTORY_LOOKBACK_DAYS = 3
MAX_TOPICS_PER_STORY = 3
QUOTE_MIN, QUOTE_MAX = 40, 320

LF_START = "<!-- CC-LATEST-FIGURES:START -->"
LF_END = "<!-- CC-LATEST-FIGURES:END -->"

PEW_DISCLAIMER = (
    "Pew Research Center bears no responsibility for the analyses or interpretations of the data "
    "presented here. The opinions expressed herein, including any implications for policy, are those "
    "of the author and not of Pew Research Center."
)

# --------------------------------------------------------------------------- text helpers

FIGURE_RE = re.compile(
    r"\b\d{1,3}(?:\.\d+)?\s?(?:%|percent\b)"
    r"|\b(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine)[ -](?:in|out of)[ -]"
    r"(?:\d{1,2}|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.I,
)
STRONG_WORDS_RE = re.compile(
    r"\b(?:surveys?|surveyed|polls?|polling|statistics|statistical|quiz|census|respondents"
    r"|study finds|new study|studies show|research shows|researchers|data shows?)\b",
    re.I,
)
WEAK_WORDS_RE = re.compile(r"\b(?:study|report|data|research|findings)\b", re.I)
BIBLE_STUDY_RE = re.compile(r"\bbible stud(?:y|ies)\b", re.I)
# A finding names who was measured. Methodology notes and asides do not.
FINDING_RE = re.compile(
    r"\b(?:respondents|adults|americans|churchgoers|pastors|ministers|clergy|christians|evangelicals"
    r"|protestants|catholics|mainliners|nones|gen z|millennials|boomers|teens|teenagers|young adults"
    r"|women|men|parents|students|people|users|readers|congregations|churches|households|voters"
    r"|population|believers|worshippers|attendees)\b",
    re.I,
)
# Sentences that lean on context we would not be quoting.
CONTEXT_START_RE = re.compile(r"^(?:so|and|but|or|because|if|when|while|that|this|these|those|it|they|then)\b", re.I)
ANAPHOR_RE = re.compile(r"\b(?:that|this|the same|those)\s+\d", re.I)
FIRST_PERSON_RE = re.compile(r"\b(?:I|I'm|I\u2019m|I've|I\u2019ve|I'd|my|My|me|we|We|our|Our|us)\b")
PROMO_RE = re.compile(
    r"\b(?:off|discount|coupon|subscribe|subscription|sale|donate|donation|shipping|free trial|promo"
    r"|cookies?|privacy policy)\b",
    re.I,
)
DASHES = ("\u2014", "\u2013")  # em and en dash


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _strip_tags(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text or "")
    return html_mod.unescape(re.sub(r"<[^>]+>", " ", text))


def _kw_hit(keyword: str, text: str) -> bool:
    """Whole-word hit, allowing a plain plural ("pastor" matches "pastors")."""
    return re.search(r"(?<![\w-])" + re.escape(keyword.lower()) + r"(?:s|es)?(?![\w-])", text) is not None


def canonical(url: str) -> str:
    try:
        from curator.dedup import canonical_url
        return canonical_url(url)
    except Exception:
        return (url or "").rstrip("/")


def esc(text) -> str:
    return html_mod.escape(str(text or ""), quote=True)


def long_date(d: date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"


# --------------------------------------------------------------------------- 1. detection


def publishers_in(text: str) -> list[dict]:
    """Publishers named in `text`, in order of first mention."""
    hits = []
    for p in PUBLISHERS:
        m = p["re"].search(text or "")
        if m:
            hits.append((m.start(), p))
    return [p for _, p in sorted(hits, key=lambda x: x[0])]


def publisher_for_url(url: str) -> dict | None:
    host = re.sub(r"^https?://(www\.)?", "", (url or "").lower()).split("/")[0]
    for p in PUBLISHERS:
        if any(host == h or host.endswith("." + h) for h in p["hosts"]):
            return p
    return None


def detect_signals(article: dict) -> dict | None:
    """Data signals in a story, or None when it is not a data story."""
    title = article.get("rewritten_title") or article.get("title") or ""
    body = _strip_tags(article.get("summary") or "")[:600]
    text = BIBLE_STUDY_RE.sub(" ", f"{title} . {body}")
    pubs = publishers_in(text)
    by_source = publisher_for_url(article.get("url", ""))
    src_name = article.get("source_name") or ""
    for p in [by_source] + publishers_in(src_name):
        if p and p not in pubs:
            pubs.append(p)
    figures = [m.group(0) for m in FIGURE_RE.finditer(text)]
    strong = sorted({m.group(0).lower() for m in STRONG_WORDS_RE.finditer(text)})
    weak = sorted({m.group(0).lower() for m in WEAK_WORDS_RE.finditer(text)})
    tags = article.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    data_tag = "data" in [str(t).lower() for t in tags]
    if not (pubs or figures or strong or (weak and data_tag)):
        return None
    return {
        "publishers": [p["name"] for p in pubs],
        "figures": figures[:3],
        "words": strong + ([w for w in weak if data_tag] if not strong else []),
        "data_tag": data_tag,
    }


# --------------------------------------------------------------------------- 2. trend


def outlet_count(article: dict, pool: list[dict]) -> int:
    """Distinct outlets carrying this story: itself, dedup copies, same topic_cluster."""
    outlets = {article.get("source_name") or ""}
    outlets.update(a for a in (article.get("also_from") or []) if a)
    cluster = article.get("topic_cluster") or ""
    if cluster and cluster != "unique":
        for other in pool:
            if other.get("topic_cluster") == cluster:
                outlets.add(other.get("source_name") or "")
    outlets.discard("")
    return max(1, len(outlets))


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def trend_score(article: dict, outlets: int, on_digest: bool) -> float:
    return round(_num(article.get("final_score")) + 1.5 * (outlets - 1) + (1.0 if on_digest else 0.0), 2)


# --------------------------------------------------------------------------- 3. topics


def existing_topic_slugs(topics_dir: Path = TOPICS_DIR) -> set[str]:
    if not topics_dir.exists():
        return set()
    return {p.parent.name for p in topics_dir.glob("*/index.html")}


def topic_labels() -> dict[str, str]:
    from frontend.topics_data import TOPICS as ALL
    return {t["slug"]: t["name"] for t in ALL}


def topic_keywords(slug: str) -> list[str]:
    """Keywords that decide whether a page sentence is about this topic."""
    from frontend.topics_data import TOPICS as ALL
    kws: list[str] = []
    for t in ALL:
        if t["slug"] == slug:
            kws += t["keywords"]
    cfg = WATCH_TOPICS.get(slug, {})
    kws += cfg.get("keywords", []) + cfg.get("sentence_keywords", [])
    return sorted({k.lower() for k in kws})


def match_topic_slugs(article: dict, existing: set[str] | None = None) -> list[str]:
    """Topic pages this story belongs on, strongest first (max MAX_TOPICS_PER_STORY)."""
    from curator.topic_classifier import classify_article
    from frontend.topic_matcher import TOPICS as CURATED
    from frontend.topics_data import TOPICS as ALL

    existing = existing_topic_slugs() if existing is None else existing
    title = _norm(_strip_tags(article.get("rewritten_title") or article.get("title") or ""))
    text = _norm(title + " " + _strip_tags(article.get("summary") or "")[:600])
    out: list[str] = []

    def add(slug):
        narrow = NARROW_TOPICS.get(slug)
        if narrow is not None and not any(_kw_hit(k, title) for k in narrow):
            return
        if slug in existing and slug not in out:
            out.append(slug)

    for slug, cfg in WATCH_TOPICS.items():
        if any(_kw_hit(k, text) for k in cfg.get("keywords", [])):
            add(slug)
    for slug in classify_article({"title": title, "summary": article.get("summary") or "",
                                  "topic_cluster": article.get("topic_cluster") or ""}):
        add(slug)
    # Title hits, plural tolerant: the classifier's whole-word match misses
    # "pastors" for "pastor" and "evangelicals" for "evangelical".
    for t in ALL:
        if any(_kw_hit(k, title) for k in t["keywords"]):
            add(t["slug"])
    for t in CURATED:
        if any(len(k) > 2 and _kw_hit(k, title) for k in t["keywords"]):
            add(t["slug"])
    return out[:MAX_TOPICS_PER_STORY]


# --------------------------------------------------------------------------- 4. figures

BLOCK_TAGS_RE = re.compile(r"</?(?:p|br|li|ul|ol|h[1-6]|div|section|article|tr|td|th|blockquote|figcaption|table)\b[^>]*>", re.I)
DROP_RE = re.compile(r"<(head|script|style|noscript|svg|nav|footer|header|form|aside|template|figcaption|button)\b.*?</\1\s*>", re.I | re.S)


def page_text_blocks(page_html: str) -> list[str]:
    """Visible text of a page, one string per block element."""
    h = DROP_RE.sub(" ", page_html or "")
    h = re.sub(r"<!--.*?-->", " ", h, flags=re.S)
    h = BLOCK_TAGS_RE.sub("\n", h)
    h = html_mod.unescape(re.sub(r"<[^>]+>", " ", h))
    blocks = [re.sub(r"[ \t\r\f\v ]+", " ", b).strip() for b in h.split("\n")]
    return [b for b in blocks if b]


# Split after . ! ? (optionally closed by a quote), but not after common abbreviations.
SENTENCE_SPLIT_RE = re.compile(
    r"(?<!\bv\.)(?<!\bvs\.)(?<!U\.S\.)(?<!\bDr\.)(?<!\bMr\.)(?<!\bMrs\.)(?<!\bSt\.)(?<!\bNo\.)"
    r"(?<!\bJan\.)(?<!\bFeb\.)(?<!\bAug\.)(?<!\bSept\.)(?<!\bOct\.)(?<!\bNov\.)(?<!\bDec\.)"
    r"(?<=[.!?])[\"”']?\s+(?=[A-Z0-9\"“(])"
)
SENTENCE_END_RE = re.compile(r"[.!?][\"”')]?$")


def _well_formed(s: str) -> bool:
    """A whole sentence: ends with . ! or ?, balanced brackets and quotes, capital start."""
    if not SENTENCE_END_RE.search(s) or s.count("(") != s.count(")"):
        return False
    if s.count("“") != s.count("”") or s.count('"') % 2:
        return False
    return s[0].isupper() or s[0].isdigit() or s[0] in "\"“"


def sentences(blocks: list[str]) -> list[str]:
    out = []
    for b in blocks:
        out.extend(s.strip() for s in SENTENCE_SPLIT_RE.split(b) if s.strip())
    return out


OTHER_SOURCE_RE = re.compile(
    r"\baccording to\b|\b(?:another|other|separate|unnamed|earlier|previous)\s+(?:surveys?|stud(?:y|ies)|polls?|reports?)\b",
    re.I,
)


def _publisher_from_context(quote: str, page_blocks: list[str], signals: dict | None) -> dict | None:
    """The research publisher behind a sentence, or None when it is not certain."""
    in_quote = publishers_in(quote)
    if in_quote:
        return in_quote[0]
    if OTHER_SOURCE_RE.search(quote):  # the sentence credits someone we cannot name
        return None
    on_page = publishers_in(" ".join(page_blocks)[:20000])
    if len(on_page) == 1:  # one publisher named on the page: unambiguous
        return on_page[0]
    names = (signals or {}).get("publishers") or []
    if len(names) == 1:
        return next((p for p in PUBLISHERS if p["name"] == names[0]), None)
    return None


def find_figures(page_html: str, keywords: list[str], signals: dict | None = None,
                 limit: int = 2) -> list[dict]:
    """Verified figures for one topic from a fetched page.

    A figure is kept only when its sentence (verbatim on the page) contains a
    number, a topic keyword, a named population, no promo words, no dashes,
    no first person, does not lean on an earlier sentence, and can be tied to
    exactly one known research publisher.
    """
    blocks = page_text_blocks(page_html)
    out, seen = [], set()
    for s in sentences(blocks):
        if not (QUOTE_MIN <= len(s) <= QUOTE_MAX) or any(d in s for d in DASHES) or not _well_formed(s):
            continue
        m = FIGURE_RE.search(s)
        low = s.lower()
        if not m or not FINDING_RE.search(s) or PROMO_RE.search(s):
            continue
        if CONTEXT_START_RE.search(s) or ANAPHOR_RE.search(s) or FIRST_PERSON_RE.search(s):
            continue
        if not any(_kw_hit(k, low) for k in keywords):
            continue
        pub = _publisher_from_context(s, blocks, signals)
        if not pub:
            continue
        key = _norm(s)
        if key in seen:
            continue
        seen.add(key)
        out.append({"quote": s, "figure": m.group(0), "publisher": pub["name"], "license_status": pub["license"]})
        if len(out) >= limit:
            break
    return out


def verify_figure(entry: dict, page_html: str | None = None) -> bool:
    """True only for an entry the data watch is allowed to publish.

    Needs an https URL, a known license status, the figure inside the quote,
    and (when the page is given) the quote found verbatim in the page text.
    """
    url, quote, figure = entry.get("url") or "", entry.get("quote") or "", entry.get("figure") or ""
    if not url.startswith("https://") or not quote or not figure:
        return False
    if figure not in quote or not FIGURE_RE.search(figure):
        return False
    if entry.get("license_status") not in LICENSE_STATUSES or not entry.get("publisher"):
        return False
    if any(d in quote for d in DASHES):
        return False
    if page_html is not None:
        text = " \n ".join(page_text_blocks(page_html))
        if _norm(quote) not in _norm(text):
            return False
    return True


def figure_id(url: str, quote: str) -> str:
    return "watch-" + hashlib.sha1(f"{canonical(url)}|{_norm(quote)}".encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------- fetch


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 ChristianCurator/1.0 "
    "(+https://www.christiancurator.com)"
)


def fetch_page(url: str, timeout: int = 15) -> tuple[str | None, str]:
    """(html, "") on success, (None, reason) on any failure. Never raises."""
    try:
        import requests
        resp = requests.get(url, timeout=timeout, allow_redirects=True,
                            headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
    except Exception as exc:
        return None, type(exc).__name__
    if resp.status_code >= 400:
        return None, f"HTTP {resp.status_code}"
    if "html" not in resp.headers.get("Content-Type", "html").lower():
        return None, "not html"
    return resp.text[:600_000], ""


# --------------------------------------------------------------------------- 5a. Latest Figures block

LF_STYLE = (
    "<style>"
    ".cc-latest-figures{margin-top:2.5rem;padding-top:1.75rem;border-top:2px solid #e0ddd8;}"
    ".cc-lf-label{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;"
    "color:#2C4A2E;margin-bottom:0.5rem;}"
    ".cc-lf-title{font-family:'Lora',Georgia,serif;font-size:22px;font-weight:600;margin-bottom:1.1rem;color:#1a1a1a;}"
    ".cc-lf-list{list-style:none;padding:0;margin:0;}"
    ".cc-lf-item{margin-bottom:1.1rem;padding-left:0.9rem;border-left:3px solid #2C4A2E;}"
    ".cc-lf-quote{font-family:'Lora',Georgia,serif;font-size:16px;line-height:1.5;color:#1a1a1a;margin:0;}"
    ".cc-lf-meta{font-size:12px;color:#777;margin-top:4px;}"
    ".cc-lf-meta a{color:#2C4A2E;}"
    ".cc-lf-note{font-size:12px;color:#888;margin-top:0.75rem;line-height:1.5;}"
    "</style>"
)


def render_latest_figures(label: str, figures: list[dict]) -> str:
    """The marker-bounded block. Text only; every figure is quoted and linked."""
    figs = [f for f in figures if verify_figure(f)]
    if not figs:
        return ""
    rows = []
    for f in figs:
        when = f.get("found_on", "")
        try:
            when = long_date(date.fromisoformat(when))
        except ValueError:
            pass
        reported = f.get("reported_by") or f["publisher"]
        meta = (
            f'Figure from {esc(f["publisher"])}. Source: '
            f'<a href="{esc(f["url"])}" target="_blank" rel="noopener">{esc(f.get("title") or reported)}</a>'
            f', {esc(reported)}, {esc(when)}.'
        )
        rows.append(
            f'\n  <li class="cc-lf-item"><p class="cc-lf-quote">“{esc(f["quote"])}”</p>'
            f'<div class="cc-lf-meta">{meta}</div></li>'
        )
    note = ("Quoted as published in the linked source and checked against that page on the date shown. "
            "Christian Curator has not reanalyzed these figures.")
    if any(f["publisher"] == "Pew Research Center" for f in figs):
        note += " " + PEW_DISCLAIMER
    return (
        f"{LF_START}\n"
        f'<section class="cc-latest-figures" id="latest-figures">{LF_STYLE}'
        f'\n  <div class="cc-lf-label">From the Data Watch</div>'
        f'\n  <h2 class="cc-lf-title">Latest Figures on {esc(label)}</h2>'
        f'\n  <ul class="cc-lf-list">{"".join(rows)}\n  </ul>'
        f'\n  <p class="cc-lf-note">{esc(note)}</p>'
        f"\n</section>\n{LF_END}"
    )


LF_BLOCK_RE = re.compile(re.escape(LF_START) + r".*?" + re.escape(LF_END), re.S)
LF_ANCHORS = ("<!-- AEO-RELATED-TOPICS:START -->", "<!-- CC-RECENT-ARTICLES:START -->", "</main>")


def upsert_block(page: str, block: str) -> str | None:
    """Replace the Latest Figures block, or insert it once before the first anchor.

    Returns None when the page has no anchor (left untouched). An empty
    `block` with no existing markers leaves the page as is.
    """
    found = LF_BLOCK_RE.findall(page)
    if len(found) > 1:
        return None
    if found:
        return LF_BLOCK_RE.sub(lambda _m: block, page, count=1)
    if not block:
        return page
    for anchor in LF_ANCHORS:
        pos = page.find(anchor)
        if pos != -1:
            return page[:pos] + block + "\n" + page[pos:]
    return None


LAST_UPDATED_RE = re.compile(r'(<p class="cc-last-updated">Last updated: )([A-Z][a-z]+ \d{1,2}, \d{4})(</p>)')
DATE_MODIFIED_RE = re.compile(r'("@type": "Article".*?"dateModified": ")(\d{4}-\d{2}-\d{2})(")', re.S)


def bump_page_dates(page: str, today: date) -> str:
    page = LAST_UPDATED_RE.sub(lambda m: m.group(1) + long_date(today) + m.group(3), page, count=1)
    return DATE_MODIFIED_RE.sub(lambda m: m.group(1) + today.isoformat() + m.group(3), page, count=1)


def apply_latest_figures(page: str, label: str, figures: list[dict], today: date) -> tuple[str, bool]:
    """(new page, changed). Dates move only when the block content changed."""
    block = render_latest_figures(label, figures)
    out = upsert_block(page, block)
    if out is None or out == page:
        return page, False
    return bump_page_dates(out, today), True


# --------------------------------------------------------------------------- 5b. structured data files


def watch_row(fig: dict) -> dict:
    return {
        "id": figure_id(fig["url"], fig["quote"]),
        "quote": fig["quote"],
        "figure": fig["figure"],
        "publisher": fig["publisher"],
        "license_status": fig["license_status"],
        "url": fig["url"],
        "title": fig.get("title", ""),
        "reported_by": fig.get("reported_by", ""),
        "verified_date": fig["found_on"],
    }


def add_watch_rows(data: dict, figures: list[dict], today: date) -> tuple[dict, list[dict]]:
    """Append new verified figures to data['watch'] plus one changelog line. Pure."""
    data = dict(data)
    existing = list(data.get("watch") or [])
    have = {r["id"] for r in existing}
    added = []
    for f in figures:
        if not verify_figure(f):
            continue
        row = watch_row(f)
        if row["id"] in have:
            continue
        have.add(row["id"])
        existing.append(row)
        added.append(row)
    if added:
        data["watch"] = existing
        pubs = sorted({r["publisher"] for r in added})
        data["changelog"] = list(data.get("changelog") or []) + [{
            "date": today.isoformat(),
            "note": (f"Data watch added {len(added)} cited figure{'s' if len(added) != 1 else ''} from "
                     f"{', '.join(pubs)} to the data watch table (quoted from the linked source, not charted)."),
        }]
    return data, added


# --------------------------------------------------------------------------- run


def _prune(state: dict, today: date) -> None:
    def fresh_enough(d: str, days: int) -> bool:
        try:
            return date.fromisoformat(d) >= today - timedelta(days=days)
        except (TypeError, ValueError):
            return False

    state["seen"] = {u: v for u, v in (state.get("seen") or {}).items()
                     if fresh_enough(v.get("date"), SEEN_MAX_AGE_DAYS)}
    state["fresh"] = {s: [i for i in items if fresh_enough(i.get("date"), FRESH_MAX_AGE_DAYS)]
                      for s, items in (state.get("fresh") or {}).items()}
    state["fresh"] = {s: v for s, v in state["fresh"].items() if v}
    figs = {}
    for slug, items in (state.get("figures") or {}).items():
        keep = [f for f in items if fresh_enough(f.get("found_on"), FIGURE_MAX_AGE_DAYS) and verify_figure(f)]
        keep.sort(key=lambda f: f.get("found_on", ""), reverse=True)
        if keep:
            figs[slug] = keep[:MAX_FIGURES_PER_TOPIC]
    state["figures"] = figs


def collect_candidates(pool: list[dict], history: list[dict], today: date) -> list[dict]:
    """The day's stories (scored pool + recent digest rows), one per canonical URL."""
    from curator.mission import is_off_mission

    cutoff = (today - timedelta(days=HISTORY_LOOKBACK_DAYS)).isoformat()
    on_digest = {}
    for row in history:
        if (row.get("date_shown") or "") >= cutoff and row.get("scored_by") != "media":
            on_digest[canonical(row.get("canonical_url") or row.get("url") or "")] = row
    out, seen = [], set()
    for a in list(pool) + list(on_digest.values()):
        url = a.get("url") or ""
        key = canonical(a.get("canonical_url") or url)
        if not url or key in seen or a.get("role") in ("media", "discovery"):
            continue
        if is_off_mission(a):  # world-news item with no faith hook
            continue
        seen.add(key)
        item = dict(a)
        item["_key"] = key
        row = on_digest.get(key)
        item["_on_digest"] = row is not None
        item["_date_shown"] = (row or {}).get("date_shown", "")
        out.append(item)
    return out


def run_watch(pool: list[dict], history: list[dict], state: dict, today: date,
              fetch=fetch_page, topics_dir: Path = TOPICS_DIR, repo_root: Path = REPO_ROOT,
              write: bool = True, max_fetch: int = MAX_FETCH) -> dict:
    """One data-watch pass. Mutates and returns `state`; report in state['last_run'].

    `fetch(url) -> (html | None, reason)` is injectable for tests. With
    write=False nothing on disk changes (dry run).
    """
    state = state or {}
    for key in ("seen", "fresh", "figures"):
        state.setdefault(key, {})
    existing = existing_topic_slugs(topics_dir)
    labels = topic_labels()
    report: list[dict] = []
    new_figs: dict[str, list[dict]] = {}
    fetched = 0

    candidates = collect_candidates(pool, history, today)
    hits = []
    for a in candidates:
        sig = detect_signals(a)
        if not sig:
            continue
        slugs = match_topic_slugs(a, existing)
        outlets = outlet_count(a, pool)
        hits.append((trend_score(a, outlets, a["_on_digest"]), outlets, a, sig, slugs))
    # Digest stories first (they get the fetch budget), then by trend.
    hits.sort(key=lambda h: (not h[2]["_on_digest"], -h[0], h[2].get("title") or ""))

    for trend, outlets, a, sig, slugs in hits:
        # Publisher headline: fresh items are listed on topic pages.
        title = article_original_title(a) or a.get("title") or ""
        item = {"title": title, "url": a["url"], "source": a.get("source_name", ""),
                "signals": sig, "topics": slugs, "trend": trend, "outlets": outlets,
                "on_digest": a["_on_digest"], "actions": []}
        report.append(item)
        if not slugs:
            item["actions"].append("no topic page matched")
            continue

        if a["_on_digest"]:
            for slug in slugs:
                lst = state["fresh"].setdefault(slug, [])
                if not any(canonical(x["url"]) == a["_key"] for x in lst):
                    lst.append({"date": a["_date_shown"] or today.isoformat(), "title": title,
                                "url": a["url"], "source": a.get("source_name", "")})
            item["actions"].append("linked in Fresh From the Digest")

        prior = state["seen"].get(a["_key"])
        if prior and (prior.get("status") == "fetched" or prior.get("attempts", 0) >= MAX_FETCH_ATTEMPTS):
            item["actions"].append(f"page already checked on {prior.get('date')} ({prior.get('note', prior.get('status'))})")
            continue
        if not (a["_on_digest"] or _num(a.get("final_score")) >= ACT_MIN_SCORE):
            item["actions"].append(f"watching only (not on digest, score below {ACT_MIN_SCORE:g})")
            continue
        if not a["url"].startswith("https://"):
            item["actions"].append("link only: story URL is not https")
            continue
        if fetched >= max_fetch:
            item["actions"].append("not fetched today (fetch cap reached); retry next run")
            continue

        fetched += 1
        page, reason = fetch(a["url"])
        attempts = (prior or {}).get("attempts", 0) + 1
        if page is None:
            state["seen"][a["_key"]] = {"date": today.isoformat(), "status": "failed",
                                        "attempts": attempts, "note": reason}
            item["actions"].append(f"fetch failed ({reason}): link only, no figure written")
            item["warning"] = f"data watch: could not fetch {a['url']} ({reason})"
            continue

        from curator.mission import has_faith_hook
        story_hook = has_faith_hook(title, _strip_tags(a.get("summary") or "")[:600])
        found_any = []
        for slug in slugs:
            if _cited_in_data_file(slug, a["_key"], repo_root):
                item["actions"].append(f"source already cited in the {slug} data file")
                continue
            figs = find_figures(page, topic_keywords(slug), sig)
            for f in figs:
                f.update({"url": a["url"], "title": title, "reported_by": a.get("source_name", ""),
                          "found_on": today.isoformat(), "topic": slug})
                f["id"] = figure_id(f["url"], f["quote"])
                if not (story_hook or has_faith_hook(f["quote"])):
                    continue  # a general stat with no faith angle never lands on a topic page
                if verify_figure(f, page):
                    new_figs.setdefault(slug, []).append(f)
                    found_any.append((slug, f))
        state["seen"][a["_key"]] = {"date": today.isoformat(), "status": "fetched", "attempts": attempts,
                                    "note": f"{len(found_any)} verified figure(s)"}
        if not found_any and not all(_cited_in_data_file(sl, a["_key"], repo_root) for sl in slugs):
            item["actions"].append("no verifiable figure on the page: link only")
        for slug, f in found_any:
            item["actions"].append(f"verified {f['figure']} ({f['publisher']}, {f['license_status']}) for {slug}")

    # Apply figures. Structured topics: data file + builder. Others: Latest Figures.
    page_changes: list[dict] = []
    for slug, figs in sorted(new_figs.items()):
        cfg = WATCH_TOPICS.get(slug, {})
        if cfg.get("data_file"):
            res = apply_structured(slug, cfg, figs, today, repo_root, write)
            page_changes.append(res)
            continue
        lst = state["figures"].setdefault(slug, [])
        have = {f["id"] for f in lst}
        for f in figs:
            if f["id"] not in have:
                lst.append({k: v for k, v in f.items() if k != "topic"})
                have.add(f["id"])
    _prune(state, today)

    for slug in sorted(set(state["figures"]) | _pages_with_block(topics_dir, existing)):
        if WATCH_TOPICS.get(slug, {}).get("data_file") or slug not in existing:
            continue
        path = topics_dir / slug / "index.html"
        page = path.read_text(encoding="utf-8")
        new, changed = apply_latest_figures(page, labels.get(slug, slug), state["figures"].get(slug, []), today)
        if changed:
            if write:
                path.write_text(new, encoding="utf-8")
            page_changes.append({"slug": slug, "kind": "latest-figures",
                                 "note": f"Latest Figures block refreshed ({len(state['figures'].get(slug, []))} figures); dates bumped"})

    state["updated"] = today.isoformat()
    state["last_run"] = {"date": today.isoformat(), "stories": report[:40], "pages": page_changes,
                         "fetched": fetched, "hits": len(hits)}
    return state


def _cited_in_data_file(slug: str, key: str, repo_root: Path) -> bool:
    """True when the story URL is already a study in the topic's data file."""
    import json
    cfg = WATCH_TOPICS.get(slug, {})
    if not cfg.get("data_file"):
        return False
    try:
        data = json.loads((repo_root / cfg["data_file"]).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    urls = [s.get("url", "") for s in (data.get("studies") or {}).values()]
    urls += [r.get("url", "") for r in data.get("rows") or []]
    return key in {canonical(u) for u in urls if u}


def _pages_with_block(topics_dir: Path, existing: set[str]) -> set[str]:
    out = set()
    for slug in existing:
        p = topics_dir / slug / "index.html"
        if LF_START in p.read_text(encoding="utf-8"):
            out.add(slug)
    return out


def apply_structured(slug: str, cfg: dict, figs: list[dict], today: date, repo_root: Path, write: bool) -> dict:
    """Add verified figures to a topic's data file and rerun its builder. Fail closed."""
    import importlib
    import json
    import sys

    path = repo_root / cfg["data_file"]
    original = path.read_text(encoding="utf-8")
    data, added = add_watch_rows(json.loads(original), figs, today)
    if not added:
        return {"slug": slug, "kind": "data-file", "note": "figures already in the data file; nothing added"}
    if not write:
        return {"slug": slug, "kind": "data-file", "note": f"dry run: would add {len(added)} watch row(s)"}
    sys.path.insert(0, str(repo_root / "scripts"))
    builder = importlib.import_module(cfg["builder"])
    page_path = Path(builder.PAGE_PATH)
    page_before = page_path.read_text(encoding="utf-8")
    indent = len(re.match(r"\{\n( *)", original).group(1)) if re.match(r"\{\n( *)", original) else 2
    path.write_text(json.dumps(data, indent=indent or None, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        rc = builder.main(["--date", today.isoformat()])
    except Exception as exc:  # builder bug: restore and alert
        rc = f"{type(exc).__name__}: {exc}"
    if rc != 0:
        path.write_text(original, encoding="utf-8")
        page_path.write_text(page_before, encoding="utf-8")
        return {"slug": slug, "kind": "data-file", "warning": True,
                "note": f"builder failed ({rc}); data file and page restored, nothing published"}
    return {"slug": slug, "kind": "data-file",
            "note": f"added {len(added)} watch row(s) ({', '.join(r['license_status'] for r in added)}); builder rerun"}


# --------------------------------------------------------------------------- summary


def _md(text: str) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def summary_markdown(state: dict) -> str:
    run = state.get("last_run") or {}
    stories = run.get("stories") or []
    lines = ["## Topic data to review", ""]
    lines.append(f"{run.get('hits', 0)} data stories found, {run.get('fetched', 0)} source pages fetched.")
    lines.append("")
    if stories:
        lines += ["| Story | Source | Signals | Topics | Trend | Action |", "|---|---|---|---|---|---|"]
        for s in stories:
            sig = s.get("signals") or {}
            bits = (sig.get("publishers") or []) + (sig.get("figures") or []) + (sig.get("words") or [])
            lines.append(
                f"| [{_md(s['title'])}]({s['url']}) | {_md(s['source'])} | {_md(', '.join(bits[:5]))} | "
                f"{_md(', '.join(s.get('topics') or []) or 'none')} | {s.get('trend')}"
                f"{' (digest)' if s.get('on_digest') else ''} | {_md('; '.join(s.get('actions') or []))} |"
            )
    else:
        lines.append("No survey or data stories in today's pool.")
    pages = run.get("pages") or []
    lines += ["", "**Topic pages changed by the data watch:**", ""]
    lines += [f"- `{p['slug']}`: {_md(p['note'])}" for p in pages] or ["- none"]
    lines += ["", "Figures are quoted only when the sentence is on the fetched source page and names a known "
              "research publisher. Nothing the data watch writes is charted.", ""]
    return "\n".join(lines)
