#!/usr/bin/env python3
"""Generate /docs/topics/index.html as a real SEO-friendly hub page.

Replaces the legacy redirect stub with a hub that links to every /topics/{slug}/
page. Without this, topics/ is invisible to search engines except through scattered
links from the homepage; with it, topics/ is a 1-click path from the canonical
"Topics" hub URL. Page parses each topic's <title> and <meta description>.
"""
from __future__ import annotations
import html as html_mod
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"
OUTPUT = TOPICS_DIR / "index.html"


def parse_meta(html: str, attr: str, name_value: str) -> str:
    m = re.search(
        rf'<meta[^>]*\s{attr}=["\']{re.escape(name_value)}["\'][^>]*\scontent=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(
        rf'<meta[^>]*\scontent=["\']([^"\']*)["\'][^>]*\s{attr}=["\']{re.escape(name_value)}["\']',
        html, re.IGNORECASE,
    )
    return m.group(1) if m else ""


def parse_title(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html)
    if not m:
        return ""
    title = html_mod.unescape(m.group(1))
    return title.split(" — ")[0].strip()


def collect_topics() -> list[dict]:
    out = []
    for d in sorted(TOPICS_DIR.iterdir()):
        if not d.is_dir():
            continue
        idx = d / "index.html"
        if not idx.exists():
            continue
        h = idx.read_text(encoding="utf-8", errors="replace")
        title = parse_title(h) or d.name.replace("-", " ").title()
        desc = parse_meta(h, "name", "description")
        out.append({"slug": d.name, "title": title, "description": desc})
    return out




def canonical_nav() -> str:
    """Pull the canonical <nav class="cc-nav">…</nav> block from archive_template.html
    and adjust the 'active' class so /topics/ is highlighted."""
    tpl = REPO_ROOT / "frontend" / "archive_template.html"
    if not tpl.exists():
        # Fallback flat nav (won't pass nav-consistency check)
        return (
            '      <nav class="cc-nav" aria-label="Primary">\n'
            '        <a href="/">Home</a>\n'
            '        <a class="active" href="/topics/">Topics</a>\n'
            '        <a href="/voices/">Voices</a>\n'
            '        <a href="/archive/">Archive</a>\n'
            '      </nav>'
        )
    src = tpl.read_text(encoding="utf-8")
    m = re.search(r'<nav\s+class="cc-nav".*?</nav>', src, re.DOTALL)
    if not m:
        return ""
    nav = m.group(0)
    # Strip any existing active classes, then we keep no specific link active
    # (the page header below already says "Topics" prominently).
    nav = re.sub(r'\s+class="active"', '', nav)
    return nav


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Topics — Christian Curator</title>
  <meta name="description" content="Browse {n} curated deep-dive topic hubs — apologetics, theology, the church, culture, family, and more — from across evangelical Christianity." />
  <link rel="canonical" href="https://www.christiancurator.com/topics/" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Christian Curator" />
  <meta property="og:title" content="Topics — Christian Curator" />
  <meta property="og:description" content="Browse {n} curated deep-dive topic hubs across evangelical Christianity." />
  <meta property="og:url" content="https://www.christiancurator.com/topics/" />
  <meta property="og:image" content="https://www.christiancurator.com/og-image.png" />
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-3NJ5DSPFXL"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","G-3NJ5DSPFXL");</script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet" />
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:"Source Sans 3",sans-serif;background:#faf9f7;color:#1a1a1a;font-size:16px;line-height:1.5;}}
    .cc-root{{max-width:880px;margin:0 auto;padding:0 20px 4rem;}}
    .cc-header{{border-bottom:1px solid #e0ddd8;padding:0.75rem 0 0;margin-bottom:2.5rem;}}
    .cc-top-bar{{display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;font-size:12px;color:#888;}}
    .cc-subscribe-btn{{background:#2C4A2E;color:#fff;padding:5px 14px;font-size:12px;border-radius:3px;text-decoration:none;font-family:inherit;}}
    .cc-subscribe-btn:hover{{background:#3a5f3c;}}
    .cc-masthead{{text-align:center;padding:0.5rem 0 1rem;border-bottom:2.5px solid #1a1a1a;}}
    .cc-site-name{{font-family:"Lora",Georgia,serif;font-size:46px;font-weight:600;letter-spacing:-0.02em;color:#1a1a1a;text-decoration:none;display:block;}}
    .cc-site-name:hover{{color:#2C4A2E;}}
    .cc-tagline{{font-size:12px;letter-spacing:0.18em;text-transform:uppercase;color:#888;margin:8px 0 0;font-weight:300;}}
    @media(max-width:600px){{.cc-site-name{{font-size:32px;}}}}
    .cc-nav{{display:flex;justify-content:center;align-items:center;gap:2rem;padding:0.6rem 0 0;border-top:1px solid #e0ddd8;margin-top:0.75rem;}}
    .cc-nav a{{font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#888;text-decoration:none;}}
    .cc-nav a:hover{{color:#2C4A2E;}}
    .cc-nav a.active{{color:#1a1a1a;border-bottom:2px solid #1a1a1a;padding-bottom:2px;}}
    .cc-page-header{{border-bottom:2px solid #1a1a1a;padding-bottom:0.75rem;margin-bottom:0.5rem;}}
    .cc-page-label{{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;margin-bottom:0.4rem;}}
    .cc-page-title{{font-family:"Lora",Georgia,serif;font-size:30px;font-weight:600;color:#1a1a1a;}}
    .cc-page-desc{{font-size:14px;color:#666;line-height:1.65;margin:0.75rem 0 2rem;}}
    .cc-topics-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;}}
    @media(max-width:680px){{.cc-topics-grid{{grid-template-columns:1fr;}}}}
    .cc-topic-card{{display:block;padding:1.1rem 1.2rem;background:#fff;border:1px solid #e0ddd8;border-radius:5px;text-decoration:none;color:#1a1a1a;transition:border-color 0.15s,box-shadow 0.15s;}}
    .cc-topic-card:hover{{border-color:#2C4A2E;box-shadow:0 2px 8px rgba(44,74,46,0.08);}}
    .cc-topic-card-title{{font-family:"Lora",Georgia,serif;font-size:17px;font-weight:600;line-height:1.3;margin-bottom:6px;color:#1a1a1a;}}
    .cc-topic-card-desc{{font-size:13.5px;color:#555;line-height:1.55;}}
    .cc-footer{{margin-top:3rem;padding:1.5rem 0 0;border-top:1px solid #e0ddd8;font-size:12px;color:#888;text-align:center;}}
  </style>
</head>
<body>
  <header class="cc-header">
    <div class="cc-root">
      <div class="cc-top-bar"><span>{today}</span><a class="cc-subscribe-btn" href="/#subscribe">Subscribe</a></div>
      <div class="cc-masthead">
        <a class="cc-site-name" href="/">Christian Curator</a>
        <p class="cc-tagline">The Best of Christian Thought, Curated Daily</p>
      </div>
{nav_block}
    </div>
  </header>

  <main class="cc-root">
    <div class="cc-page-header">
      <div class="cc-page-label">Deep Dives</div>
      <h1 class="cc-page-title">Topics</h1>
    </div>
    <p class="cc-page-desc">{n} curated deep-dive hubs collecting the best evangelical thinking on the questions, controversies, and convictions that shape Christian life today.</p>
    <div class="cc-topics-grid">
{cards}
    </div>
  </main>

  <footer class="cc-footer">
    <div class="cc-root">© {year} Christian Curator</div>
  </footer>
</body>
</html>
"""


def main() -> int:
    topics = collect_topics()
    if not topics:
        print("no topics found", file=sys.stderr)
        return 1
    cards = []
    for t in topics:
        title = html_mod.escape(t["title"])
        desc = html_mod.escape(t["description"])[:180]
        cards.append(
            f'      <a href="/topics/{t["slug"]}/" class="cc-topic-card">\n'
            f'        <div class="cc-topic-card-title">{title}</div>\n'
            f'        <div class="cc-topic-card-desc">{desc}</div>\n'
            f'      </a>'
        )
    page = PAGE.format(
        n=len(topics),
        cards="\n".join(cards),
        today=date.today().strftime("%A, %B %-d, %Y"),
        year=date.today().year,
        nav_block=canonical_nav(),
    )
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUTPUT} with {len(topics)} topics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
