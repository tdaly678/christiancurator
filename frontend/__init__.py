"""
frontend package — renders the HTML digest from the Jinja2 template.
"""

from pathlib import Path
from datetime import date
from jinja2 import Environment, FileSystemLoader
import hashlib
import json
import re

TEMPLATE_DIR = Path(__file__).parent
DOCS_DIR = Path(__file__).parent.parent / "docs"
OUTPUT_HTML = DOCS_DIR / "index.html"
DAILY_DIR = DOCS_DIR / "daily"
ARCHIVE_DIR = DOCS_DIR / "archive"
DIGEST_DIR = DOCS_DIR / "digest"
VOICES_DIR = DOCS_DIR / "voices"
SITEMAP_PATH = DOCS_DIR / "sitemap.xml"
SITEMAP_DIR = DOCS_DIR  # per-section sitemap files live alongside sitemap.xml
RESEARCH_ARTICLES_PATH = DOCS_DIR / "research_articles.json"

# Sources whose articles always qualify for the Research & Data section
# regardless of tagging (in addition to any article tagged "data")
RESEARCH_SOURCES = {"Ryan Burge", "Pew Research", "Barna Group", "Lifeway Research", "Ed Stetzer"}
RESEARCH_MAX = 3          # max slots in the section
RESEARCH_MAX_AGE_DAYS = 60  # articles older than this are retired from the section


def load_research_articles() -> list[dict]:
    """Load the persistent Research & Data article list from docs/research_articles.json."""
    if not RESEARCH_ARTICLES_PATH.exists():
        return []
    try:
        return json.loads(RESEARCH_ARTICLES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def load_voices_by_name() -> dict:
    """Return a {lowercase_name: slug} dict from docs/voices_data.json for author cross-linking."""
    voices_path = DOCS_DIR / "voices_data.json"
    if not voices_path.exists():
        return {}
    try:
        voices = json.loads(voices_path.read_text(encoding="utf-8"))
        return {v["name"].lower(): v["slug"] for v in voices if "name" in v and "slug" in v}
    except Exception:
        return {}


def update_research_articles(new_articles: list[dict]) -> list[dict]:
    """Merge today's data/research articles into the persistent store.

    - Qualifies: articles tagged 'data' OR from a RESEARCH_SOURCES source.
    - New qualifying articles are prepended (most recent first).
    - Duplicates (by URL) are removed, keeping the newer occurrence.
    - Articles older than RESEARCH_MAX_AGE_DAYS are retired.
    - Result is capped at RESEARCH_MAX entries and saved back to disk.
    Returns the updated list.
    """
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime

    def article_age_days(a: dict) -> float:
        pub = a.get("published", "")
        if not pub:
            return 0.0
        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        except Exception:
            return 0.0

    # Identify qualifying articles from today's scored pool
    qualifying = [
        a for a in new_articles
        if "data" in (a.get("tags") or [])
        or a.get("source_name", "") in RESEARCH_SOURCES
    ]

    # Load existing store
    existing = load_research_articles()

    # Build merged list: new first, then existing; dedupe by URL
    merged = qualifying + existing
    seen_urls: set = set()
    deduped = []
    for a in merged:
        url = a.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(a)

    # Retire articles that are too old
    fresh = [a for a in deduped if article_age_days(a) <= RESEARCH_MAX_AGE_DAYS]

    # Cap at max slots
    result = fresh[:RESEARCH_MAX]

    RESEARCH_ARTICLES_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    added = len([a for a in qualifying if a.get("url") not in {e.get("url") for e in existing}])
    if added:
        print(f"  Research & Data: added {added} new article(s), section now has {len(result)} item(s).")
    else:
        print(f"  Research & Data: no new articles today, keeping {len(result)} existing item(s).")
    return result


def render_html(articles: list[dict], pairings: list[dict], yesterday_articles: list[dict] = None,
                daily_summary: dict = None, research_articles: list[dict] = None):
    """Render index.html from template.html using Jinja2."""
    from frontend.topic_matcher import match_topics
    from curator.topic_classifier import classify_articles, compute_featured_topics
    from frontend.topics_data import TOPICS, TOPICS_BY_CATEGORY, CATEGORIES

    def strip_html(value):
        """Strip HTML tags and collapse whitespace for use in templates."""
        if not value:
            return ""
        clean = re.sub(r'<[^>]+>', '', str(value))
        return re.sub(r'\s+', ' ', clean).strip()

    def article_anchor(url: str) -> str:
        """Convert an article URL into a stable 9-char HTML id (letter prefix + 8 hex chars)."""
        return "a" + hashlib.md5((url or "").encode()).hexdigest()[:8]

    def format_author_links(author_str: str, voices: dict, css_class: str = "cc-author-link") -> str:
        """Split a multi-author string and hyperlink each name that has a voice page.

        Splits on commas, semicolons, and the word ' and ' (case-insensitive).
        Linked authors render as <a class={css_class}><strong>Name</strong></a>;
        unlinked authors render as <span class={css_class}><strong>Name</strong></span>
        so per-location styling (color, weight) flows through regardless of voice match.
        Authors are joined with ', '.
        """
        if not author_str:
            return ""
        parts = re.split(r',|;|\s+and\s+', author_str, flags=re.IGNORECASE)
        parts = [p.strip(" \t\n\r.") for p in parts]
        parts = [p for p in parts if p]
        linked = []
        for name in parts:
            slug = voices.get(name.lower(), "") if voices else ""
            if slug:
                linked.append(f'<a href="/voices/{slug}/" class="{css_class}"><strong>{name}</strong></a>')
            else:
                linked.append(f'<span class="{css_class}"><strong>{name}</strong></span>')
        return ", ".join(linked)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    env.tests['contains'] = lambda value, item: item in (value or [])
    env.filters['strip_html'] = strip_html
    env.filters['article_anchor'] = article_anchor
    env.filters['format_author_links'] = format_author_links
    template = env.get_template("template.html")

    # Build simplified pairings for the template
    template_pairings = [
        {
            "topic": p["topic"],
            "point_title": p["point"].get("rewritten_title") or p["point"]["title"],
            "point_url": p["point"]["url"],
            "counterpoint_title": p["counterpoint"].get("rewritten_title") or p["counterpoint"]["title"],
            "counterpoint_url": p["counterpoint"]["url"],
        }
        for p in pairings
    ]

    # Match today's articles and themes to relevant deep-dive topic pages (legacy sidebar)
    matched_topics = match_topics(articles, daily_summary)
    if matched_topics:
        labels = ", ".join(t["label"] for t in matched_topics)
        print(f"  Topic matcher: surfacing '{labels}'")

    # Classify articles against the 36 debate topics → compute featured topics for homepage
    classify_articles(articles)
    featured_topics = compute_featured_topics(articles, top_n=3)
    if featured_topics:
        labels = ", ".join(t["name"] for t in featured_topics)
        print(f"  Featured debates today: {labels}")

    # Build article URL → primary topic lookup so the template can show "More on X" for any article
    from frontend.topics_data import TOPICS_BY_SLUG
    article_topic_map = {}
    for article in articles:
        for slug in article.get("debate_topics", []):
            if slug in TOPICS_BY_SLUG:
                topic = TOPICS_BY_SLUG[slug]
                article_topic_map[article["url"]] = {"slug": slug, "name": topic["name"]}
                break  # use first matched topic only

    # Persist today's featured topics so the email sender can use them (and look up yesterday's)
    _save_featured_topic_log(featured_topics)

    # Build diversified front-page cards: max 2 per topic slug, top 10 total
    front_page_cards = _build_diversified_cards(articles, TOPICS_BY_SLUG, max_per_topic=2, total=10)
    front_page_urls  = {c["article"]["url"] for c in front_page_cards}

    # Build diversified other-headlines: max 2 per topic slug, top 10, excluding front-page URLs
    other_headlines = _build_diversified_headlines(articles, TOPICS_BY_SLUG, front_page_urls, max_per_topic=2, total=10)

    if front_page_cards:
        topics_shown = [c["topic_name"] for c in front_page_cards[:3]]
        print(f"  Front-page cards (top 3): {topics_shown}")

    # Compute recent archive dates for the homepage archive list
    archive_dates = []
    if ARCHIVE_DIR.exists():
        for day_dir in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
            if day_dir.is_dir() and (day_dir / "index.html").exists():
                try:
                    d = date.fromisoformat(day_dir.name)
                    archive_dates.append({
                        "iso": day_dir.name,
                        "display": d.strftime("%B %-d, %Y"),
                    })
                except ValueError:
                    pass
        archive_dates = archive_dates[:20]

    html = template.render(
        articles=articles,
        pairings=template_pairings,
        yesterday_articles=yesterday_articles or [],
        date=date.today().strftime("%B %-d, %Y"),
        daily_summary=daily_summary,
        research_articles=research_articles or load_research_articles(),
        matched_topics=matched_topics,
        featured_topics=featured_topics,
        front_page_cards=front_page_cards,
        other_headlines=other_headlines,
        article_topic_map=article_topic_map,
        all_topics=TOPICS,
        topics_by_category=TOPICS_BY_CATEGORY,
        categories=CATEGORIES,
        archive_dates=archive_dates,
        voices_by_name=load_voices_by_name(),
    )

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Rendered HTML to {OUTPUT_HTML}")

    # Render the standalone daily summary page if we have one
    if daily_summary:
        render_daily_page(daily_summary, env, matched_topics=matched_topics)

    # Render the daily digest page (/digest/)
    render_digest_page(articles, env, featured_topics=featured_topics, yesterday_articles=yesterday_articles)

    # Render the daily archive snapshot and update the archive index
    render_archive_page(articles, template_pairings, env, yesterday_articles=yesterday_articles or [])
    render_archive_index(env)

    # Backfill prev/next + crosslinks on pages predating this feature
    _backfill_crosslinks()

    # Regenerate sitemap to include all daily and archive pages
    regenerate_sitemap()


FEATURED_TOPIC_LOG_PATH = DOCS_DIR / "featured_topic_log.json"


def _build_diversified_cards(articles: list, topics_by_slug: dict,
                              max_per_topic: int = 2, total: int = 10) -> list:
    """
    Return up to `total` front-page cards drawn from all non-world-news classified articles,
    capped at `max_per_topic` cards per topic slug.  Cards are sorted by article score so the
    best articles surface first, while no single topic dominates the layout.
    Each card is a dict: {article, topic_name, topic_slug}.
    """
    from curator.topic_classifier import _fmt_date  # reuse existing date formatter

    topic_counts: dict = {}
    cards = []
    seen_urls: set = set()

    # Score-ranked pool: only non-world-news articles that have at least one topic match
    pool = sorted(
        [a for a in articles
         if a.get("source_type") != "world_news" and a.get("debate_topics")],
        key=lambda a: a.get("final_score", 0),
        reverse=True,
    )

    for article in pool:
        if len(cards) >= total:
            break
        url = article.get("url", "")
        if url in seen_urls:
            continue

        # Pick the first valid topic slug
        slug = next(
            (s for s in article.get("debate_topics", []) if s in topics_by_slug),
            None,
        )
        if not slug:
            continue
        if topic_counts.get(slug, 0) >= max_per_topic:
            continue

        topic = topics_by_slug[slug]
        cards.append({
            "article": article,
            "topic_name": topic["name"],
            "topic_slug": slug,
        })
        topic_counts[slug] = topic_counts.get(slug, 0) + 1
        seen_urls.add(url)

    return cards


def _build_diversified_headlines(articles: list, topics_by_slug: dict,
                                  exclude_urls: set, max_per_topic: int = 2,
                                  total: int = 10) -> list:
    """
    Return up to `total` other-headlines articles (non-world-news, not in exclude_urls),
    capped at `max_per_topic` per topic slug.  Articles with no topic match are still
    included but count against a shared 'unclassified' bucket (no per-topic cap applied).
    """
    topic_counts: dict = {}
    headlines = []

    pool = sorted(
        [a for a in articles if a.get("source_type") != "world_news"],
        key=lambda a: a.get("final_score", 0),
        reverse=True,
    )

    for article in pool:
        if len(headlines) >= total:
            break
        url = article.get("url", "")
        if url in exclude_urls:
            continue

        slug = next(
            (s for s in article.get("debate_topics", []) if s in topics_by_slug),
            None,
        )
        if slug and topic_counts.get(slug, 0) >= max_per_topic:
            continue

        headlines.append(article)
        if slug:
            topic_counts[slug] = topic_counts.get(slug, 0) + 1
        exclude_urls.add(url)  # prevent duplicates within this list too

    return headlines


def _save_featured_topic_log(featured_topics: list):
    """Persist today's featured topics to docs/featured_topic_log.json, keeping 30 days."""
    today_iso = date.today().isoformat()

    log = {}
    if FEATURED_TOPIC_LOG_PATH.exists():
        try:
            log = json.loads(FEATURED_TOPIC_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            log = {}

    # Store only the fields the email sender needs (strip heavy article data to just title/url/source/summary)
    def _slim_articles(articles):
        def _plain(text):
            """Strip HTML tags and collapse whitespace."""
            if not text:
                return ""
            clean = re.sub(r'<[^>]+>', '', str(text))
            return re.sub(r'\s+', ' ', clean).strip()

        return [
            {
                "title": a.get("rewritten_title") or a.get("title", ""),
                "url": a.get("url", ""),
                "source_name": a.get("source_name", ""),
                "author": a.get("author", ""),
                "summary": _plain(a.get("summary", "")),
            }
            for a in (articles or [])[:2]
        ]

    log[today_iso] = [
        {
            "slug": t["slug"],
            "name": t["name"],
            "hook": t["hook"],
            "category": t["category"],
            "articles": _slim_articles(t.get("articles", [])),
        }
        for t in (featured_topics or [])
    ]

    # Prune entries older than 30 days
    cutoff = (date.today().replace(day=1)).isoformat()  # rough cutoff
    from datetime import timedelta
    cutoff_iso = (date.today() - timedelta(days=30)).isoformat()
    log = {k: v for k, v in log.items() if k >= cutoff_iso}

    FEATURED_TOPIC_LOG_PATH.write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _slug_to_display(slug: str) -> str:
    """Convert a YYYY-MM-DD slug to a human-readable date string."""
    try:
        return date.fromisoformat(slug).strftime("%B %-d, %Y")
    except ValueError:
        return slug


def render_daily_page(daily_summary: dict, env: Environment, matched_topics: list = None):
    """Render a standalone daily pulse page to docs/daily/YYYY-MM-DD/index.html."""
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    slug = daily_summary["slug"]
    page_dir = DAILY_DIR / slug
    page_dir.mkdir(parents=True, exist_ok=True)

    # Compute prev/next slugs from existing daily pages
    existing = sorted([
        p.name for p in DAILY_DIR.iterdir()
        if p.is_dir() and len(p.name) == 10 and p.name != slug
    ])
    all_slugs = sorted(existing + [slug])
    idx = all_slugs.index(slug)
    prev_slug = all_slugs[idx - 1] if idx > 0 else None
    next_slug = all_slugs[idx + 1] if idx < len(all_slugs) - 1 else None

    template = env.get_template("daily_template.html")
    html = template.render(
        **daily_summary,
        prev_slug=prev_slug,
        prev_date=_slug_to_display(prev_slug) if prev_slug else None,
        next_slug=next_slug,
        next_date=_slug_to_display(next_slug) if next_slug else None,
        archive_date_iso=slug,  # archive is always generated in the same pipeline run
        matched_topics=matched_topics or [],
    )

    output_path = page_dir / "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Rendered daily page to {output_path}")

    # Back-patch the previous daily page so its "next" link now points to today
    if prev_slug:
        _patch_daily_next_link(prev_slug, slug, _slug_to_display(slug))


def _patch_daily_next_link(target_slug: str, next_slug: str, next_display: str):
    """Re-patch an existing daily page to add or update its prev/next nav block."""
    page_path = DAILY_DIR / target_slug / "index.html"
    if not page_path.exists():
        return

    # Recompute prev for the target page
    all_slugs = sorted([
        p.name for p in DAILY_DIR.iterdir()
        if p.is_dir() and len(p.name) == 10
    ])
    idx = all_slugs.index(target_slug) if target_slug in all_slugs else -1
    prev_slug = all_slugs[idx - 1] if idx > 0 else None

    prev_html = (
        f'<a href="/daily/{prev_slug}/">← {_slug_to_display(prev_slug)}</a>'
        if prev_slug else ''
    )
    next_html = f'<a href="/daily/{next_slug}/">{next_display} →</a>'
    has_archive = (ARCHIVE_DIR / target_slug / "index.html").exists()
    archive_line = (
        f'\n      <p class="cc-archive-crosslink">'
        f'<a href="/archive/{target_slug}/">See the articles from this day →</a></p>'
        if has_archive else ""
    )

    new_nav = (
        f'<div class="cc-daily-nav">\n'
        f'        <span>{prev_html}</span>\n'
        f'        <span>{next_html}</span>\n'
        f'      </div>{archive_line}'
    )

    content = page_path.read_text(encoding="utf-8")
    nav_pattern = re.compile(r'<div class="cc-daily-nav">.*?</div>', re.DOTALL)
    if nav_pattern.search(content):
        # Replace existing nav div (but preserve any archive crosslink that follows)
        new_content = nav_pattern.sub(
            f'<div class="cc-daily-nav">\n'
            f'        <span>{prev_html}</span>\n'
            f'        <span>{next_html}</span>\n'
            f'      </div>',
            content, count=1
        )
    else:
        # Insert before the cc-back link
        new_content = content.replace(
            '      <a class="cc-back"',
            f'      {new_nav}\n\n      <a class="cc-back"',
            1
        )

    page_path.write_text(new_content, encoding="utf-8")
    print(f"  Updated daily nav on {page_path}")


def render_archive_page(articles: list[dict], pairings: list[dict], env: Environment,
                        yesterday_articles: list[dict] = None):
    """Render a daily archive snapshot to docs/archive/YYYY-MM-DD/index.html."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Top 10 of today's non-world-news articles by final_score
    today_top = sorted(
        [a for a in articles if a.get("source_type") != "world_news"],
        key=lambda a: a.get("final_score", a.get("score", 0)), reverse=True
    )[:10]

    # Top 10 of yesterday's articles (passed in from caller)
    yesterday_top = sorted(
        [a for a in (yesterday_articles or []) if a.get("source_type") != "world_news"],
        key=lambda a: a.get("final_score", a.get("score", 0)), reverse=True
    )[:10]

    today = date.today()
    date_iso = today.isoformat()                          # e.g. "2026-03-22"
    date_display = today.strftime("%B %-d, %Y")           # e.g. "March 22, 2026"

    # Determine prev date: most recent archive day strictly before today
    existing = sorted(
        [p.name for p in ARCHIVE_DIR.iterdir()
         if p.is_dir() and (p / "index.html").exists() and p.name < date_iso]
    )

    prev_date_iso = existing[-1] if existing else None
    prev_date_display = None
    if prev_date_iso:
        try:
            prev_date_display = date.fromisoformat(prev_date_iso).strftime("%B %-d, %Y")
        except ValueError:
            prev_date_iso = None

    # Link to the daily pulse page for this date if one exists
    has_daily_pulse = (DAILY_DIR / date_iso / "index.html").exists()

    template = env.get_template("archive_template.html")
    html = template.render(
        articles=today_top,
        yesterday_articles=yesterday_top,
        pairings=pairings,
        date_iso=date_iso,
        date_display=date_display,
        prev_date_iso=prev_date_iso,
        prev_date_display=prev_date_display,
        next_date_iso=None,
        next_date_display=None,
        daily_slug=date_iso if has_daily_pulse else None,
        voices_by_name=load_voices_by_name(),
    )

    page_dir = ARCHIVE_DIR / date_iso
    page_dir.mkdir(parents=True, exist_ok=True)
    output_path = page_dir / "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Rendered archive page to {output_path}")

    # Write slim metadata for the search/filter index
    _write_archive_meta(page_dir, articles)

    # Back-patch: update the previous day's page so its "next" link points to today
    if prev_date_iso:
        _patch_archive_next_link(prev_date_iso, date_iso, date_display, env, articles, pairings)


def render_digest_page(articles: list[dict], env: Environment,
                       featured_topics: list = None,
                       yesterday_articles: list = None):
    """Render the daily digest page to docs/digest/index.html."""
    from frontend.topics_data import TOPICS, TOPICS_BY_CATEGORY, CATEGORIES

    DIGEST_DIR.mkdir(parents=True, exist_ok=True)

    top10 = sorted(
        [a for a in articles if a.get("source_type") != "world_news"],
        key=lambda a: a.get("final_score", a.get("score", 0)), reverse=True
    )[:10]

    world_news_top3 = sorted(
        [a for a in articles if a.get("source_type") == "world_news"],
        key=lambda a: a.get("final_score", a.get("score", 0)), reverse=True
    )[:3]

    today = date.today()
    date_display = today.strftime("%B %-d, %Y")

    # Compute recent archive dates (same as homepage)
    archive_dates = []
    if ARCHIVE_DIR.exists():
        for day_dir in sorted(ARCHIVE_DIR.iterdir(), reverse=True):
            if day_dir.is_dir() and (day_dir / "index.html").exists():
                try:
                    d = date.fromisoformat(day_dir.name)
                    archive_dates.append({
                        "iso": day_dir.name,
                        "display": d.strftime("%B %-d, %Y"),
                    })
                except ValueError:
                    pass
        archive_dates = archive_dates[:20]

    template = env.get_template("digest_template.html")
    # Top 10 yesterday articles by score
    yesterday_top10 = sorted(
        [a for a in (yesterday_articles or []) if a.get("source_type") != "world_news"],
        key=lambda a: a.get("final_score", a.get("score", 0)), reverse=True
    )[:10]

    html = template.render(
        articles=top10,
        yesterday_articles=yesterday_top10,
        world_news_articles=world_news_top3,
        date=date_display,
        iso_date=today.isoformat(),
        featured_topics=featured_topics or [],
        topics_by_category=TOPICS_BY_CATEGORY,
        categories=CATEGORIES,
        archive_dates=archive_dates,
        voices_by_name=load_voices_by_name(),
    )

    output_path = DIGEST_DIR / "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Rendered digest page to {output_path}")


def _split_author_names(author_str: str) -> list[str]:
    """Split a multi-author byline (commas, semicolons, ' and ') into clean individual names."""
    if not author_str:
        return []
    parts = re.split(r',|;|\s+and\s+', author_str, flags=re.IGNORECASE)
    return [p.strip(" \t\n\r.") for p in parts if p.strip(" \t\n\r.")]


def _write_archive_meta(page_dir: Path, articles: list[dict]):
    """Write a slim meta.json alongside the archive page for the filter index."""
    non_world = [a for a in articles if a.get("source_type") != "world_news"]

    def _author(a):
        auth = (a.get("author") or "").strip()
        src  = (a.get("source_name") or "").strip()
        return auth if auth and auth.lower() != src.lower() else ""

    article_data = []
    for a in non_world:
        if not a.get("url"):
            continue
        auth_str = _author(a)
        article_data.append({
            "title":   a.get("rewritten_title") or a.get("title", ""),
            "url":     a.get("url", ""),
            "author":  auth_str,
            "authors": _split_author_names(auth_str),
            "source":  (a.get("source_name") or "").strip(),
            "tags":    a.get("tags") or [],
        })

    authors = sorted({name for d in article_data for name in d["authors"]})
    sources = sorted(set(d["source"] for d in article_data if d["source"]))
    tags    = sorted(set(t for d in article_data for t in d["tags"]))

    with open(page_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump({"authors": authors, "sources": sources, "tags": tags,
                   "articles": article_data}, f, ensure_ascii=False)


def _patch_archive_next_link(
    target_iso: str, next_iso: str, next_display: str,
    env: Environment, today_articles: list[dict], today_pairings: list[dict]
):
    """Re-render a previous archive page with an updated next-day navigation link."""
    page_dir = ARCHIVE_DIR / target_iso
    output_path = page_dir / "index.html"
    if not output_path.exists():
        return

    try:
        target_date = date.fromisoformat(target_iso)
        target_display = target_date.strftime("%B %-d, %Y")
    except ValueError:
        return

    # Find that day's prev (one step earlier in the archive)
    existing = sorted(
        [p.name for p in ARCHIVE_DIR.iterdir() if p.is_dir() and (p / "index.html").exists()]
    )
    idx = existing.index(target_iso) if target_iso in existing else -1
    prev_iso = existing[idx - 1] if idx > 0 else None
    prev_display = None
    if prev_iso:
        try:
            prev_display = date.fromisoformat(prev_iso).strftime("%B %-d, %Y")
        except ValueError:
            prev_iso = None

    # We don't store each day's article data, so we re-read the existing HTML's
    # article links via a lightweight string replacement of the nav section only.
    # Simpler: just re-render with empty articles (the content is already written);
    # instead, do a targeted string replace of the nav block.
    with open(output_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace the archive-nav block using a simple marker approach
    import re
    nav_pattern = re.compile(
        r'(<div class="cc-archive-nav">)(.*?)(</div>)',
        re.DOTALL
    )

    new_nav_inner = "\n"
    if prev_iso:
        new_nav_inner += f'      <a href="/archive/{prev_iso}/">← {prev_display}</a>\n'
    new_nav_inner += '      <a href="/archive/">All Archives</a>\n'
    new_nav_inner += f'      <a href="/archive/{next_iso}/">{next_display} →</a>\n'
    # Preserve / add daily pulse crosslink if one exists for this archive day
    if (DAILY_DIR / target_iso / "index.html").exists():
        new_nav_inner += (
            f'      <div class="cc-archive-nav-pulse">'
            f'<a href="/daily/{target_iso}/">Read the editorial pulse for this day →</a>'
            f'</div>\n'
        )
    new_nav_inner += '    '

    new_content = nav_pattern.sub(
        lambda m: m.group(1) + new_nav_inner + m.group(3),
        content,
        count=1
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  Updated archive nav on {output_path}")


def _backfill_archive_meta():
    """Generate meta.json for archive days that don't have one (or are missing article data),
    by parsing existing HTML."""
    for day_dir in ARCHIVE_DIR.iterdir():
        if not day_dir.is_dir():
            continue
        meta_path = day_dir / "meta.json"
        html_path = day_dir / "index.html"
        if not html_path.exists():
            continue
        # Re-run backfill if meta.json is missing or lacks the articles key
        if meta_path.exists():
            try:
                existing = json.loads(meta_path.read_text(encoding="utf-8"))
                if "articles" in existing:
                    continue
            except Exception:
                pass
        try:
            content = html_path.read_text(encoding="utf-8")

            article_data = []

            # Lead article (has distinct cc-lead-title / cc-author / cc-source classes)
            lead_m = re.search(
                r'<a href="([^"]+)" class="cc-lead-title"[^>]*>([^<]+)</a>'
                r'.*?<div class="cc-lead-meta">(.*?)</div>',
                content, re.DOTALL
            )
            if lead_m:
                url   = lead_m.group(1)
                title = lead_m.group(2).strip()
                meta_html = lead_m.group(3)
                author = (re.findall(r'<span class="cc-author">([^<]+)</span>', meta_html) or [""])[0].strip()
                source = (re.findall(r'<span class="cc-source">([^<]+)</span>', meta_html) or [""])[0].strip()
                tags   = re.findall(r'<span class="cc-article-tag">([^<]+)</span>', meta_html)
                article_data.append({"title": title, "url": url, "author": author, "source": source, "tags": tags})

            # Article list items (cc-article-title links + adjacent cc-article-meta divs)
            for m in re.finditer(
                r'<a href="([^"]+)" class="cc-article-title"[^>]*>([^<]+)</a>\s*'
                r'<div class="cc-article-meta">(.*?)</div>',
                content, re.DOTALL
            ):
                url       = m.group(1)
                title     = m.group(2).strip()
                meta_html = m.group(3)
                tags      = re.findall(r'<span class="cc-article-tag">([^<]+)</span>', meta_html)
                spans     = [s.strip() for s in re.findall(r'<span>([^<]+)</span>', meta_html)
                             if s.strip() and s.strip() != "·"]
                if len(spans) >= 2:
                    author, source = spans[0], spans[-1]
                elif spans:
                    author, source = "", spans[0]
                else:
                    author, source = "", ""
                article_data.append({"title": title, "url": url,
                                     "author": author,
                                     "authors": _split_author_names(author),
                                     "source": source, "tags": tags})

            # Also enrich the lead entry (first item) with split author names
            if article_data:
                article_data[0]["authors"] = _split_author_names(article_data[0].get("author", ""))

            authors = sorted({name for d in article_data for name in d.get("authors", [])})
            sources = sorted(set(d["source"] for d in article_data if d["source"]))
            tags    = sorted(set(t for d in article_data for t in d["tags"]))

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump({"authors": authors, "sources": sources, "tags": tags,
                           "articles": article_data}, f, ensure_ascii=False)
        except Exception as e:
            print(f"  Warning: could not backfill meta for {day_dir.name}: {e}")


def _backfill_crosslinks():
    """Backfill prev/next + archive links on existing daily pages that predate this feature,
    and add daily pulse links to existing archive pages that are missing them."""

    # --- Daily pages: add prev/next nav + archive crosslink ---
    if not DAILY_DIR.exists():
        return
    all_daily_slugs = sorted([
        p.name for p in DAILY_DIR.iterdir()
        if p.is_dir() and len(p.name) == 10 and (p / "index.html").exists()
    ])

    patched_daily = 0
    for idx, slug in enumerate(all_daily_slugs):
        page_path = DAILY_DIR / slug / "index.html"
        content = page_path.read_text(encoding="utf-8")
        if 'cc-daily-nav' in content:
            continue  # already has nav from new template

        prev_slug = all_daily_slugs[idx - 1] if idx > 0 else None
        next_slug = all_daily_slugs[idx + 1] if idx < len(all_daily_slugs) - 1 else None
        has_archive = (ARCHIVE_DIR / slug / "index.html").exists()

        prev_html = (
            f'<a href="/daily/{prev_slug}/">← {_slug_to_display(prev_slug)}</a>'
            if prev_slug else ''
        )
        next_html = (
            f'<a href="/daily/{next_slug}/">{_slug_to_display(next_slug)} →</a>'
            if next_slug else ''
        )
        nav_html = (
            f'<div class="cc-daily-nav">\n'
            f'        <span>{prev_html}</span>\n'
            f'        <span>{next_html}</span>\n'
            f'      </div>'
        )
        if has_archive:
            nav_html += (
                f'\n      <p class="cc-archive-crosslink">'
                f'<a href="/archive/{slug}/">See the articles from this day →</a></p>'
            )

        if '      <a class="cc-back"' in content:
            new_content = content.replace(
                '      <a class="cc-back"',
                f'      {nav_html}\n\n      <a class="cc-back"',
                1
            )
            page_path.write_text(new_content, encoding="utf-8")
            patched_daily += 1

    if patched_daily:
        print(f"  Backfilled crosslinks on {patched_daily} daily page(s).")

    # --- Archive pages: add daily pulse link to nav if missing ---
    if not ARCHIVE_DIR.exists():
        return

    patched_archive = 0
    nav_pattern = re.compile(r'(<div class="cc-archive-nav">)(.*?)(</div>)', re.DOTALL)
    for day_dir in sorted(ARCHIVE_DIR.iterdir()):
        if not day_dir.is_dir() or not (day_dir / "index.html").exists():
            continue
        try:
            date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        slug = day_dir.name
        if not (DAILY_DIR / slug / "index.html").exists():
            continue  # no daily pulse for this date

        page_path = day_dir / "index.html"
        content = page_path.read_text(encoding="utf-8")
        if 'cc-archive-nav-pulse' in content:
            continue  # already has the link

        pulse_div = (
            f'<div class="cc-archive-nav-pulse">'
            f'<a href="/daily/{slug}/">Read the editorial pulse for this day →</a>'
            f'</div>\n    '
        )
        m = nav_pattern.search(content)
        if m:
            new_content = (
                content[:m.start(3)] +
                '\n      ' + pulse_div +
                content[m.start(3):]
            )
            page_path.write_text(new_content, encoding="utf-8")
            patched_archive += 1

    if patched_archive:
        print(f"  Backfilled daily pulse links on {patched_archive} archive page(s).")


def render_archive_index(env: Environment):
    """Regenerate docs/archive/index.html — a filterable chronological listing of all archive days."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Backfill meta.json for any archive days that pre-date this feature
    _backfill_archive_meta()

    # Collect all dated subdirectories with full article-level metadata
    days = []
    all_authors: set = set()
    all_sources: set = set()
    all_tags: set = set()

    for day_dir in ARCHIVE_DIR.iterdir():
        if not day_dir.is_dir() or not (day_dir / "index.html").exists():
            continue
        try:
            d = date.fromisoformat(day_dir.name)
        except ValueError:
            continue
        meta = {}
        meta_path = day_dir / "meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                pass
        authors  = meta.get("authors", [])
        sources  = meta.get("sources", [])
        tags     = meta.get("tags", [])
        articles = meta.get("articles", [])
        all_authors.update(authors)
        all_sources.update(sources)
        all_tags.update(tags)
        days.append({
            "iso":      day_dir.name,
            "display":  d.strftime("%B %-d, %Y"),
            "weekday":  d.strftime("%A"),
            "articles": articles,
        })

    days.sort(key=lambda x: x["iso"], reverse=True)

    # Group by month for the default day-list view
    from collections import OrderedDict
    months: dict = OrderedDict()
    for day in days:
        month_key = day["iso"][:7]
        try:
            month_label = date.fromisoformat(day["iso"]).strftime("%B %Y")
        except ValueError:
            month_label = month_key
        if month_key not in months:
            months[month_key] = {"label": month_label, "days": []}
        months[month_key]["days"].append(day)

    sorted_authors = sorted(all_authors)
    sorted_sources = sorted(all_sources)
    sorted_tags    = sorted(all_tags)

    # Serialise article data for embedding in the page (escape </script> sequences)
    archive_data_json = json.dumps(
        [{"iso": d["iso"], "display": d["display"], "articles": d["articles"]} for d in days],
        ensure_ascii=False
    ).replace("</script>", "<\\/script>")

    def opt(val, label=None):
        label = label or val
        escaped = val.replace('"', '&quot;')
        return f'        <option value="{escaped}">{label}</option>'

    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '  <meta charset="UTF-8" />',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        '  <title>Christian Curator — Archive</title>',
        '  <meta name="description" content="Browse all past issues of Christian Curator — a daily digest of evangelical Christian news, theology, and culture." />',
        '  <link rel="canonical" href="https://www.christiancurator.com/archive/" />',
        '  <script async src="https://www.googletagmanager.com/gtag/js?id=G-3NJ5DSPFXL"></script>',
        '  <script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag("js",new Date());gtag("config","G-3NJ5DSPFXL");</script>',
        '  <link rel="preconnect" href="https://fonts.googleapis.com" />',
        '  <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet" />',
        '  <style>',
        '    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}',
        '    body{font-family:"Source Sans 3",sans-serif;background:#faf9f7;color:#1a1a1a;font-size:16px;line-height:1.5;}',
        '    .cc-root{max-width:640px;margin:0 auto;padding:0 20px 4rem;}',
        '    .cc-header{border-bottom:1px solid #e0ddd8;padding:0.75rem 0 0;margin-bottom:2rem;}',
        '    .cc-top-bar{display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;font-size:12px;color:#888;}',
        '    .cc-back-link{font-size:12px;color:#2C4A2E;text-decoration:none;font-weight:600;}',
        '    .cc-back-link:hover{text-decoration:underline;}',
        '    .cc-subscribe-btn{background:#2C4A2E;color:#fff;border:none;padding:5px 14px;font-size:12px;border-radius:3px;cursor:pointer;font-family:"Source Sans 3",sans-serif;text-decoration:none;display:inline-block;}',
        '    .cc-subscribe-btn:hover{background:#3a5f3c;}',
        '    .cc-masthead{text-align:center;padding:0.5rem 0 1rem;border-bottom:2.5px solid #1a1a1a;}',
        '    .cc-site-name{font-family:"Lora",Georgia,serif;font-size:46px;font-weight:600;letter-spacing:-0.02em;line-height:1;color:#1a1a1a;text-decoration:none;}',
        '    .cc-site-name:hover{color:#2C4A2E;}',
        '    .cc-tagline{font-size:12px;letter-spacing:0.18em;text-transform:uppercase;color:#888;margin:8px 0 0;font-weight:300;}',
        '    h1{font-family:"Lora",Georgia,serif;font-size:24px;font-weight:600;margin:1.75rem 0 0.5rem;}',
        '    .cc-archive-intro{font-size:14px;color:#666;margin-bottom:1.25rem;}',
        '    .cc-filter-bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:0.5rem;}',
        '    .cc-filter-bar select{font-family:"Source Sans 3",sans-serif;font-size:12px;color:#1a1a1a;background:#fff;border:1px solid #d0cdc8;border-radius:3px;padding:5px 8px;cursor:pointer;flex:1;min-width:140px;}',
        '    .cc-filter-bar select:focus{outline:none;border-color:#2C4A2E;}',
        '    .cc-filter-clear{font-family:"Source Sans 3",sans-serif;font-size:12px;background:none;border:1px solid #d0cdc8;border-radius:3px;padding:5px 12px;cursor:pointer;color:#888;white-space:nowrap;}',
        '    .cc-filter-clear:hover{border-color:#2C4A2E;color:#2C4A2E;}',
        '    .cc-filter-count{font-size:12px;color:#888;margin-bottom:1.25rem;min-height:1.2em;}',
        '    .cc-month{margin-bottom:2rem;}',
        '    .cc-month-label{font-size:10px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;padding-bottom:0.5rem;border-bottom:1px solid #e0ddd8;margin-bottom:0.75rem;}',
        '    .cc-day-link{display:flex;align-items:baseline;gap:10px;padding:0.6rem 0;border-bottom:1px solid #f0ede8;text-decoration:none;color:#1a1a1a;}',
        '    .cc-day-link:last-child{border-bottom:none;}',
        '    .cc-day-link:hover .cc-day-display{text-decoration:underline;text-decoration-color:#2C4A2E;}',
        '    .cc-day-weekday{font-size:11px;color:#aaa;min-width:60px;}',
        '    .cc-day-display{font-family:"Lora",Georgia,serif;font-size:15px;font-weight:500;}',
        '    .cc-result-group{margin-bottom:2rem;}',
        '    .cc-result-date{font-size:10px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;padding-bottom:0.5rem;border-bottom:1px solid #e0ddd8;margin-bottom:0.75rem;}',
        '    .cc-result-date a{color:#2C4A2E;text-decoration:none;}',
        '    .cc-result-date a:hover{text-decoration:underline;}',
        '    .cc-result-item{padding:0.75rem 0;border-bottom:1px solid #f0ede8;}',
        '    .cc-result-item:last-child{border-bottom:none;}',
        '    .cc-result-title{font-family:"Lora",Georgia,serif;font-size:15px;font-weight:500;line-height:1.35;color:#1a1a1a;text-decoration:none;display:block;margin-bottom:4px;}',
        '    .cc-result-title:hover{text-decoration:underline;text-decoration-color:#2C4A2E;}',
        '    .cc-result-meta{font-size:11.5px;color:#aaa;}',
        '    .cc-result-meta .cc-meta-dot{margin:0 4px;}',
        '    .cc-footer{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #e0ddd8;text-align:center;font-size:12px;color:#aaa;}',
        '    .cc-footer a{color:#2C4A2E;text-decoration:none;}',
        '    .cc-footer a:hover{text-decoration:underline;}',
        '    .cc-nav{display:flex;justify-content:center;align-items:center;gap:2rem;padding:0.6rem 0 0;border-top:1px solid #e0ddd8;margin-top:0.75rem;}',
        '    .cc-nav a{font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#888;text-decoration:none;}',
        '    .cc-nav a:hover{color:#2C4A2E;}',
        '    .cc-nav a.active{color:#1a1a1a;border-bottom:2px solid #1a1a1a;padding-bottom:2px;}',
        '    .cc-nav-dropdown{position:relative;display:inline-block;}',
        '    .cc-nav-dropdown-toggle{font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#1a1a1a;cursor:pointer;display:flex;align-items:center;gap:4px;background:none;border:none;font-family:inherit;padding:0;}',
        '    .cc-nav-dropdown-toggle:hover{color:#2C4A2E;}',
        '    .cc-nav-dropdown-toggle::after{content:"▾";font-size:10px;letter-spacing:0;}',
        '    .cc-nav-dropdown-menu{display:none;position:absolute;top:100%;left:50%;transform:translateX(-50%);background:#fff;border:1px solid #e0ddd8;border-radius:4px;padding:14px 0 6px;min-width:140px;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,0.08);}',
        '    .cc-nav-dropdown:hover .cc-nav-dropdown-menu,.cc-nav-dropdown:focus-within .cc-nav-dropdown-menu{display:block;}',
        '    .cc-nav-dropdown-menu a{display:block;padding:7px 18px;font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#888;text-decoration:none;white-space:nowrap;}',
        '    .cc-nav-dropdown-menu a:hover{color:#2C4A2E;background:#f7f5f2;}',
        '    .cc-nav-dropdown-menu a.active{color:#1a1a1a;}',
        '    /* CC-NAV-TOPICS-SUBMENU:START */',
        '    .cc-nav-dropdown-menu-topics{left:0;transform:none;min-width:220px;padding:6px 0;}',
        '    .cc-nav-submenu{position:relative;}',
        '    .cc-nav-submenu-toggle{display:block;width:100%;text-align:left;padding:7px 18px;background:none;border:none;cursor:pointer;font-family:inherit;font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#888;white-space:nowrap;}',
        '    .cc-nav-submenu-toggle::after{content:"›";float:right;margin-left:18px;color:#bbb;font-weight:400;}',
        '    .cc-nav-submenu-toggle:hover{color:#2C4A2E;background:#f7f5f2;}',
        '    .cc-nav-submenu-panel{display:none;position:absolute;left:100%;top:-7px;background:#fff;border:1px solid #e0ddd8;border-radius:4px;padding:8px 0;min-width:260px;max-height:70vh;overflow-y:auto;box-shadow:0 4px 12px rgba(0,0,0,0.08);z-index:101;}',
        '    .cc-nav-submenu:hover > .cc-nav-submenu-panel,.cc-nav-submenu:focus-within > .cc-nav-submenu-panel{display:block;}',
        '    .cc-nav-submenu-panel a{display:block;padding:6px 18px;font-size:13px;font-weight:500;letter-spacing:0;text-transform:none;color:#333;text-decoration:none;white-space:nowrap;}',
        '    .cc-nav-submenu-panel a:hover{color:#2C4A2E;background:#f7f5f2;}',
        '    /* CC-NAV-TOPICS-SUBMENU:END */',
        '    @media(max-width:600px){.cc-site-name{font-size:32px;}.cc-filter-bar select{min-width:100%;}}',
        '  </style>',
        '</head>',
        '<body>',
        '  <div class="cc-root">',
        '    <header class="cc-header">',
        '      <div class="cc-top-bar">',
        "        <a href='/' class='cc-back-link'>← Today's Digest</a>",
        "        <a href='/#cc-email-box' class='cc-subscribe-btn'>Get the Daily Digest</a>",
        '      </div>',
        '      <div class="cc-masthead">',
        "        <a href='/' class='cc-site-name'>Christian Curator</a>",
        "        <p class='cc-tagline'>Evangelical News &amp; Theology — Curated Daily</p>",
        '      </div>',
        '      <nav class="cc-nav">',
        "        <a href='/'>Home</a>",
        '        <!-- CC-TOPICS-DROPDOWN:START -->',
        '        <div class="cc-nav-dropdown cc-nav-dropdown-topics">',
        '          <button class="cc-nav-dropdown-toggle" aria-haspopup="true">Topics</button>',
        '          <div class="cc-nav-dropdown-menu cc-nav-dropdown-menu-topics">',
        '            <div class="cc-nav-submenu">',
        '              <button class="cc-nav-submenu-toggle" aria-haspopup="true">Core Theology</button>',
        '              <div class="cc-nav-submenu-panel">',
        '                <a href="/topics/apologetics/">Apologetics</a>',
        '                <a href="/topics/baptism/">Baptism</a>',
        '                <a href="/topics/biblical-inerrancy/">Biblical Inerrancy</a>',
        '                <a href="/topics/christology/">Christology</a>',
        '                <a href="/topics/covenant-theology/">Covenant Theology</a>',
        '                <a href="/topics/creation-evolution/">Creation & Evolution</a>',
        '                <a href="/topics/eschatology/">Eschatology & End Times</a>',
        '                <a href="/topics/gender-and-biblical-anthropology/">Gender & Biblical Anthropology</a>',
        '                <a href="/topics/heaven-hell-eternity/">Heaven, Hell & Eternity</a>',
        '                <a href="/topics/israel-and-prophecy/">Israel & Prophecy</a>',
        '                <a href="/topics/justification-by-faith/">Justification by Faith</a>',
        '                <a href="/topics/predestination-free-will/">Predestination & Free Will</a>',
        '                <a href="/topics/suffering-and-providence/">Suffering & Providence</a>',
        '                <a href="/topics/atonement/">The Atonement</a>',
        '                <a href="/topics/holy-spirit-spiritual-gifts/">The Holy Spirit & Spiritual Gifts</a>',
        '                <a href="/topics/lords-supper/">The Lord\'s Supper</a>',
        '                <a href="/topics/the-trinity/">The Trinity</a>',
        '              </div>',
        '            </div>',
        '            <div class="cc-nav-submenu">',
        '              <button class="cc-nav-submenu-toggle" aria-haspopup="true">Church Life</button>',
        '              <div class="cc-nav-submenu-panel">',
        '                <a href="/topics/church-discipline/">Church Discipline</a>',
        '                <a href="/topics/church-governance/">Church Governance</a>',
        '                <a href="/topics/church-history/">Church History</a>',
        '                <a href="/topics/membership/">Church Membership</a>',
        '                <a href="/topics/church-planting/">Church Planting</a>',
        '                <a href="/topics/complementarianism-egalitarianism/">Complementarianism & Egalitarianism</a>',
        '                <a href="/topics/missions-and-evangelism/">Missions & Evangelism</a>',
        '                <a href="/topics/church-accountability/">Pastoral Accountability</a>',
        '                <a href="/topics/preaching/">Preaching</a>',
        '                <a href="/topics/small-groups/">Small Groups</a>',
        '                <a href="/topics/spiritual-abuse/">Spiritual Abuse & Toxic Churches</a>',
        '                <a href="/topics/local-church/">The Local Church</a>',
        '                <a href="/topics/pastoral-ministry/">The Pastor\'s Role</a>',
        '                <a href="/topics/worship-and-liturgy/">Worship & Liturgy</a>',
        '              </div>',
        '            </div>',
        '            <div class="cc-nav-submenu">',
        '              <button class="cc-nav-submenu-toggle" aria-haspopup="true">Spiritual Formation</button>',
        '              <div class="cc-nav-submenu-panel">',
        '                <a href="/topics/anxiety-and-fear/">Anxiety & Fear</a>',
        '                <a href="/topics/biblical-literacy/">Biblical Literacy</a>',
        '                <a href="/topics/christian-friendship/">Christian Friendship & Community</a>',
        '                <a href="/topics/contemplative-prayer/">Contemplative Prayer</a>',
        '                <a href="/topics/death-and-dying/">Death & Dying</a>',
        '                <a href="/topics/faith-deconstruction/">Deconstruction & Faith</a>',
        '                <a href="/topics/discipleship/">Discipleship</a>',
        '                <a href="/topics/fasting/">Fasting</a>',
        '                <a href="/topics/forgiveness/">Forgiveness</a>',
        '                <a href="/topics/grief-and-lament/">Grief & Lament</a>',
        '                <a href="/topics/mental-health/">Mental Health & Faith</a>',
        '                <a href="/topics/pornography/">Pornography & Sexual Purity</a>',
        '                <a href="/topics/prayer/">Prayer</a>',
        '                <a href="/topics/sanctification/">Sanctification</a>',
        '                <a href="/topics/singleness/">Singleness</a>',
        '                <a href="/topics/spiritual-disciplines/">Spiritual Disciplines</a>',
        '                <a href="/topics/spiritual-warfare/">Spiritual Warfare</a>',
        '              </div>',
        '            </div>',
        '            <div class="cc-nav-submenu">',
        '              <button class="cc-nav-submenu-toggle" aria-haspopup="true">Culture & Society</button>',
        '              <div class="cc-nav-submenu-panel">',
        '                <a href="/topics/abortion/">Abortion & the Pro-Life Movement</a>',
        '                <a href="/topics/addiction-and-recovery/">Addiction & Recovery</a>',
        '                <a href="/topics/ai-and-the-church/">Artificial Intelligence & the Church</a>',
        '                <a href="/topics/biblical-justice/">Biblical Justice & the Social Gospel</a>',
        '                <a href="/topics/biblical-sexuality/">Biblical Sexuality</a>',
        '                <a href="/topics/christian-education/">Christian Education</a>',
        '                <a href="/topics/christian-ethics/">Christian Ethics</a>',
        '                <a href="/topics/christian-masculinity/">Christian Masculinity</a>',
        '                <a href="/topics/christian-nationalism/">Christian Nationalism</a>',
        '                <a href="/topics/christian-parenting/">Christian Parenting</a>',
        '                <a href="/topics/creation-care/">Creation Care</a>',
        '                <a href="/topics/marriage-and-family/">Marriage & Family</a>',
        '                <a href="/topics/politics-and-the-church/">Politics & the Church</a>',
        '                <a href="/topics/progressive-christianity/">Progressive Christianity</a>',
        '                <a href="/topics/racial-reconciliation/">Racial Reconciliation</a>',
        '                <a href="/topics/religious-liberty/">Religious Liberty</a>',
        '                <a href="/topics/stewardship-and-generosity/">Stewardship & Generosity</a>',
        '                <a href="/topics/technology-and-discipleship/">Technology & Discipleship</a>',
        '                <a href="/topics/technology/">Technology & the Christian Life</a>',
        '                <a href="/topics/evangelicalism/">The Future of Evangelicalism</a>',
        '                <a href="/topics/prosperity-gospel/">The Prosperity Gospel</a>',
        '                <a href="/topics/vocation-and-work/">Vocation & Work</a>',
        '              </div>',
        '            </div>',
        '          </div>',
        '        </div>',
        '        <!-- CC-TOPICS-DROPDOWN:END -->',
        "        <div class='cc-nav-dropdown'>",
        "          <button class='cc-nav-dropdown-toggle'>Resources</button>",
        "          <div class='cc-nav-dropdown-menu'>",
        "            <a href='/about/'>About</a>",
        "            <a href='/voices/'>Voices</a>",
        "            <a href='/archive/' class='active'>Archive</a>",
        "          </div>",
        "        </div>",
        '      </nav>',
        '    </header>',
        '    <h1>Archive</h1>',
        f'    <p class="cc-archive-intro">Browse {len(days)} past issue{"s" if len(days) != 1 else ""} of Christian Curator.</p>',
        '    <div class="cc-filter-bar">',
        '      <select id="cc-filter-author" onchange="ccApplyFilters()">',
        '        <option value="">All Authors</option>',
        *[opt(a) for a in sorted_authors],
        '      </select>',
        '      <select id="cc-filter-tag" onchange="ccApplyFilters()">',
        '        <option value="">All Tags</option>',
        *[opt(t, t.title()) for t in sorted_tags],
        '      </select>',
        '      <select id="cc-filter-outlet" onchange="ccApplyFilters()">',
        '        <option value="">All Outlets</option>',
        *[opt(s) for s in sorted_sources],
        '      </select>',
        '      <button class="cc-filter-clear" onclick="ccClearFilters()">Clear</button>',
        '    </div>',
        '    <p class="cc-filter-count" id="cc-filter-count"></p>',
        '    <div id="cc-results" style="display:none;"></div>',
        '    <div id="cc-day-list">',
    ]

    for month_data in months.values():
        lines.append('      <div class="cc-month">')
        lines.append(f'        <div class="cc-month-label">{month_data["label"]}</div>')
        for day in month_data["days"]:
            lines.append(
                f'        <a href="/archive/{day["iso"]}/" class="cc-day-link">'
                f'<span class="cc-day-weekday">{day["weekday"]}</span>'
                f'<span class="cc-day-display">{day["display"]}</span>'
                f'</a>'
            )
        lines.append('      </div>')

    lines += [
        '    </div>',  # /cc-day-list
        '    <footer class="cc-footer">',
        '      <p><a href="/">Christian Curator</a> — A daily digest of the best evangelical Christian writing.</p>',
        '      <p style="margin-top:6px;"><a href="/#subscribe">Subscribe to the daily email</a></p>',
        '    </footer>',
        '  </div>',
        f'  <script>var ARCHIVE_DATA={archive_data_json};</script>',
        '  <script>',
        '    function ccApplyFilters() {',
        '      var author = document.getElementById("cc-filter-author").value;',
        '      var tag    = document.getElementById("cc-filter-tag").value;',
        '      var outlet = document.getElementById("cc-filter-outlet").value;',
        '      var dayList = document.getElementById("cc-day-list");',
        '      var resultsEl = document.getElementById("cc-results");',
        '      var countEl = document.getElementById("cc-filter-count");',
        '      if (!author && !tag && !outlet) {',
        '        dayList.style.display = "";',
        '        resultsEl.style.display = "none";',
        '        countEl.textContent = "";',
        '        return;',
        '      }',
        '      dayList.style.display = "none";',
        '      var groups = [];',
        '      var totalArticles = 0;',
        '      var seenUrls = {};',
        '      ARCHIVE_DATA.forEach(function(day) {',
        '        var matching = (day.articles || []).filter(function(a) {',
        '          var authorOk = !author || (a.authors ? a.authors.indexOf(author) !== -1 : a.author === author);',
        '          var tagOk    = !tag    || (a.tags && a.tags.indexOf(tag) !== -1);',
        '          var outletOk = !outlet || a.source === outlet;',
        '          return authorOk && tagOk && outletOk && !seenUrls[a.url];',
        '        });',
        '        matching.forEach(function(a) { seenUrls[a.url] = true; });',
        '        if (matching.length) { groups.push({day: day, articles: matching}); totalArticles += matching.length; }',
        '      });',
        '      var html = "";',
        '      groups.forEach(function(g) {',
        '        html += \'<div class="cc-result-group">\';',
        '        html += \'<div class="cc-result-date"><a href="/archive/\' + g.day.iso + \'/">\' + g.day.display + \'</a></div>\';',
        '        g.articles.forEach(function(a) {',
        '          var meta = a.author ? a.author + \'<span class="cc-meta-dot">·</span>\' + a.source : a.source;',
        '          html += \'<div class="cc-result-item">\';',
        '          html += \'<a href="\' + a.url + \'" class="cc-result-title" target="_blank" rel="noopener">\' + a.title + \'</a>\';',
        '          html += \'<div class="cc-result-meta">\' + meta + \'</div>\';',
        '          html += \'</div>\';',
        '        });',
        '        html += \'</div>\';',
        '      });',
        '      if (!html) html = \'<p style="font-size:14px;color:#888;padding:1rem 0;">No articles found.</p>\';',
        '      resultsEl.innerHTML = html;',
        '      resultsEl.style.display = "";',
        '      var issueWord = groups.length === 1 ? "issue" : "issues";',
        '      var articleWord = totalArticles === 1 ? "article" : "articles";',
        '      countEl.textContent = totalArticles + " " + articleWord + " across " + groups.length + " " + issueWord;',
        '    }',
        '    function ccClearFilters() {',
        '      ["cc-filter-author","cc-filter-tag","cc-filter-outlet"].forEach(function(id){ document.getElementById(id).value = ""; });',
        '      ccApplyFilters();',
        '    }',
        '  </script>',
        '</body>',
        '</html>',
    ]

    output_path = ARCHIVE_DIR / "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Rendered archive index to {output_path} ({len(days)} days listed)")


TOPICS_DIR = DOCS_DIR / "topics"


def _file_mtime_iso(path):
    """Return the file's mtime as a YYYY-MM-DD string, or today if unreadable."""
    try:
        from datetime import datetime, timezone
        ts = path.stat().st_mtime
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    except Exception:
        return date.today().isoformat()


def _write_urlset(path, entries):
    """Write a sitemap urlset file. entries = [(url, changefreq, priority, lastmod), ...]"""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, changefreq, priority, lastmod in entries:
        lines += [
            "  <url>",
            f"    <loc>{url}</loc>",
            f"    <lastmod>{lastmod}</lastmod>",
            f"    <changefreq>{changefreq}</changefreq>",
            f"    <priority>{priority}</priority>",
            "  </url>",
        ]
    lines.append("</urlset>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def regenerate_sitemap():
    """Regenerate sitemap.xml as a sitemap-index pointing to per-section sitemaps.

    Sections: core (home/digest/about/hub indexes), topics, voices, daily, archive.
    Each per-section sitemap uses accurate per-page lastmod (file mtime).

    Priority/changefreq tuned to favor deep evergreen content (topics, voices)
    over high-volume frozen content (daily/archive individual snapshots).
    """
    today_iso = date.today().isoformat()
    base = "https://www.christiancurator.com"

    # --- Core hub URLs (always-on, high priority) ---
    core_entries = [
        (f"{base}/",        "daily",   "1.0", today_iso),
        (f"{base}/digest/", "daily",   "0.9", today_iso),
        (f"{base}/about/",  "monthly", "0.6", today_iso),
        (f"{base}/archive/","daily",   "0.7", today_iso),
    ]
    if (TOPICS_DIR / "index.html").exists():
        core_entries.append((f"{base}/topics/", "weekly", "0.8",
                             _file_mtime_iso(TOPICS_DIR / "index.html")))
    if (VOICES_DIR / "index.html").exists():
        core_entries.append((f"{base}/voices/", "weekly", "0.8",
                             _file_mtime_iso(VOICES_DIR / "index.html")))

    # --- Topics (deepest evergreen content) ---
    topic_entries = []
    if TOPICS_DIR.exists():
        for topic_dir in sorted(TOPICS_DIR.iterdir()):
            idx = topic_dir / "index.html"
            if topic_dir.is_dir() and idx.exists():
                topic_entries.append((
                    f"{base}/topics/{topic_dir.name}/",
                    "weekly", "0.9", _file_mtime_iso(idx),
                ))

    # --- Voices (deep author/contributor profiles) ---
    voice_entries = []
    if VOICES_DIR.exists():
        for voice_dir in sorted(VOICES_DIR.iterdir()):
            idx = voice_dir / "index.html"
            if voice_dir.is_dir() and idx.exists():
                voice_entries.append((
                    f"{base}/voices/{voice_dir.name}/",
                    "monthly", "0.9", _file_mtime_iso(idx),
                ))

    # --- Daily pulse pages (frozen snapshots, lower priority to preserve crawl budget) ---
    daily_entries = []
    if DAILY_DIR.exists():
        for day_dir in sorted(DAILY_DIR.iterdir()):
            idx = day_dir / "index.html"
            if day_dir.is_dir() and idx.exists():
                daily_entries.append((
                    f"{base}/daily/{day_dir.name}/",
                    "never", "0.5", day_dir.name,
                ))

    # --- Individual archive pages ---
    archive_entries = []
    if ARCHIVE_DIR.exists():
        for day_dir in sorted(ARCHIVE_DIR.iterdir()):
            idx = day_dir / "index.html"
            if day_dir.is_dir() and idx.exists():
                archive_entries.append((
                    f"{base}/archive/{day_dir.name}/",
                    "never", "0.5", day_dir.name,
                ))

    # Write per-section sitemaps
    sections = [
        ("sitemap-core.xml",    core_entries),
        ("sitemap-topics.xml",  topic_entries),
        ("sitemap-voices.xml",  voice_entries),
        ("sitemap-daily.xml",   daily_entries),
        ("sitemap-archive.xml", archive_entries),
    ]
    written = []
    for filename, entries in sections:
        if not entries:
            continue
        _write_urlset(SITEMAP_DIR / filename, entries)
        written.append((filename, len(entries)))

    # Write sitemap index at /sitemap.xml
    idx_lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for filename, _count in written:
        idx_lines += [
            "  <sitemap>",
            f"    <loc>{base}/{filename}</loc>",
            f"    <lastmod>{today_iso}</lastmod>",
            "  </sitemap>",
        ]
    idx_lines.append("</sitemapindex>")
    with open(SITEMAP_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(idx_lines) + "\n")

    total = sum(c for _, c in written)
    detail = ", ".join(f"{n}={c}" for n, c in written)
    print(f"  Regenerated sitemap index with {total} URL(s) across {len(written)} sitemaps ({detail}).")
