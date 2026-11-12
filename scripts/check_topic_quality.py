"""
check_topic_quality.py — Block placeholder / template-filler entries in the
curated article lists on docs/topics/<slug>/index.html.

Why this exists
---------------
In October 2026 a live review found that /topics/faith-deconstruction/ (one of
the two pages carrying most Search Console impressions) was showing entries
like "Article on On Deconstruction & Faith #1" with href="#", "The Biblical
Basis for On Deconstruction & Faith", and annotations such as "A pastoral
reflection on how Biblical Literacy connects to the gospel…". No script in
this repo generates those strings. They came from an early bulk template and
then survived every later pass because topic pages are hand-curated HTML. This
check stops that kind of filler from shipping again.

What it flags (inside each <article class="cc-article-entry">)
---------------------------------------------------------------
  missing-url        href absent, empty, "#", or not http(s)
  placeholder-title  title contains "Article on"
  template-title     title contains "On <Topic Name>" (the topic name pasted
                     into a stock title) or a stock title stem
  filler-annotation  annotation matches a known boilerplate sentence
  dup-annotation     identical annotation text on 3+ different topic pages

  outlet-mismatch    the credited outlet is a known publisher whose domain is
                     not the link's domain (Christianity Today credited on a
                     thegospelcoalition.org link)
  author-mismatch    the credited author is not among the authors the linked
                     page names (needs cached page metadata, below)
  title-mismatch     the credited title shares no significant word with the
                     linked page's title (needs cached page metadata)

A byline with only an outlet and no author is allowed; many hand-curated pages
use that format on purpose.

Credit checks and the metadata cache
------------------------------------
The author and title checks compare each entry with what the linked page says
about itself. They run offline from data/topic_link_metadata.json, which `--fetch-metadata`
fills by fetching every curated URL not yet cached (title from og:title /
JSON-LD headline / <title>, authors from <meta name="author"> / JSON-LD). When a
page cannot be read, the byline the pipeline stored in docs/article_history.json
is cached instead (its titles may be display rewrites, so they are not used).
Only the committed cache is read by the gate, so a daily run never changes
verdict on its own. Network is used only with that flag; an entry
with no cached metadata, or a page that names no author, is not judged. A
paraphrased title passes as long as it shares one significant word with the
page title, so only a wholly different title is flagged. Added Nov 12 2026
after a curated entry on /topics/predestination-free-will/ credited "Darrell
Cole, Christianity Today" for a TGC article he did not write.

Ratchet, not a cliff
--------------------
Some older pages still contain filler (see the baseline file). Failing on
every one of them would block the whole daily commit, so this check uses a
ratchet. `scripts/topic_quality_baseline.json` records the known violation
count per slug. The check fails if any page has MORE violations than its
baseline, and a page with no baseline entry is allowed none. When you clean a
page, run with --update-baseline so the lower count is locked in.

Where it runs
-------------
`.github/workflows/daily_run.yml` runs it *before* the commit step, so a
regression keeps the run from publishing. `topic_quality.yml` also runs it on
every push that touches docs/topics/, to catch hand edits.

Usage
-----
    python scripts/check_topic_quality.py                  # gate (exit 1 on regression)
    python scripts/check_topic_quality.py --report         # list every violation
    python scripts/check_topic_quality.py --update-baseline
    python scripts/check_topic_quality.py --fetch-metadata   # refresh the cache (network)

The script never modifies topic pages.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOPICS_DIR = ROOT / "docs" / "topics"
BASELINE = Path(__file__).resolve().parent / "topic_quality_baseline.json"
METADATA_CACHE = ROOT / "data" / "topic_link_metadata.json"
HISTORY = ROOT / "docs" / "article_history.json"

sys.path.insert(0, str(ROOT))
try:
    from frontend.topics_data import TOPICS  # type: ignore
    TOPIC_NAMES = {t["slug"]: t["name"] for t in TOPICS}
except Exception:  # topics_data shape changed — fall back to the H1 only
    TOPIC_NAMES = {}

ENTRY_RE = re.compile(r'<article class="cc-article-entry">(.*?)</article>', re.S)
TITLE_RE = re.compile(r'<(div|h[2-4]) class="cc-article-title">\s*(?:<a\b([^>]*)>(.*?)</a>|(.*?))\s*</\1>', re.S)
HREF_RE = re.compile(r'\bhref="([^"]*)"')
ANNOT_RE = re.compile(r'<(div|p) class="cc-article-annotation">(.*?)</\1>', re.S)
H1_RE = re.compile(r'<h1 class="cc-topic-title">(.*?)</h1>', re.S)
BYLINE_RE = re.compile(r'<(div|p) class="cc-article-byline">(.*?)</\1>', re.S)
SOURCE_SPAN_RE = re.compile(r'<span class="source">(.*?)</span>', re.S)

# Credited outlet -> domains its articles live on. An outlet not listed here
# is never judged; only a listed outlet on an unlisted domain is flagged.
OUTLET_DOMAINS = {
    "the gospel coalition": ("thegospelcoalition.org",),
    "desiring god": ("desiringgod.org",),
    "christianity today": ("christianitytoday.com",),
    "crossway": ("crossway.org",),
    "9marks": ("9marks.org",),
    "ligonier": ("ligonier.org",),
    "ligonier ministries": ("ligonier.org",),
    "tabletalk": ("ligonier.org", "tabletalkmagazine.com"),
    "tabletalk magazine": ("ligonier.org", "tabletalkmagazine.com"),
    "first things": ("firstthings.com",),
    "mere orthodoxy": ("mereorthodoxy.com",),
    "erlc": ("erlc.com",),
    "ethics & religious liberty commission": ("erlc.com",),
    "ccef": ("ccef.org",),
    "biologos": ("biologos.org",),
    "acts 29": ("acts29.com",),
    "albertmohler.com": ("albertmohler.com",),
    "albert mohler": ("albertmohler.com",),
    "lifeway research": ("lifewayresearch.com", "research.lifeway.com"),
}

STOPWORDS = set("""a an and the of in on for to with from by at as is are was be it its how why what
when who whom whose which that this these those your our their his her my we you i not no or but
do does did can should would will about into over than then them they he she us vs""".split())

# Stock title stems from the original bulk template. "{t}" is the topic name.
TEMPLATE_TITLE_STEMS = [
    r"^The Biblical Basis for\b",
    r"^Historical Development of On\b",
    r"^Rethinking .* for a New Generation$",
    r"^Defending Traditional Views on On\b",
    r"^Pastoral Care and On\b",
    r"^Unity and Disagreement: On\b",
    r"\bin Evangelical Thought$",
    r"^Contemporary Evangelical [A-Z][\w ]+: A Crisis of Authority$",
]

# Boilerplate annotations. Matched as prefixes after whitespace is collapsed.
FILLER_ANNOTATIONS = [
    r"A pastoral reflection on how ",
    r"A contemporary reflection on how ",
    r"A foundational evangelical perspective on this topic",
    r"An accessible theological survey helping readers understand the major positions",
    r"A collection of essays representing multiple evangelical perspectives",
    r"A careful exegetical study of key biblical passages that inform",
    r"Exploring the practical implications: how pastors should think about",
    r"Tracing how evangelical theology on this topic has evolved",
    r"An analysis of how current cultural pressures are reshaping",
    r"A sophisticated theological defense of classical evangelical teaching",
    r"How younger evangelicals are re-examining inherited positions",
    r"A call for charity and deeper engagement as evangelicals",
]
FILLER_RE = re.compile("|".join(f"(?:^{p})" for p in FILLER_ANNOTATIONS))
STEM_RES = [re.compile(p) for p in TEMPLATE_TITLE_STEMS]


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _topic_names(slug: str, page: str) -> list[str]:
    names = []
    if slug in TOPIC_NAMES:
        names.append(TOPIC_NAMES[slug])
    m = H1_RE.search(page)
    if m:
        h1 = _text(m.group(1))
        names.append(h1[3:] if h1.startswith("On ") else h1)
    return [n for n in dict.fromkeys(names) if n]


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/:?#]+)", url or "")
    host = (m.group(1).lower() if m else "")
    return host[4:] if host.startswith("www.") else host


def _canon(url: str) -> str:
    url = re.sub(r"[?#].*$", "", (url or "").strip())
    url = re.sub(r"^https?://(www\.)?", "", url, flags=re.I)
    return url.rstrip("/").lower()


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", _fold(text)) if len(w) > 2 and w not in STOPWORDS}


def _credited_authors(byline_html: str) -> tuple[list[str], str]:
    """(author names, outlet) from a curated byline like 'A · <span class=source>X</span>'."""
    src = SOURCE_SPAN_RE.search(byline_html)
    outlet = _text(src.group(1)) if src else ""
    people = _text(SOURCE_SPAN_RE.sub(" ", byline_html)).strip(" ·|,")
    people = re.sub(r"^by\b\s*", "", people, flags=re.I)
    names = [n.strip() for n in re.split(r"\s*(?:·|\||,|&|\band\b)\s*", people) if n.strip()]
    return [n for n in names if re.search(r"[A-Za-z]{2}", n) and not _is_org(n, outlet)], outlet


ORG_WORDS_RE = re.compile(
    r"\b(?:coalition|ministries|ministry|institute|magazine|journal|press|publishing|staff|editors|"
    r"research|commission|seminary|church|network|foundation|domain|orthodoxy|god|crossway|9marks|"
    r"today|things|ligonier|tabletalk|erlc|ccef|biologos)\b|\.(?:com|org|net)\b",
    re.I,
)


def _is_org(name: str, outlet: str = "") -> bool:
    """An outlet or organisation standing where a person's name should be."""
    folded = _fold(name).strip()
    return folded == _fold(outlet).strip() or folded in OUTLET_DOMAINS or bool(ORG_WORDS_RE.search(folded))


def _surname(name: str) -> str:
    parts = [p for p in re.findall(r"[a-z']+", _fold(name)) if p not in ("jr", "sr", "ii", "iii", "dr", "rev")]
    return parts[-1] if parts else ""


def author_matches(credited: list[str], page_authors: list[str]) -> bool:
    """True when any credited author's surname appears among the page's authors."""
    blob = " ".join(_fold(a) for a in page_authors)
    return any(_surname(c) and re.search(rf"\b{re.escape(_surname(c))}\b", blob) for c in credited)


def title_matches(credited: str, page_title: str) -> bool:
    a, b = _words(credited), _words(page_title)
    return not a or not b or bool(a & b)


def scan_page(slug: str, page: str, metadata: dict | None = None) -> tuple[list[tuple[str, str]], list[str]]:
    """Return (violations, annotations). Each violation is (code, detail).

    `metadata` maps a canonical URL (see _canon) to {"title", "authors"} for
    the credit checks; without it only the outlet check runs."""
    metadata = metadata or {}
    out: list[tuple[str, str]] = []
    annotations: list[str] = []
    names = _topic_names(slug, page)
    for i, m in enumerate(ENTRY_RE.finditer(page), 1):
        body = m.group(1)
        t = TITLE_RE.search(body)
        _, attrs, linked, bare = (t.groups() if t else ("", "", "", ""))
        title = _text(linked or bare or "")
        href_m = HREF_RE.search(attrs or "")
        href = (href_m.group(1).strip() if href_m else "")
        label = f"#{i} {title[:70]!r}"

        if not href or href == "#" or not re.match(r"https?://", href):
            out.append(("missing-url", label))
        if re.search(r"\bArticle on\b", title):
            out.append(("placeholder-title", label))
        elif any(f"On {n}" in title and title != f"On {n}" for n in names) or any(r.search(title) for r in STEM_RES):
            out.append(("template-title", label))

        b = BYLINE_RE.search(body)
        credited, outlet = _credited_authors(b.group(2)) if b else ([], "")
        domains = OUTLET_DOMAINS.get(_fold(outlet).strip())
        host = _domain(href)
        if domains and host and not any(host == d or host.endswith("." + d) for d in domains):
            out.append(("outlet-mismatch", f"{label}: credited {outlet!r}, links to {host}"))
        meta = metadata.get(_canon(href)) if href else None
        # A link that now redirects somewhere else (an archive or home page) is
        # a dead link, not a miscredit; book listings carry store titles.
        if meta and meta.get("final_url") and _canon(meta["final_url"]) != _canon(href):
            meta = None
        if meta and host in ("amazon.com", "books.google.com"):
            meta = None
        if meta:
            page_authors = [a for a in meta.get("authors") or [] if a and not _is_org(a)]
            if credited and page_authors and not author_matches(credited, page_authors):
                out.append(("author-mismatch", f"{label}: credited {', '.join(credited)!r}, page names {', '.join(page_authors)!r}"))
            if meta.get("title") and not title_matches(title, meta["title"]):
                out.append(("title-mismatch", f"{label}: page title {meta['title'][:70]!r}"))

        a = ANNOT_RE.search(body)
        ann = _text(a.group(2)) if a else ""
        if ann:
            annotations.append(ann)
            if FILLER_RE.search(ann):
                out.append(("filler-annotation", f"{label}: {ann[:70]!r}"))
    return out, annotations


def history_bylines() -> dict:
    """Bylines the pipeline stored in article_history.json, keyed by canonical URL.
    Its titles may be display rewrites, so only the byline is used."""
    if not HISTORY.exists():
        return {}
    try:
        rows = json.loads(HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return {}
    rows = rows if isinstance(rows, list) else rows.get("articles", [])
    out: dict = {}
    for r in rows:
        if r.get("author") and r.get("scored_by") != "backfill":
            for u in (r.get("url"), r.get("canonical_url")):
                if u:
                    out.setdefault(_canon(u), r["author"])
    return out


def load_metadata() -> dict:
    """Cached page metadata keyed by canonical URL. Only the committed cache is
    read, so the daily gate never changes verdict because history grew."""
    meta: dict = {}
    if METADATA_CACHE.exists():
        for url, m in json.loads(METADATA_CACHE.read_text(encoding="utf-8")).get("urls", {}).items():
            if m.get("status") == 200 or m.get("authors"):
                meta[_canon(url)] = m
    return meta


def page_metadata(page: str) -> dict:
    """Title and authors an article page gives for itself."""
    from fetcher.rss_fetcher import _meta_content, page_byline  # lazy: only with --fetch-metadata

    title = _meta_content(page, "og:title")
    if not title:
        m = re.search(r'"headline"\s*:\s*"([^"]+)"', page)
        title = html.unescape(m.group(1)) if m else ""
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
        title = _text(m.group(1)) if m else ""
    byline = page_byline(page)
    authors = [a.strip() for a in re.split(r"\s+and\s+|,\s*", byline) if a.strip()] if byline else []
    return {"title": title.strip(), "authors": authors}


def curated_urls() -> list[str]:
    urls = []
    for path in sorted(TOPICS_DIR.glob("*/index.html")):
        for m in ENTRY_RE.finditer(path.read_text(encoding="utf-8")):
            t = TITLE_RE.search(m.group(1))
            h = HREF_RE.search((t.group(2) if t else "") or "")
            if h and re.match(r"https?://", h.group(1)):
                urls.append(h.group(1).strip())
    return list(dict.fromkeys(urls))


def fetch_metadata(refresh: bool = False, workers: int = 8) -> dict:
    """Fetch every curated URL not yet cached (all of them with refresh) and
    write data/topic_link_metadata.json. Network; opt-in only."""
    import datetime
    from concurrent.futures import ThreadPoolExecutor

    import requests

    cache = json.loads(METADATA_CACHE.read_text(encoding="utf-8")) if METADATA_CACHE.exists() else {"urls": {}}
    todo = [u for u in curated_urls() if refresh or cache["urls"].get(u, {}).get("status") != 200]
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    today = datetime.date.today().isoformat()

    def one(url: str) -> tuple[str, dict]:
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=20)
        except Exception as e:
            return url, {"status": None, "error": type(e).__name__, "fetched_on": today}
        if r.status_code >= 400:
            return url, {"status": r.status_code, "fetched_on": today}
        return url, {"status": 200, "final_url": r.url, "fetched_on": today, **page_metadata(r.text)}

    bylines = history_bylines()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for url, m in ex.map(one, todo):
            # An unreadable page falls back to the byline the pipeline stored.
            if m.get("status") != 200 and bylines.get(_canon(url)):
                m.update(authors=[bylines[_canon(url)]], authors_from="article_history")
            cache["urls"][url] = m
    cache["urls"] = dict(sorted(cache["urls"].items()))
    METADATA_CACHE.parent.mkdir(parents=True, exist_ok=True)
    METADATA_CACHE.write_text(json.dumps(cache, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    ok = sum(1 for u in todo if cache["urls"][u].get("status") == 200)
    print(f"Fetched {len(todo)} curated URL(s): {ok} readable, {len(todo) - ok} failed. Cache: {METADATA_CACHE}")
    return cache


def scan_all() -> dict[str, list[tuple[str, str]]]:
    metadata = load_metadata()
    results: dict[str, list[tuple[str, str]]] = {}
    ann_pages: dict[str, set[str]] = defaultdict(set)
    ann_by_slug: dict[str, list[str]] = {}
    for path in sorted(TOPICS_DIR.glob("*/index.html")):
        slug = path.parent.name
        page = path.read_text(encoding="utf-8")
        v, anns = scan_page(slug, page, metadata)
        results[slug] = v
        ann_by_slug[slug] = anns
        for a in anns:
            ann_pages[a].add(slug)
    for slug, anns in ann_by_slug.items():
        for a in anns:
            if len(ann_pages[a]) >= 3 and not FILLER_RE.search(a):
                results[slug].append(("dup-annotation", f"on {len(ann_pages[a])} pages: {a[:70]!r}"))
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", action="store_true", help="print every violation, not just regressions")
    ap.add_argument("--update-baseline", action="store_true", help="rewrite the baseline to current counts")
    ap.add_argument("--fetch-metadata", action="store_true",
                    help="fetch uncached curated URLs into data/topic_link_metadata.json first (network)")
    ap.add_argument("--refresh", action="store_true", help="with --fetch-metadata, refetch every URL")
    args = ap.parse_args()

    if args.fetch_metadata:
        fetch_metadata(refresh=args.refresh)

    results = scan_all()
    counts = {s: len(v) for s, v in results.items() if v}

    if args.update_baseline:
        BASELINE.write_text(json.dumps(dict(sorted(counts.items())), indent=2) + "\n", encoding="utf-8")
        print(f"Baseline written: {len(counts)} page(s), {sum(counts.values())} known violation(s).")
        return 0

    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
    regressions = {s: c for s, c in counts.items() if c > baseline.get(s, 0)}
    improved = {s: (b, counts.get(s, 0)) for s, b in baseline.items() if counts.get(s, 0) < b}

    if args.report:
        for slug, v in results.items():
            for code, detail in v:
                print(f"{slug}: {code}: {detail}")
        print()

    for slug in sorted(regressions):
        print(f"::error title=Topic quality::{slug} has {counts[slug]} curated-list violation(s) (baseline {baseline.get(slug, 0)})")
        for code, detail in results[slug]:
            print(f"    {code}: {detail}")
    for slug, (b, c) in sorted(improved.items()):
        print(f"{slug}: improved {b} → {c}; run with --update-baseline to lock it in.")

    print(f"Topic quality: {len(counts)} page(s) with known filler, {sum(counts.values())} violation(s); "
          f"{len(regressions)} regression(s).")
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
