"""voice_pilot.py: render Voices pilot pages from data/voices/pilot.json.

A pilot page is a one-page guide to a writer, top to bottom: name and a
one-line identity dek, a short sourced bio with "Last updated", where they
write, Start here picks with a curator note each, recent pieces from the
digest (static HTML), topics they return to, related voices, and a
"Compiled from public sources" line. Person + ProfilePage JSON-LD carries
sameAs links to the writer's outlets.

Drafts carry "reviewed": false until Tom signs off. needs_noindex() keeps an
unreviewed page out of the index when it is only an auto list (no bio and no
Start here picks).

Topic hubs link back through a marker block (render_topic_voices_block /
inject_topic_voices) placed before AEO-RELATED-TOPICS.

No em dashes anywhere in rendered copy (assert_no_em_dash).
"""
from __future__ import annotations

import html as html_mod
import json
import re
from datetime import date
from pathlib import Path

from curator.voice_generator import (
    FOOTER_HTML,
    HEADER_HTML,
    NAV_CSS,
    NAV_HTML,
    PERSON_MARKER,
    SITE_URL,
    TOPICS_SUBMENU_CSS,
    voice_page_title,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT_PATH = REPO_ROOT / "data" / "voices" / "pilot.json"

ROBOTS_NOINDEX = '<meta name="robots" content="noindex, follow" />'
CORRECTIONS_URL = "/about/#contact"

TOPIC_START = "<!-- CC-TOPIC-VOICES:START -->"
TOPIC_END = "<!-- CC-TOPIC-VOICES:END -->"
TOPIC_ANCHOR = "<!-- AEO-RELATED-TOPICS:START -->"

RECENT_START = "<!-- CC-RECENT-ARTICLES:START -->"
RECENT_END = "<!-- CC-RECENT-ARTICLES:END -->"


def _esc(text) -> str:
    return html_mod.escape(str(text or ""), quote=True)


def load_pilot(path: Path = PILOT_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pilot_slugs(path: Path = PILOT_PATH) -> set[str]:
    try:
        return {w["slug"] for w in load_pilot(path)["writers"]}
    except (OSError, ValueError, KeyError):
        return set()


def has_curated_content(entry: dict) -> bool:
    return bool((entry.get("bio") or "").strip() or entry.get("start_here"))


def needs_noindex(entry: dict) -> bool:
    """Unreviewed pages that are only an auto list stay out of the index."""
    return not entry.get("reviewed") and not has_curated_content(entry)


def page_title(entry: dict) -> str:
    if entry.get("page_kind") == "where_to_start":
        return f"Where to Start with {entry['name']}: Articles and Bio | Christian Curator"
    return voice_page_title(entry["name"])


def page_heading(entry: dict) -> str:
    if entry.get("page_kind") == "where_to_start":
        return f"Where to start with {entry['name']}"
    return entry["name"]


def fmt_date(iso: str) -> str:
    if not iso:
        return ""
    if re.fullmatch(r"\d{4}", iso):
        return iso
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return date(y, m, d).strftime("%B %-d, %Y")
    except ValueError:
        return iso


def meta_description(entry: dict) -> str:
    text = entry.get("dek") or entry.get("bio") or f"Articles on Christian Curator credited to {entry['name']}."
    text = text.replace(" | ", ", ")
    if len(text) > 158:
        text = text[:155].rsplit(" ", 1)[0] + "..."
    return text


def render_schema(entry: dict) -> str:
    url = f"{SITE_URL}/voices/{entry['slug']}/"
    person = {"@type": "Person", "@id": f"{url}#person", "name": entry["name"], "url": url}
    if entry.get("bio"):
        person["description"] = entry["bio"]
    same_as = [u for u in entry.get("same_as") or [] if u]
    if same_as:
        person["sameAs"] = same_as
    data = {
        "@context": "https://schema.org",
        "@type": "ProfilePage",
        "url": url,
        "name": page_title(entry),
        "mainEntity": person,
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE_URL}/"},
                {"@type": "ListItem", "position": 2, "name": "Voices", "item": f"{SITE_URL}/voices/"},
                {"@type": "ListItem", "position": 3, "name": entry["name"], "item": url},
            ],
        },
    }
    if entry.get("last_updated"):
        data["dateModified"] = entry["last_updated"]
    body = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return f'  <script type="application/ld+json" data-cc-marker="{PERSON_MARKER}">\n{body}\n  </script>'


def _section(label: str, inner: str, cls: str = "") -> str:
    return (
        f'\n    <section class="cc-vp-section{(" " + cls) if cls else ""}">'
        f'\n      <h2 class="cc-vp-label">{_esc(label)}</h2>{inner}'
        f'\n    </section>'
    )


def render_bio(entry: dict, last_updated: str) -> str:
    bio = (entry.get("bio") or "").strip()
    if not bio:
        return ""
    sources = " &middot; ".join(
        f'<a href="{_esc(s["url"])}" target="_blank" rel="noopener">{_esc(s["label"])}</a>'
        for s in entry.get("bio_sources") or []
    )
    src_line = f'Source: {sources}. ' if sources else ""
    return _section(
        "About",
        f'\n      <p class="cc-vp-bio">{_esc(bio)}</p>'
        f'\n      <p class="cc-vp-source">{src_line}Last updated {_esc(fmt_date(last_updated))}.</p>',
    )


def render_where(entry: dict) -> str:
    outlets = entry.get("where_they_write") or []
    if not outlets:
        return ""
    label = "Where to read" if entry.get("deceased") else "Where they write"
    items = "".join(
        f'\n        <li><a href="{_esc(o["url"])}" target="_blank" rel="noopener">{_esc(o["outlet"])}</a></li>'
        for o in outlets
    )
    return _section(label, f'\n      <ul class="cc-vp-outlets">{items}\n      </ul>')


def render_start_here(entry: dict) -> str:
    picks = entry.get("start_here") or []
    if not picks:
        return ""
    items = ""
    for p in picks:
        meta = " &middot; ".join(_esc(b) for b in (p.get("outlet"), fmt_date(p.get("date", ""))) if b)
        items += (
            '\n        <li class="cc-vp-pick">'
            f'\n          <a class="cc-vp-pick-title" href="{_esc(p["url"])}" target="_blank" rel="noopener">{_esc(p["title"])}</a>'
            f'\n          <div class="cc-vp-meta">{meta}</div>'
            f'\n          <p class="cc-vp-note">{_esc(p["note"])}</p>'
            '\n        </li>'
        )
    return _section("Start here", f'\n      <ol class="cc-vp-picks">{items}\n      </ol>')


def render_topics(entry: dict, topic_names: dict[str, str]) -> str:
    topics = [t for t in entry.get("topics") or [] if t["slug"] in topic_names]
    if not topics:
        return ""
    items = "".join(
        f'\n        <li><a href="/topics/{_esc(t["slug"])}/">{_esc(topic_names[t["slug"]])}</a>'
        f'<span class="cc-vp-angle">{_esc(t["angle"])}</span></li>'
        for t in topics
    )
    label = "Topics in this work" if entry.get("deceased") else "Topics they return to"
    return _section(label, f'\n      <ul class="cc-vp-topics">{items}\n      </ul>')


def render_related(entry: dict, voice_names: dict[str, str]) -> str:
    related = [s for s in entry.get("related") or [] if s in voice_names]
    if not related:
        return ""
    items = "".join(
        f'\n        <li><a href="/voices/{_esc(s)}/">{_esc(voice_names[s])}</a></li>' for s in related
    )
    return _section("Related voices", f'\n      <ul class="cc-vp-related">{items}\n      </ul>')


PILOT_CSS = """
    .cc-breadcrumb{font-size:11px;color:#aaa;margin-bottom:1.5rem;}
    .cc-breadcrumb a{color:#2C4A2E;text-decoration:none;}
    .cc-breadcrumb span{margin:0 6px;}
    .cc-vp-hero{margin-bottom:2rem;padding-bottom:1.5rem;border-bottom:2px solid #1a1a1a;}
    .cc-vp-name{font-family:"Lora",Georgia,serif;font-size:30px;font-weight:600;line-height:1.2;color:#1a1a1a;margin-bottom:6px;}
    .cc-vp-dek{font-size:15px;color:#555;line-height:1.5;}
    .cc-vp-section{margin:0 0 2.25rem;}
    .cc-vp-label{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;margin-bottom:0.8rem;}
    .cc-vp-bio{font-family:"Lora",Georgia,serif;font-size:17px;line-height:1.75;color:#1a1a1a;margin-bottom:0.6rem;}
    .cc-vp-source{font-size:12px;color:#888;}
    .cc-vp-source a{color:#2C4A2E;}
    .cc-vp-outlets,.cc-vp-topics,.cc-vp-related{list-style:none;}
    .cc-vp-outlets li,.cc-vp-related li{padding:0.35rem 0;}
    .cc-vp-outlets a,.cc-vp-related a,.cc-vp-topics a{color:#2C4A2E;font-weight:600;text-decoration:none;}
    .cc-vp-outlets a:hover,.cc-vp-related a:hover,.cc-vp-topics a:hover{text-decoration:underline;}
    .cc-vp-topics li{padding:0.45rem 0;border-bottom:1px solid #f0ede8;}
    .cc-vp-angle{display:block;font-size:14px;color:#555;margin-top:2px;}
    .cc-vp-picks{list-style:decimal;padding-left:1.3rem;}
    .cc-vp-pick{margin-bottom:1.2rem;}
    .cc-vp-pick-title{font-family:"Lora",Georgia,serif;font-size:17px;font-weight:600;line-height:1.35;color:#1a1a1a;text-decoration:none;}
    .cc-vp-pick-title:hover{color:#2C4A2E;text-decoration:underline;}
    .cc-vp-meta{font-size:12px;color:#888;margin-top:2px;}
    .cc-vp-note{font-size:15px;color:#333;line-height:1.6;margin-top:4px;}
    .cc-vp-compiled{margin-top:2.5rem;padding-top:1rem;border-top:1px solid #e0ddd8;font-size:12px;color:#888;}
    .cc-vp-compiled a{color:#2C4A2E;}
    .cc-recent{margin:0 0 2.25rem;}
    .cc-back-link{display:inline-block;margin-top:1.5rem;font-size:13px;color:#2C4A2E;text-decoration:none;font-weight:600;border-bottom:1px solid #2C4A2E;}
    .cc-footer{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #e0ddd8;font-size:12px;color:#aaa;text-align:center;line-height:1.8;}
    .cc-footer-name{font-family:"Lora",serif;font-size:14px;color:#888;margin-bottom:4px;}
    .cc-footer-nav{display:flex;justify-content:center;gap:1.5rem;margin-bottom:6px;}
    .cc-footer-nav a{color:#aaa;text-decoration:none;font-size:12px;}"""

BASE_CSS = """
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
    body{font-family:"Source Sans 3",sans-serif;background:#faf9f7;color:#1a1a1a;font-size:16px;line-height:1.5;}
    .cc-root{max-width:980px;margin:0 auto;padding:0 20px 3rem;}
    main.cc-prose{max-width:740px;margin:0 auto;padding-top:1.5rem;}
    .cc-header{border-bottom:1px solid #e0ddd8;padding:0.75rem 0 0;margin-bottom:2.5rem;}
    .cc-top-bar{display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;font-size:12px;color:#888;}
    .cc-subscribe-btn{background:#2C4A2E;color:#fff;padding:5px 14px;font-size:12px;border-radius:3px;text-decoration:none;font-family:inherit;}
    .cc-masthead{text-align:center;padding:0.5rem 0 1rem;border-bottom:2.5px solid #1a1a1a;}
    .cc-site-name{font-family:"Lora",Georgia,serif;font-size:46px;font-weight:600;letter-spacing:-0.02em;color:#1a1a1a;text-decoration:none;display:block;}
    .cc-tagline{font-size:12px;letter-spacing:0.18em;text-transform:uppercase;color:#888;margin:8px 0 0;font-weight:300;}
    @media(max-width:600px){.cc-site-name{font-size:32px;}}"""


def render_pilot_page(entry: dict, *, recent_html: str, voice_names: dict[str, str],
                      topic_names: dict[str, str], last_updated: str) -> str:
    slug, name = entry["slug"], entry["name"]
    title = page_title(entry)
    desc = meta_description(entry)
    url = f"{SITE_URL}/voices/{slug}/"
    robots = f"\n  {ROBOTS_NOINDEX}" if needs_noindex(entry) else ""
    dek = f'\n      <p class="cc-vp-dek">{_esc(entry["dek"])}</p>' if entry.get("dek") else ""

    body = (
        render_bio(entry, last_updated)
        + render_where(entry)
        + render_start_here(entry)
        + (f"\n{recent_html.strip()}" if recent_html else "")
        + render_topics(entry, topic_names)
        + render_related(entry, voice_names)
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_esc(title)}</title>
  <meta name="description" content="{_esc(desc)}" />{robots}
  <link rel="canonical" href="{url}" />
  <meta property="og:type" content="profile" />
  <meta property="og:site_name" content="Christian Curator" />
  <meta property="og:title" content="{_esc(title)}" />
  <meta property="og:description" content="{_esc(desc)}" />
  <meta property="og:url" content="{url}" />
  <meta property="og:image" content="{SITE_URL}/og-image.png" />
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-3NJ5DSPFXL"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","G-3NJ5DSPFXL");</script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet" />
{render_schema(dict(entry, last_updated=last_updated))}
  <style>{BASE_CSS}
    {NAV_CSS}
    {TOPICS_SUBMENU_CSS}{PILOT_CSS}
  </style>
</head>
<body>
<div class="cc-root">

{HEADER_HTML.format(nav=NAV_HTML)}

  <main class="cc-prose" data-cc-voice-pilot="{'reviewed' if entry.get('reviewed') else 'draft'}">
    <div class="cc-breadcrumb">
      <a href="/">Home</a><span>&rsaquo;</span>
      <a href="/voices/">Voices</a><span>&rsaquo;</span>
      {_esc(name)}
    </div>
    <header class="cc-vp-hero">
      <h1 class="cc-vp-name">{_esc(page_heading(entry))}</h1>{dek}
    </header>{body}
    <p class="cc-vp-compiled">Compiled from public sources. Corrections: <a href="{CORRECTIONS_URL}">contact Christian Curator</a>.</p>
    <a href="/voices/" class="cc-back-link">&larr; All Voices</a>
  </main>

{FOOTER_HTML}

</div>
</body>
</html>
"""
    assert_no_em_dash(page)
    return page


def assert_no_em_dash(text: str) -> None:
    if "—" in text:
        i = text.index("—")
        raise ValueError(f"em dash in rendered voice pilot copy: ...{text[max(0, i - 60):i + 20]}...")


# ── Topic hub back-links ─────────────────────────────────────────────────────

def topic_voice_map(writers: list[dict]) -> dict[str, list[tuple[dict, str]]]:
    """topic slug -> [(writer, angle)] for indexable pilot writers."""
    out: dict[str, list[tuple[dict, str]]] = {}
    for w in writers:
        if needs_noindex(w):
            continue
        for t in w.get("topics") or []:
            out.setdefault(t["slug"], []).append((w, t["angle"]))
    return out


TOPIC_BLOCK_CSS = (
    "<style>.cc-topic-voices{margin:2rem 0;padding:1.1rem 1.4rem;background:#fff;border:1px solid #e0ddd8;"
    "border-radius:5px;}.cc-topic-voices-label{font-size:10px;font-weight:700;letter-spacing:0.16em;"
    "text-transform:uppercase;color:#2C4A2E;margin-bottom:0.6rem;}.cc-topic-voices ul{list-style:none;}"
    ".cc-topic-voices li{padding:0.35rem 0;font-size:14px;color:#555;line-height:1.5;}"
    ".cc-topic-voices a{color:#2C4A2E;font-weight:600;text-decoration:none;}"
    ".cc-topic-voices a:hover{text-decoration:underline;}</style>"
)


def render_topic_voices_block(pairs: list[tuple[dict, str]]) -> str:
    items = "".join(
        f'\n    <li><a href="/voices/{_esc(w["slug"])}/">{_esc(w["name"])}</a>: {_esc(angle)}</li>'
        for w, angle in sorted(pairs, key=lambda p: p[0]["name"].split()[-1].lower())
    )
    block = (
        f"{TOPIC_START}\n"
        f'<aside class="cc-topic-voices">{TOPIC_BLOCK_CSS}'
        f'\n  <div class="cc-topic-voices-label">Writers on this topic</div>'
        f"\n  <ul>{items}\n  </ul>"
        f"\n</aside>\n{TOPIC_END}"
    )
    assert_no_em_dash(block)
    return block


def inject_topic_voices(html: str, block: str) -> str | None:
    """Replace the block in place, or insert it before AEO-RELATED-TOPICS.

    An empty block removes an existing one. Returns None when there is no
    anchor to insert at.
    """
    block_re = re.compile(re.escape(TOPIC_START) + r".*?" + re.escape(TOPIC_END) + r"\n?", re.DOTALL)
    if block_re.search(html):
        return block_re.sub(lambda _: (block + "\n") if block else "", html, count=1)
    if not block:
        return html
    pos = html.find(TOPIC_ANCHOR)
    if pos == -1:
        return None
    return html[:pos] + block + "\n" + html[pos:]
