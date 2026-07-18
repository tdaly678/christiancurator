#!/usr/bin/env python3
"""build_voice_hubs.py — Generate SEO category hub pages for /voices/.

Creates /voices/<category>/ hub pages (e.g. /voices/pastors/) grouping the
~950 voice profiles by role. Each hub is an indexable CollectionPage with
ItemList schema, breadcrumbs, canonical nav, cards linking to every voice in
the category, and cross-links to sibling hubs.

Also:
  * injects a category-strip block into /voices/index.html (marker-wrapped,
    idempotent) so the master index links every hub;
  * upgrades each voice page's breadcrumb to include its category hub
    (Home > Voices > Pastors > John Piper), adding an inbound link from every
    profile to its hub.

Intended to run in the daily pipeline after backfill_voices_data.py so new
voices are categorized automatically. Safe to re-run anytime.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from curator.voice_generator import load_canonical_nav, avatar_color  # noqa: E402

DOCS_DIR = REPO_ROOT / "docs"
VOICES_DIR = DOCS_DIR / "voices"
VOICES_DATA = DOCS_DIR / "voices_data.json"
BASE = "https://www.christiancurator.com"

STRIP_START = "<!-- CC-VOICE-HUBS:START -->"
STRIP_END = "<!-- CC-VOICE-HUBS:END -->"

# Order matters: first match wins. A "Pastor & Author" is filed under Pastors.
CATEGORIES = [
    {
        "slug": "pastors",
        "name": "Pastors & Church Leaders",
        "short": "Pastors",
        "title": "Evangelical Pastors & Church Leaders Worth Following",
        "desc": "Profiles of evangelical pastors, preachers, and church leaders whose sermons and writing we curate most often — bios, books, and where to read them.",
        "intro": "The pastors and church leaders below shepherd congregations and shape evangelical preaching today. Each profile includes a biography, notable books, and links to their recent writing.",
        "keywords": ["pastor", "preacher", "bishop", "elder", "church planter", "chaplain", "rector", "vicar", "priest", "minister"],
    },
    {
        "slug": "theologians-scholars",
        "name": "Theologians & Scholars",
        "short": "Theologians",
        "title": "Evangelical Theologians & Biblical Scholars",
        "desc": "Profiles of evangelical theologians, seminary professors, and biblical scholars — their traditions, key works, and where to read their latest writing.",
        "intro": "These theologians, professors, and biblical scholars do the deep academic work behind evangelical faith and practice. Each profile covers their tradition, education, and most influential books.",
        "keywords": ["theolog", "professor", "scholar", "seminary", "academic", "historian", "philosopher", "ethicist"],
    },
    {
        "slug": "apologists",
        "name": "Apologists",
        "short": "Apologists",
        "title": "Christian Apologists Worth Following",
        "desc": "Profiles of Christian apologists defending the faith in the public square — their arguments, books, and where to read their latest work.",
        "intro": "Christian apologists make the intellectual case for the faith. The voices below engage skeptics, answer hard questions, and equip believers to give a reason for their hope.",
        "keywords": ["apolog"],
    },
    {
        "slug": "bible-teachers",
        "name": "Bible Teachers",
        "short": "Bible Teachers",
        "title": "Bible Teachers & Study Leaders",
        "desc": "Profiles of gifted Bible teachers and study leaders — their teaching ministries, books, and where to find their latest studies.",
        "intro": "The Bible teachers below open Scripture for churches, conferences, and small groups around the world. Each profile includes their teaching ministry and best-known studies.",
        "keywords": ["bible teacher", "bible study"],
    },
    {
        "slug": "journalists",
        "name": "Journalists & Reporters",
        "short": "Journalists",
        "title": "Journalists Covering Faith & Culture",
        "desc": "Profiles of journalists and reporters covering religion, faith, and culture — their beats, publications, and recent reporting.",
        "intro": "The journalists and reporters below cover religion, faith, and the places where church meets culture. Each profile notes their publication, beat, and notable reporting.",
        "keywords": ["journalist", "reporter", "correspondent", "news", "columnist", "analyst", "fellow"],
    },
    {
        "slug": "ministry-leaders",
        "name": "Ministry Leaders",
        "short": "Ministry Leaders",
        "title": "Evangelical Ministry Leaders & Counselors",
        "desc": "Profiles of ministry leaders, missionaries, counselors, and nonprofit heads serving the evangelical church — their organizations and writing.",
        "intro": "These ministry leaders, missionaries, and counselors serve the church beyond the pulpit — leading organizations, counseling the hurting, and taking the gospel to hard places.",
        "keywords": ["ministry", "missionar", "evangelist", "director", "president", "founder", "counsel", "psycholog", "nonprofit", "leader", "researcher"],
    },
    {
        "slug": "writers",
        "name": "Writers & Authors",
        "short": "Writers",
        "title": "Christian Writers & Authors Worth Reading",
        "desc": "Profiles of Christian writers and authors we curate most often — their books, essays, and where to read their latest work.",
        "intro": "The writers and authors below craft the books, essays, and articles that shape evangelical conversation. Each profile includes a biography and notable books.",
        "keywords": ["writer", "author", "novelist", "poet", "editor", "blogger", "essayist", "commentator", "contributor"],
    },
    {
        "slug": "speakers-creators",
        "name": "Speakers & Content Creators",
        "short": "Speakers",
        "title": "Christian Speakers, Podcasters & Content Creators",
        "desc": "Profiles of Christian speakers, podcasters, and content creators — their platforms, shows, and where to follow their work.",
        "intro": "The speakers, podcasters, and creators below reach audiences through conferences, shows, and digital platforms. Each profile covers their platform and best-known work.",
        "keywords": ["speaker", "podcast", "content creator", "communicator", "musician", "artist", "broadcaster", "host"],
    },
]

CAT_BY_SLUG = {c["slug"]: c for c in CATEGORIES}


def classify(role: str) -> str | None:
    r = (role or "").lower()
    if not r:
        return None
    for cat in CATEGORIES:
        if any(k in r for k in cat["keywords"]):
            return cat["slug"]
    return None


def _esc(t: str) -> str:
    return html_mod.escape(t or "", quote=True)


def load_voices() -> list[dict]:
    return json.loads(VOICES_DATA.read_text(encoding="utf-8"))


def group_voices(voices: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {c["slug"]: [] for c in CATEGORIES}
    for v in voices:
        cat = classify(v.get("role"))
        if cat:
            groups[cat].append(v)

    def sort_key(a):
        parts = re.sub(r"\b(Jr\.?|Sr\.?|PhD\.?)\b", "", a["name"], flags=re.IGNORECASE).strip().split()
        return parts[-1].lower() if parts else a["name"].lower()

    for slug in groups:
        groups[slug].sort(key=sort_key)
    return groups


def render_card(v: dict, i: int) -> str:
    name = v["name"]
    bio = (v.get("bio") or "").strip()
    teaser = bio[:120].rsplit(" ", 1)[0] + "…" if len(bio) > 120 else bio
    initials = v.get("initials") or "".join(
        p[0].upper() for p in name.split()[:3] if p and p[0].isalpha()
    ) or name[:2].upper()
    return (
        f'\n      <a href="/voices/{v["slug"]}/" class="cc-voice-card">'
        f'\n        <div class="cc-voice-card-avatar" style="background:{avatar_color(i)};">{_esc(initials)}</div>'
        f'\n        <div class="cc-voice-card-body">'
        f'\n          <div class="cc-voice-card-name">{_esc(name)}</div>'
        f'\n          <div class="cc-voice-card-role">{_esc(v.get("role") or "")}</div>'
        f'\n          <div class="cc-voice-card-teaser">{_esc(teaser)}</div>'
        f'\n        </div>'
        f'\n      </a>'
    )


def render_jsonld(cat: dict, members: list[dict]) -> str:
    url = f"{BASE}/voices/{cat['slug']}/"
    items = [
        {
            "@type": "ListItem",
            "position": i + 1,
            "url": f"{BASE}/voices/{v['slug']}/",
            "name": v["name"],
        }
        for i, v in enumerate(members)
    ]
    data = [
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": cat["title"],
            "description": cat["desc"],
            "url": url,
            "isPartOf": {"@type": "WebSite", "name": "Christian Curator", "url": BASE},
            "mainEntity": {"@type": "ItemList", "numberOfItems": len(members), "itemListElement": items},
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{BASE}/"},
                {"@type": "ListItem", "position": 2, "name": "Voices", "item": f"{BASE}/voices/"},
                {"@type": "ListItem", "position": 3, "name": cat["name"], "item": url},
            ],
        },
    ]
    return (
        '<script type="application/ld+json">'
        + json.dumps(data, ensure_ascii=False)
        + "</script>"
    )


def sibling_chips(current_slug: str, groups: dict[str, list[dict]]) -> str:
    chips = []
    for c in CATEGORIES:
        if c["slug"] == current_slug or not groups[c["slug"]]:
            continue
        chips.append(
            f'<a href="/voices/{c["slug"]}/" class="cc-hub-chip">{_esc(c["short"])}'
            f' <span class="cc-hub-chip-n">{len(groups[c["slug"]])}</span></a>'
        )
    return "\n        ".join(chips)


def render_hub(cat: dict, members: list[dict], groups: dict[str, list[dict]]) -> str:
    nav_html, nav_css = load_canonical_nav(active="/voices/")
    cards = "".join(render_card(v, i) for i, v in enumerate(members))
    today = date.today().strftime("%B %d, %Y")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{_esc(cat['title'])} — Christian Curator</title>
  <meta name="description" content="{_esc(cat['desc'])}" />
  <link rel="canonical" href="{BASE}/voices/{cat['slug']}/" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Christian Curator" />
  <meta property="og:title" content="{_esc(cat['title'])} — Christian Curator" />
  <meta property="og:description" content="{_esc(cat['desc'])}" />
  <meta property="og:url" content="{BASE}/voices/{cat['slug']}/" />
  <meta property="og:image" content="{BASE}/og-image.png" />
  {render_jsonld(cat, members)}
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-3NJ5DSPFXL"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","G-3NJ5DSPFXL");</script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet" />
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:"Source Sans 3",sans-serif;background:#faf9f7;color:#1a1a1a;font-size:16px;line-height:1.5;}}
    .cc-root{{max-width:760px;margin:0 auto;padding:0 20px 4rem;}}
    .cc-header{{border-bottom:1px solid #e0ddd8;padding:0.75rem 0 0;margin-bottom:2.5rem;}}
    .cc-top-bar{{display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;font-size:12px;color:#888;}}
    .cc-subscribe-btn{{background:#2C4A2E;color:#fff;padding:5px 14px;font-size:12px;border-radius:3px;text-decoration:none;font-family:inherit;}}
    .cc-subscribe-btn:hover{{background:#3a5f3c;}}
    .cc-masthead{{text-align:center;padding:0.5rem 0 1rem;border-bottom:2.5px solid #1a1a1a;}}
    .cc-site-name{{font-family:"Lora",Georgia,serif;font-size:46px;font-weight:600;letter-spacing:-0.02em;color:#1a1a1a;text-decoration:none;display:block;}}
    .cc-site-name:hover{{color:#2C4A2E;}}
    .cc-tagline{{font-size:12px;letter-spacing:0.18em;text-transform:uppercase;color:#888;margin:8px 0 0;font-weight:300;}}
    @media(max-width:600px){{.cc-site-name{{font-size:32px;}}}}
    {nav_css}
    .cc-breadcrumb{{font-size:12px;color:#888;margin-bottom:1.5rem;}}
    .cc-breadcrumb a{{color:#2C4A2E;text-decoration:none;}}
    .cc-breadcrumb span{{margin:0 6px;}}
    .cc-hub-h1{{font-family:"Lora",Georgia,serif;font-size:30px;font-weight:600;letter-spacing:-0.01em;margin-bottom:0.5rem;}}
    .cc-hub-intro{{font-size:15px;color:#555;line-height:1.65;margin-bottom:0.5rem;max-width:640px;}}
    .cc-hub-count{{font-size:12px;color:#888;letter-spacing:0.04em;margin-bottom:2rem;}}
    .cc-voices-grid{{display:grid;grid-template-columns:1fr;gap:0.85rem;}}
    .cc-voice-card{{display:flex;gap:14px;align-items:flex-start;padding:0.9rem 1rem;background:#fff;border:1px solid #e0ddd8;border-radius:4px;text-decoration:none;color:#1a1a1a;transition:border-color 0.15s,box-shadow 0.15s;}}
    .cc-voice-card:hover{{border-color:#2C4A2E;box-shadow:0 1px 6px rgba(44,74,46,0.08);}}
    .cc-voice-card-avatar{{flex:none;width:44px;height:44px;border-radius:50%;color:#fff;display:flex;align-items:center;justify-content:center;font-size:14px;font-weight:600;letter-spacing:0.02em;}}
    .cc-voice-card-name{{font-family:"Lora",Georgia,serif;font-size:16px;font-weight:600;margin-bottom:1px;}}
    .cc-voice-card-role{{font-size:11px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#2C4A2E;margin-bottom:4px;}}
    .cc-voice-card-teaser{{font-size:13px;color:#666;line-height:1.5;}}
    .cc-hub-siblings{{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #e0ddd8;}}
    .cc-hub-siblings-label{{font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#888;margin-bottom:0.75rem;}}
    .cc-hub-chips{{display:flex;flex-wrap:wrap;gap:0.5rem;}}
    .cc-hub-chip{{font-size:12.5px;font-weight:600;color:#2C4A2E;background:#fff;border:1px solid #e0ddd8;border-radius:999px;padding:5px 12px;text-decoration:none;}}
    .cc-hub-chip:hover{{border-color:#2C4A2E;}}
    .cc-hub-chip-n{{color:#999;font-weight:400;margin-left:2px;}}
    .cc-footer{{margin-top:4rem;padding-top:1.5rem;border-top:2.5px solid #1a1a1a;font-size:12px;color:#888;display:flex;justify-content:space-between;flex-wrap:wrap;gap:0.5rem;}}
    .cc-footer a{{color:#2C4A2E;text-decoration:none;}}
  </style>
</head>
<body>
<div class="cc-root">
  <header class="cc-header">
    <div class="cc-top-bar">
      <span>{today}</span>
      <a class="cc-subscribe-btn" href="/#subscribe">Subscribe</a>
    </div>
    <div class="cc-masthead">
      <a class="cc-site-name" href="/">Christian Curator</a>
      <p class="cc-tagline">The best of evangelical writing, curated daily</p>
    </div>
    {nav_html}
  </header>
  <main>
    <div class="cc-breadcrumb">
      <a href="/">Home</a><span>›</span>
      <a href="/voices/">Voices</a><span>›</span>
      {_esc(cat['name'])}
    </div>
    <h1 class="cc-hub-h1">{_esc(cat['title'])}</h1>
    <p class="cc-hub-intro">{_esc(cat['intro'])}</p>
    <div class="cc-hub-count">{len(members)} voices · updated automatically as we curate new work</div>
    <div class="cc-voices-grid">{cards}
    </div>
    <div class="cc-hub-siblings">
      <div class="cc-hub-siblings-label">Browse other categories</div>
      <div class="cc-hub-chips">
        {sibling_chips(cat['slug'], groups)}
        <a href="/voices/" class="cc-hub-chip">All voices</a>
      </div>
    </div>
  </main>
  <footer class="cc-footer">
    <span>© Christian Curator</span>
    <span><a href="/about/">About</a> · <a href="/topics/">Topics</a> · <a href="/voices/">Voices</a> · <a href="/archive/">Archive</a></span>
  </footer>
</div>
</body>
</html>
"""


def build_strip(groups: dict[str, list[dict]]) -> str:
    chips = []
    for c in CATEGORIES:
        n = len(groups[c["slug"]])
        if not n:
            continue
        chips.append(
            f'<a href="/voices/{c["slug"]}/" class="cc-hub-chip">{_esc(c["name"])}'
            f' <span class="cc-hub-chip-n">{n}</span></a>'
        )
    style = (
        "<style>"
        ".cc-hub-strip{margin:0 0 2rem;}"
        ".cc-hub-strip-label{font-size:11px;font-weight:700;letter-spacing:0.12em;"
        "text-transform:uppercase;color:#888;margin-bottom:0.75rem;}"
        ".cc-hub-chips{display:flex;flex-wrap:wrap;gap:0.5rem;}"
        ".cc-hub-chip{font-size:12.5px;font-weight:600;color:#2C4A2E;background:#fff;"
        "border:1px solid #e0ddd8;border-radius:999px;padding:5px 12px;text-decoration:none;}"
        ".cc-hub-chip:hover{border-color:#2C4A2E;}"
        ".cc-hub-chip-n{color:#999;font-weight:400;margin-left:2px;}"
        "</style>"
    )
    return (
        f"\n    {STRIP_START}\n"
        f'    <div class="cc-hub-strip">{style}\n'
        f'      <div class="cc-hub-strip-label">Browse by category</div>\n'
        f'      <div class="cc-hub-chips">\n        '
        + "\n        ".join(chips)
        + f"\n      </div>\n    </div>\n    {STRIP_END}\n"
    )


def inject_strip_into_index(groups: dict[str, list[dict]]) -> bool:
    idx = VOICES_DIR / "index.html"
    if not idx.exists():
        return False
    html = idx.read_text(encoding="utf-8")
    strip = build_strip(groups)
    if STRIP_START in html:
        html = re.sub(
            re.escape(STRIP_START) + r".*?" + re.escape(STRIP_END) + r"\s*",
            strip.lstrip("\n") + "\n",
            html,
            flags=re.DOTALL,
        )
    else:
        m = re.search(r'<div class="cc-voices-grid">', html)
        if not m:
            return False
        html = html[: m.start()] + strip + "    " + html[m.start():]
    idx.write_text(html, encoding="utf-8")
    return True


def update_voice_breadcrumbs(groups: dict[str, list[dict]]) -> int:
    """Insert the category hub link into each voice page breadcrumb."""
    updated = 0
    for slug, members in groups.items():
        cat = CAT_BY_SLUG[slug]
        crumb = (
            f'<a href="/voices/">Voices</a><span>›</span>\n'
            f'<a href="/voices/{slug}/">{_esc(cat["short"])}</a><span>›</span>'
        )
        for v in members:
            page = VOICES_DIR / v["slug"] / "index.html"
            if not page.exists():
                continue
            html = page.read_text(encoding="utf-8")
            if f'href="/voices/{slug}/"' in html:
                continue  # already linked
            # Remove any previously injected hub crumb (category may have changed)
            html2 = re.sub(
                r'<a href="/voices/[a-z0-9-]+/">[^<]+</a><span>›</span>\s*(?=\n?\s*[^<\s])',
                "",
                html,
            )
            new_html, n = re.subn(
                r'<a href="/voices/">Voices</a><span>›</span>',
                crumb,
                html2,
                count=1,
            )
            if n:
                page.write_text(new_html, encoding="utf-8")
                updated += 1
    return updated


def main() -> int:
    voices = load_voices()
    groups = group_voices(voices)

    total = 0
    for cat in CATEGORIES:
        members = groups[cat["slug"]]
        if not members:
            continue
        out_dir = VOICES_DIR / cat["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(render_hub(cat, members, groups), encoding="utf-8")
        total += len(members)
        print(f"  /voices/{cat['slug']}/ — {len(members)} voices")

    if inject_strip_into_index(groups):
        print("  category strip injected into /voices/index.html")

    n = update_voice_breadcrumbs(groups)
    print(f"  breadcrumbs updated on {n} voice pages")

    uncategorized = len(voices) - total
    print(f"done: {total} voices across {sum(1 for c in CATEGORIES if groups[c['slug']])} hubs ({uncategorized} uncategorized, listed on /voices/ only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
