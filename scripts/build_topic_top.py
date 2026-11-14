#!/usr/bin/env python3
"""build_topic_top.py: the top-of-page block on every topic page.

Writes, idempotently, on each docs/topics/<slug>/index.html:

1. Shared assets in <head> between <!-- CC-TOPIC-ASSETS:START/END -->:
   /assets/topic.css and /assets/topic.js (deferred), each with a ?v= content
   hash so a change reaches readers past the browser cache.
2. Section ids on the existing hand-curated sections (an id attribute is added
   to the opening tag only when the tag has none; no copy is touched):
   definition, tldr, key-questions, debate, position-1..4, synthesis, reading.
   The "Recent Articles" block gets id="recent" from build_recent_articles.py.
3. The block between <!-- CC-TOPIC-TOP:START/END -->, right after the TL;DR:
   - every page: the "On this page" jump nav (links only to sections that exist)
     with a Share button (topic.js: native share on phones, else copies a short
     summary plus the URL);
   - pages with data/topic_top/<slug>.json, in this order: What changed line,
     "Where evangelicals disagree" strip (with its own Share button), related
     debates, Start here (three picks from the page's own curated list), the
     Latest line (<!-- CC-TOPIC-LATEST --> markers, refreshed daily by
     build_recent_articles.py), one key number (with a Copy button), and the
     inline Daily Digest signup (hidden source field "topic:<slug>").

Schema of data/topic_top/<slug>.json (all keys but "slug" optional):

{
  "slug": "faith-deconstruction",
  "glance": {
    "question": "Is deconstruction apostasy, a reckoning, or a season to pastor through?",
    "positions": [                       # 2 to 4, in the debate card's order
      {"name": "Deconstruction as Apostasy",
       "claim": "About 12 words, no more than 18.",
       "anchor": "position-1",           # optional; default position-<n>; must exist
       "voices": [{"name": "Doug Wilson", "slug": "doug-wilson"}, {"name": "No page yet"}]}
    ]
  },
  "start_here": [                        # 1 to 3; url MUST be in the page's curated list
    {"kind": "Primer", "url": "https://...", "title": "...", "author": "...",
     "outlet": "...", "why": "One sentence on why to read it first."}
  ],
  "key_number": {
    "figure": "66%", "text": "Sentence containing the figure exactly.",
    "publisher": "Lifeway Research", "study": "Study name", "year": 2019,
    "source_url": "https://...", "fetched": "2026-11-14",
    "license": "reuse" | "own-chart-cite" | "credit",
    "link": "#by-the-numbers"            # optional in-page anchor
  },
  "related": [{"slug": "biblical-inerrancy", "question": "Is the Bible without error?"}],  # max 3
  "changes": [{"date": "2026-11-14", "text": "Added the survey charts."}],  # newest shown
  "latest": true,                        # default true
  "signup": true,                        # default true
  "notes": "free text for editors; never rendered"
}

Rules (validate()): no em or en dashes anywhere; no tracking params; no feed
counts; no "Quiet Revival"; no name listed for the slug in
data/topic_top/flagged_names.json; voices link to /voices/<slug>/ only when the
page exists, is not retired and is indexable (otherwise plain text); Start here
URLs must already be in the page's curated list; the key number must carry its
source URL, publisher, year and the date it was opened, and the figure must
appear in its sentence.

Usage:
  python scripts/build_topic_top.py               # all topic pages
  python scripts/build_topic_top.py --slug faith-deconstruction
  python scripts/build_topic_top.py --check       # validate data files only
  python scripts/build_topic_top.py --dry-run     # report, write nothing
Tests: tests/test_build_topic_top.py
"""
from __future__ import annotations

import argparse
import hashlib
import html as html_mod
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from curator.headline_voice import strip_dashes  # noqa: E402

DOCS = REPO_ROOT / "docs"
TOPICS_DIR = DOCS / "topics"
VOICES_DIR = DOCS / "voices"
ASSETS = DOCS / "assets"
DATA_DIR = REPO_ROOT / "data" / "topic_top"
FLAGGED = DATA_DIR / "flagged_names.json"
NOINDEX = REPO_ROOT / "frontend" / "voices_noindex.json"
REDIRECTS = REPO_ROOT / "frontend" / "voices_redirects.json"
SITE = "https://www.christiancurator.com"

TOP_START = "<!-- CC-TOPIC-TOP:START -->"
TOP_END = "<!-- CC-TOPIC-TOP:END -->"
ASSET_START = "<!-- CC-TOPIC-ASSETS:START -->"
ASSET_END = "<!-- CC-TOPIC-ASSETS:END -->"
LATEST_START = "<!-- CC-TOPIC-LATEST:START -->"
LATEST_END = "<!-- CC-TOPIC-LATEST:END -->"

TOP_KEYS = {"slug", "glance", "start_here", "key_number", "related", "changes",
            "latest", "signup", "notes"}
LICENSES = {"reuse", "own-chart-cite", "credit"}
MAX_CLAIM_WORDS = 18
SIDES = ("side-a", "side-b", "side-c", "side-d")

DASH_RE = re.compile("[–—]")
FEED_COUNT_RE = re.compile(r"\b\d[\d,]*\s+(?:feeds|sources|outlets)\b", re.I)
BANNED_RE = re.compile(r"quiet revival", re.I)
TRACKING_RE = re.compile(r"[?&](?:utm_[a-z]+|fbclid|gclid|mc_eid|ref)=", re.I)
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Opening tags that get an id, in page order: (regex for the tag, id).
ID_TARGETS = [
    (r'<section class="cc-definition"', "definition"),
    (r'<section class="cc-tldr"', "tldr"),
    (r'<section class="cc-key-questions"', "key-questions"),
    (r'<div class="cc-debate"', "debate"),
    (r'<section class="cc-controversy"', "debate"),
    (r'<section class="cc-synthesis"', "synthesis"),
    (r'<h2 class="cc-article-list-label"', "reading"),
]
POSITION_RE = re.compile(
    r'<div class="(?:cc-debate-position-card position|cc-debate-side side)-([a-d])"(?![^>]*\bid=)'
)
TLDR_RE = re.compile(r'<section class="cc-tldr"[^>]*>.*?</section>', re.DOTALL)
CURATED_RE = re.compile(r'<article class="cc-article-entry">.*?</article>', re.DOTALL)
HREF_RE = re.compile(r'href="([^"]+)"')


# ---------------------------------------------------------------- helpers

def esc(text) -> str:
    return html_mod.escape(str(text or ""), quote=True)


def esc_attr(text) -> str:
    """Attribute value that may hold line breaks (share summaries)."""
    return esc(text).replace("\n", "&#10;")


def plain(fragment: str) -> str:
    """HTML fragment -> one line of text."""
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    except OSError:
        return "0"


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def load_data(slug: str, data_dir: Path = DATA_DIR) -> dict | None:
    path = data_dir / f"{slug}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from all_strings(v)


def curated_urls(page_html: str) -> set[str]:
    urls = set()
    for block in CURATED_RE.findall(page_html):
        urls.update(html_mod.unescape(u) for u in HREF_RE.findall(block))
    return urls


def page_ids(page_html: str) -> set[str]:
    return set(re.findall(r'\bid="([^"]+)"', page_html))


class VoiceIndex:
    """Which /voices/ pages may be linked: exists, not retired, indexable."""

    def __init__(self, voices_dir: Path = VOICES_DIR, noindex_path: Path = NOINDEX,
                 redirects_path: Path = REDIRECTS):
        self.voices_dir = voices_dir
        self.noindex = set(load_json(noindex_path, []))
        self.redirects = load_json(redirects_path, {})

    def exists(self, slug: str) -> bool:
        return (self.voices_dir / slug / "index.html").exists()

    def retired(self, slug: str) -> bool:
        return slug in self.redirects

    def linkable(self, slug: str) -> bool:
        if not slug or not self.exists(slug) or self.retired(slug) or slug in self.noindex:
            return False
        head = (self.voices_dir / slug / "index.html").read_text(encoding="utf-8")[:6000]
        return not re.search(r'<meta[^>]+name="robots"[^>]+noindex|<meta[^>]+noindex[^>]+name="robots"', head)


# ---------------------------------------------------------------- validation

def validate(data: dict, slug: str, page_html: str, *, voices: VoiceIndex | None = None,
             flagged: dict | None = None, topics_dir: Path = TOPICS_DIR) -> list[str]:
    """Problems with a data file, as human-readable strings (empty = valid)."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["data file must be a JSON object"]
    if data.get("slug") != slug:
        errs.append(f'"slug" must be "{slug}"')
    for k in data:
        if k not in TOP_KEYS:
            errs.append(f"unknown key {k!r}")
    flagged = load_json(FLAGGED, {}) if flagged is None else flagged
    rendered = {k: v for k, v in data.items() if k != "notes"}
    for s in all_strings(rendered):
        if DASH_RE.search(s):
            errs.append(f"em or en dash in {s[:60]!r}")
        if FEED_COUNT_RE.search(s):
            errs.append(f"feed count in {s[:60]!r}")
        if BANNED_RE.search(s):
            errs.append(f"Quiet Revival is withdrawn and may not be cited: {s[:60]!r}")
        if TRACKING_RE.search(s):
            errs.append(f"tracking parameter in {s[:80]!r}")
        for name in flagged.get(slug, []):
            if name.lower() in s.lower():
                errs.append(f"flagged name {name!r} may not appear in the top block")
    ids = page_ids(ensure_ids(page_html))

    glance = data.get("glance")
    if glance is not None:
        if not isinstance(glance, dict) or not str(glance.get("question", "")).strip():
            errs.append("glance.question is required")
        positions = (glance or {}).get("positions") or []
        if not 2 <= len(positions) <= 4:
            errs.append("glance.positions must have 2 to 4 entries")
        for n, p in enumerate(positions, 1):
            if not p.get("name") or not p.get("claim"):
                errs.append(f"glance.positions[{n}] needs name and claim")
            if len(str(p.get("claim", "")).split()) > MAX_CLAIM_WORDS:
                errs.append(f"glance.positions[{n}].claim is over {MAX_CLAIM_WORDS} words")
            anchor = p.get("anchor") or f"position-{n}"
            if anchor not in ids:
                errs.append(f"glance.positions[{n}] anchor #{anchor} is not on the page")
            for v in p.get("voices") or []:
                if not v.get("name"):
                    errs.append(f"glance.positions[{n}] voice without a name")
                vs = v.get("slug")
                if vs and voices is not None and (not voices.exists(vs) or voices.retired(vs)):
                    errs.append(f"voice /voices/{vs}/ does not exist or is retired")

    picks = data.get("start_here")
    if picks is not None:
        if not 1 <= len(picks) <= 3:
            errs.append("start_here must have 1 to 3 picks")
        curated = curated_urls(page_html)
        for n, p in enumerate(picks, 1):
            for f in ("url", "title", "author", "outlet", "why"):
                if not str(p.get(f, "")).strip():
                    errs.append(f"start_here[{n}].{f} is required")
            if p.get("url") and p["url"] not in curated:
                errs.append(f"start_here[{n}] url is not in the page's curated list: {p['url']}")

    kn = data.get("key_number")
    if kn is not None:
        for f in ("figure", "text", "publisher", "study", "year", "source_url", "fetched", "license"):
            if not str(kn.get(f, "")).strip():
                errs.append(f"key_number.{f} is required")
        if kn.get("figure") and kn.get("text") and str(kn["figure"]) not in str(kn["text"]):
            errs.append("key_number.figure must appear verbatim in key_number.text")
        if kn.get("source_url") and not str(kn["source_url"]).startswith(("https://", "http://")):
            errs.append("key_number.source_url must be a full URL")
        if kn.get("fetched") and not ISO_RE.match(str(kn["fetched"])):
            errs.append("key_number.fetched must be YYYY-MM-DD (the day the source was opened)")
        if kn.get("license") and kn["license"] not in LICENSES:
            errs.append(f"key_number.license must be one of {sorted(LICENSES)}")
        link = kn.get("link")
        if link and link.startswith("#") and link[1:] not in ids:
            errs.append(f"key_number.link {link} is not on the page")

    for n, r in enumerate(data.get("related") or [], 1):
        if not (topics_dir / str(r.get("slug", "")) / "index.html").exists():
            errs.append(f"related[{n}] /topics/{r.get('slug')}/ does not exist")
        if not str(r.get("question", "")).strip():
            errs.append(f"related[{n}].question is required")
    if len(data.get("related") or []) > 3:
        errs.append("related has at most 3 entries")

    for n, c in enumerate(data.get("changes") or [], 1):
        if not ISO_RE.match(str(c.get("date", ""))) or not str(c.get("text", "")).strip():
            errs.append(f"changes[{n}] needs date (YYYY-MM-DD) and text")
    for k in ("latest", "signup"):
        if k in data and not isinstance(data[k], bool):
            errs.append(f"{k} must be true or false")
    return errs


# ---------------------------------------------------------------- page edits

def ensure_ids(page_html: str) -> str:
    """Add ids to existing section tags that lack one. Idempotent."""
    out = page_html
    present = page_ids(out)
    for pattern, ident in ID_TARGETS:
        if ident in present:
            continue
        m = re.search(pattern + r'(?![^>]*\bid=)', out)
        if m:
            out = out[:m.end()] + f' id="{ident}"' + out[m.end():]
            present.add(ident)

    def pos(m: re.Match) -> str:
        ident = f"position-{'abcd'.index(m.group(1)) + 1}"
        if ident in present:
            return m.group(0)
        present.add(ident)
        return f'{m.group(0)} id="{ident}"'

    return POSITION_RE.sub(pos, out)


def ensure_assets(page_html: str) -> str:
    block = (
        f"{ASSET_START}\n"
        f'<link rel="stylesheet" href="/assets/topic.css?v={file_hash(ASSETS / "topic.css")}"/>\n'
        f'<script defer src="/assets/topic.js?v={file_hash(ASSETS / "topic.js")}"></script>\n'
        f"{ASSET_END}"
    )
    block_re = re.compile(re.escape(ASSET_START) + r".*?" + re.escape(ASSET_END), re.DOTALL)
    if block_re.search(page_html):
        return block_re.sub(lambda _: block, page_html, count=1)
    i = page_html.find("</head>")
    if i == -1:
        return page_html
    return page_html[:i] + block + "\n" + page_html[i:]


def page_summary(page_html: str) -> str:
    """Fallback share text: the H1 and the TL;DR's first sentence."""
    h1 = re.search(r'<h1[^>]*>(.*?)</h1>', page_html, re.DOTALL)
    title = plain(h1.group(1)) if h1 else ""
    tldr = TLDR_RE.search(page_html)
    first = ""
    if tldr:
        body = re.sub(r'<div class="cc-tldr-label">.*?</div>', "", tldr.group(0), flags=re.DOTALL)
        text = plain(body)
        m = re.match(r"(.+?[.?!])(\s|$)", text)
        first = m.group(1) if m else text
    return strip_dashes("\n".join(x for x in (title, first) if x))


JUMP_ITEMS = [
    ("Where evangelicals disagree", ("debate",)),
    ("By the numbers", ("by-the-numbers",)),
    ("Questions answered", ("faq", "key-questions")),
    ("Start reading", ("reading",)),
    ("Latest", ("recent",)),
]


def render_jump(page_html: str, share_text: str, print_button: bool) -> str:
    ids = page_ids(page_html)
    links = []
    for label, candidates in JUMP_ITEMS:
        target = next((c for c in candidates if c in ids), None)
        if target:
            links.append(f'<a href="#{target}" data-pos="topic-jump">{esc(label)}</a>')
    buttons = (
        f'<span class="cc-tt-share"><button type="button" class="cc-tt-btn" data-cc-action="share"'
        f' data-share-item="page" data-share-text="{esc_attr(share_text)}">Share</button>'
    )
    if print_button:
        buttons += ' <button type="button" class="cc-tt-btn" data-cc-action="print">Print for a group</button>'
    buttons += "</span>"
    return (
        '<nav class="cc-tt-jump" aria-label="On this page">'
        '<span class="cc-tt-jump-label">On this page</span>'
        + "".join(links) + buttons + "</nav>"
    )


def render_changed(changes: list[dict]) -> str:
    if not changes:
        return ""
    latest = max(changes, key=lambda c: c["date"])
    d = date.fromisoformat(latest["date"])
    return (f'<p class="cc-tt-changed"><strong>What changed:</strong> '
            f'{esc(d.strftime("%b %Y"))}, {esc(latest["text"])}</p>')


def glance_share_text(glance: dict) -> str:
    lines = [glance["question"]]
    lines += [f'{p["name"]}: {p["claim"]}' for p in glance["positions"]]
    return "\n".join(lines)


def render_glance(glance: dict, voices: VoiceIndex) -> str:
    rows = []
    for n, p in enumerate(glance["positions"], 1):
        anchor = p.get("anchor") or f"position-{n}"
        names = []
        for v in p.get("voices") or []:
            if v.get("slug") and voices.linkable(v["slug"]):
                names.append(f'<a href="/voices/{esc(v["slug"])}/" data-pos="topic-voices">{esc(v["name"])}</a>')
            else:
                names.append(esc(v["name"]))
        rows.append(
            f'<li class="{SIDES[n - 1]}"><a class="cc-tt-pos" href="#{esc(anchor)}" data-pos="topic-glance">'
            f'{esc(p["name"])}</a><div class="cc-tt-claim">{esc(p["claim"])}</div>'
            + (f'<div class="cc-tt-voices">{" · ".join(names)}</div>' if names else "")
            + "</li>"
        )
    return (
        '<section class="cc-tt-glance" id="at-a-glance">'
        '<div class="cc-tt-glance-head"><h2 class="cc-tt-label">Where evangelicals disagree</h2>'
        f'<button type="button" class="cc-tt-btn" data-cc-action="share" data-share-item="at-a-glance"'
        f' data-share-text="{esc_attr(glance_share_text(glance))}">Share</button></div>'
        f'<p class="cc-tt-glance-q">{esc(glance["question"])}</p>'
        f'<ol>{"".join(rows)}</ol></section>'
    )


def render_related(related: list[dict]) -> str:
    if not related:
        return ""
    items = "".join(
        f'<li><a href="/topics/{esc(r["slug"])}/" data-pos="topic-related">{esc(r["question"])}</a></li>'
        for r in related
    )
    return f'<nav class="cc-tt-related" aria-label="Related debates"><div class="cc-tt-label">Related debates</div><ul>{items}</ul></nav>'


def short_url(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url).rstrip("/")


def render_start(picks: list[dict]) -> str:
    items = []
    for p in picks:
        kind = f'<div class="cc-tt-start-kind">{esc(p["kind"])}</div>' if p.get("kind") else ""
        items.append(
            f"<li>{kind}"
            f'<a href="{esc(p["url"])}" target="_blank" rel="noopener" data-pos="topic-start"'
            f' data-src="{esc(p["outlet"])}" data-print-url="{esc(short_url(p["url"]))}">{esc(p["title"])}</a>'
            f'<div class="cc-tt-byline">{esc(p["author"])}, {esc(p["outlet"])}</div>'
            f'<div class="cc-tt-why">{esc(p["why"])}</div></li>'
        )
    return (f'<section class="cc-tt-start" id="start-here"><h2 class="cc-tt-label">Start here</h2>'
            f'<ol>{"".join(items)}</ol></section>')


def render_key_number(kn: dict, slug: str) -> str:
    link = kn.get("link") or ""
    cite = f'{kn["publisher"]}, {kn["study"]}, {kn["year"]}'
    copy = f'{kn["text"]} {cite}. {SITE}/topics/{slug}/{link if link.startswith("#") else "#key-number"}'
    more = f' <a href="{esc(link)}" data-pos="topic-keynumber">More figures</a>' if link else ""
    return (
        '<aside class="cc-tt-num" id="key-number" aria-label="Key number">'
        f'<div class="cc-tt-num-fig">{esc(kn["figure"])}</div><div>'
        f'<div class="cc-tt-num-text">{esc(kn["text"])}</div>'
        f'<div class="cc-tt-num-src">Source: <a href="{esc(kn["source_url"])}" target="_blank" rel="noopener"'
        f' data-pos="topic-keynumber" data-src="{esc(kn["publisher"])}">{esc(cite)}</a>.{more}</div>'
        f'<button type="button" class="cc-tt-btn" data-cc-action="copy-stat" data-copy="{esc_attr(copy)}">Copy with source</button>'
        "</div></aside>"
    )


def render_signup(slug: str) -> str:
    return (
        '<aside class="cc-tt-signup" aria-label="Daily Digest signup">'
        "<p><strong>The Daily Digest:</strong> the best of the evangelical conversation, "
        "every morning at 5 AM ET.</p>"
        '<form class="cc-tt-signup-form" action="/#cc-email-box" method="post" novalidate>'
        '<div class="cc-tt-signup-row">'
        '<input type="email" name="email" placeholder="Your email address" required autocomplete="email"'
        ' aria-label="Email address"/>'
        '<button type="submit">Subscribe</button></div>'
        f'<input type="hidden" name="source" value="topic:{esc(slug)}"/>'
        '<input type="text" name="honeypot" value="" tabindex="-1" autocomplete="off" aria-hidden="true"'
        ' class="cc-tt-signup-hp"/></form>'
        '<div class="cc-tt-signup-msg" role="status"></div>'
        '<p class="cc-tt-signup-fine">No spam. Unsubscribe anytime. Protected by reCAPTCHA; Google '
        '<a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Privacy</a> and '
        '<a href="https://policies.google.com/terms" target="_blank" rel="noopener">Terms</a> apply.</p>'
        "</aside>"
    )


def render_latest(items: list[dict]) -> str:
    from build_recent_articles import render_latest_line
    return render_latest_line(items)


def render_block(slug: str, page_html: str, data: dict | None, *, voices: VoiceIndex,
                 latest_items: list[dict] | None = None) -> str:
    """The full CC-TOPIC-TOP block (markers included). page_html must already have ids."""
    data = data or {}
    glance = data.get("glance")
    share = glance_share_text(glance) if glance else page_summary(page_html)
    parts = [render_jump(page_html, share, print_button=bool(glance or data.get("start_here")))]
    if data:
        parts.append(render_changed(data.get("changes") or []))
        if glance:
            parts.append(render_glance(glance, voices))
        parts.append(render_related(data.get("related") or []))
        if data.get("start_here"):
            parts.append(render_start(data["start_here"]))
        if data.get("latest", True):
            parts.append(render_latest(latest_items or []))
        if data.get("key_number"):
            parts.append(render_key_number(data["key_number"], slug))
        if data.get("signup", True):
            parts.append(render_signup(slug))
    body = "\n".join(p for p in parts if p)
    return f'{TOP_START}\n<div class="cc-tt">\n{body}\n</div>\n{TOP_END}'


def insert_top(page_html: str, block: str) -> str:
    block_re = re.compile(re.escape(TOP_START) + r".*?" + re.escape(TOP_END), re.DOTALL)
    if block_re.search(page_html):
        return block_re.sub(lambda _: block, page_html, count=1)
    m = TLDR_RE.search(page_html)
    if not m:
        raise ValueError("no TL;DR section to anchor the top block")
    return page_html[:m.end()] + "\n" + block + page_html[m.end():]


def build_page(slug: str, page_html: str, data: dict | None, *, voices: VoiceIndex,
               latest_items: list[dict] | None = None) -> str:
    out = ensure_assets(ensure_ids(page_html))
    # Ids of blocks this function writes must not be counted when choosing jump
    # links, so strip the old block before rendering.
    block_re = re.compile(re.escape(TOP_START) + r".*?" + re.escape(TOP_END), re.DOTALL)
    base = block_re.sub("", out)
    block = render_block(slug, base, data, voices=voices, latest_items=latest_items)
    return insert_top(out, block)


# ---------------------------------------------------------------- main

def topic_slugs() -> list[str]:
    return sorted(p.parent.name for p in TOPICS_DIR.glob("*/index.html"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug", action="append", help="limit to one slug (repeatable)")
    ap.add_argument("--check", action="store_true", help="validate data files only")
    ap.add_argument("--dry-run", action="store_true", help="write nothing")
    args = ap.parse_args(argv)

    slugs = args.slug or topic_slugs()
    voices = VoiceIndex()
    errors = 0
    for path in sorted(DATA_DIR.glob("*.json")):
        if path.name == FLAGGED.name:
            continue
        s = path.stem
        page = TOPICS_DIR / s / "index.html"
        if not page.exists():
            print(f"::error::{path.relative_to(REPO_ROOT)}: no topic page /topics/{s}/")
            errors += 1
            continue
        if args.slug and s not in args.slug:
            continue
        for e in validate(load_data(s), s, page.read_text(encoding="utf-8"), voices=voices):
            print(f"::error::{path.relative_to(REPO_ROOT)}: {e}")
            errors += 1
    if errors:
        print(f"{errors} problem(s); nothing written.")
        return 1
    if args.check:
        print("topic_top data files: OK")
        return 0

    history = fresh = None
    changed = 0
    for slug in slugs:
        page = TOPICS_DIR / slug / "index.html"
        if not page.exists():
            print(f"skip {slug}: no page")
            continue
        data = load_data(slug)
        items: list[dict] = []
        if data and data.get("latest", True):
            import build_recent_articles as bra
            if history is None:
                history = load_json(bra.HISTORY, [])
                fresh = bra.load_data_watch_fresh()
            items = bra.topic_items(slug, history, fresh)
        html = page.read_text(encoding="utf-8")
        try:
            out = build_page(slug, html, data, voices=voices, latest_items=items)
        except ValueError as e:
            print(f"::warning::{slug}: {e}")
            continue
        if out != html:
            changed += 1
            if not args.dry_run:
                page.write_text(out, encoding="utf-8")
    print(f"topic top blocks: {changed} page(s) {'would change' if args.dry_run else 'updated'}"
          f" of {len(slugs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
