#!/usr/bin/env python3
"""Generate /docs/topics/index.html, the Topics hub, and refresh the topic
page breadcrumbs.

The hub lists every live topic in one of six categories (frontend/topics_hub.py),
each with a one-line description, a "Four views" tag where the page's debate
grid has four positions, a row of category jump links (/topics/#doctrine) and a
type-to-filter box with synonym matching. Every link is plain HTML; the filter
box is shown only when JavaScript runs, so the page works without it.
Schema: CollectionPage with an ItemList of every topic, plus BreadcrumbList.

The daily workflow runs this script ("Rebuild /topics/ hub index"), so the hub,
its topic count and the Home > Topics > Category breadcrumbs on every topic page
(scripts/add_breadcrumbs.py) stay current. The nav's plain Topics link to this
page is written by scripts/add_topics_nav.py.

Click tracking (P2.1 pattern): every topic link carries data-pos="topics-hub",
data-topic=<slug> and data-category=<hub category id>. One delegated listener
sends the GA4 `article_click` event the homepage sends, with position, topic,
topic_category, hub_filter (browse / filtered) and link_url, by beacon. The
links stay plain hrefs: no redirect, no URL parameters, nothing needs JS.

Run:  python scripts/build_topics_index.py [--no-breadcrumbs]
Tests: tests/test_topics_hub.py
"""
from __future__ import annotations

import argparse
import html as html_mod
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"
OUTPUT = TOPICS_DIR / "index.html"
SITE = "https://www.christiancurator.com"
PAGE_URL = f"{SITE}/topics/"

sys.path.insert(0, str(REPO_ROOT))
from frontend.topics_hub import hub_sections  # noqa: E402
from frontend.a11y_css import A11Y_BLOCK  # noqa: E402

TITLE = "Topics | Christian Curator"
DESCRIPTION = ("Every Christian Curator topic guide in one place: Scripture, doctrine, "
               "church practice, Christian living, culture and ethics, faith and doubt.")
INTRO = ("Each guide gathers the best evangelical writing on one question, sets out where "
         "believers agree and where they part ways, and points to the strongest reading on "
         "every side. Browse by category, or type a word to narrow the list.")


def esc(s: str) -> str:
    return html_mod.escape(s, quote=True)


def canonical_nav() -> str:
    """The canonical <nav class="cc-nav"> block from archive_template.html,
    with no item marked active."""
    src = (REPO_ROOT / "frontend" / "archive_template.html").read_text(encoding="utf-8")
    m = re.search(r'[ \t]*<nav\s+class="cc-nav".*?</nav>', src, re.DOTALL)
    nav = m.group(0) if m else ""
    nav = re.sub(r'\s+class="active"', "", nav)
    # This page is the Topics section: mark the Topics link as current.
    nav = nav.replace(' style="color:#1a1a1a;"', "")
    nav = nav.replace('<a class="cc-nav-topics" href="/topics/">',
                      '<a class="cc-nav-topics" href="/topics/" aria-current="page">', 1)
    return nav


def nav_css() -> str:
    """Nav and dropdown CSS from archive_template.html (through the Topics block)."""
    src = (REPO_ROOT / "frontend" / "archive_template.html").read_text(encoding="utf-8")
    m = re.search(r"[ \t]*\.cc-nav \{.*?/\* CC-NAV-TOPICS-SUBMENU:END \*/", src, re.DOTALL)
    return m.group(0) if m else ""


def build_jsonld(sections: list[dict]) -> str:
    items = []
    pos = 0
    for sec in sections:
        for t in sec["topics"]:
            pos += 1
            items.append({
                "@type": "ListItem",
                "position": pos,
                "name": t["name"],
                "url": f"{SITE}/topics/{t['slug']}/",
            })
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": f"{PAGE_URL}#page",
                "url": PAGE_URL,
                "name": "Topics",
                "description": DESCRIPTION,
                "isPartOf": {"@type": "WebSite", "name": "Christian Curator", "url": f"{SITE}/"},
                "breadcrumb": {"@id": f"{PAGE_URL}#breadcrumb"},
                "mainEntity": {
                    "@type": "ItemList",
                    "name": "Christian Curator topic guides",
                    "numberOfItems": len(items),
                    "itemListElement": items,
                },
            },
            {
                "@type": "BreadcrumbList",
                "@id": f"{PAGE_URL}#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                    {"@type": "ListItem", "position": 2, "name": "Topics", "item": PAGE_URL},
                ],
            },
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def build_sections_html(sections: list[dict]) -> str:
    out = []
    for sec in sections:
        out.append(f'    <section class="cc-hub-cat" id="{sec["id"]}" aria-labelledby="{sec["id"]}-h">')
        out.append(f'      <h2 class="cc-hub-cat-name" id="{sec["id"]}-h">{esc(sec["name"])}</h2>')
        out.append('      <ul class="cc-hub-list">')
        for t in sec["topics"]:
            tag = ' <span class="cc-hub-tag">Four views</span>' if t["four_views"] else ""
            out.append(
                f'        <li class="cc-hub-topic" data-terms="{esc(t["terms"])}">'
                f'<a href="/topics/{t["slug"]}/" data-pos="topics-hub" data-topic="{t["slug"]}" '
                f'data-category="{sec["id"]}">{esc(t["name"])}</a>{tag}'
                f'<span class="cc-hub-line">{esc(t["line"])}</span></li>'
            )
        out.append("      </ul>")
        out.append("    </section>")
    return "\n".join(out)


def build_jump_html(sections: list[dict]) -> str:
    links = "".join(
        f'<a href="#{sec["id"]}">{esc(sec["name"])}</a>' for sec in sections
    )
    return f'    <nav class="cc-hub-jump" aria-label="Topic categories">{links}</nav>'


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <meta name="description" content="{description}" />
  <link rel="canonical" href="{page_url}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="Christian Curator" />
  <meta property="og:title" content="{title}" />
  <meta property="og:description" content="{description}" />
  <meta property="og:url" content="{page_url}" />
  <meta property="og:image" content="{site}/og-image.png" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="{title}" />
  <meta name="twitter:description" content="{description}" />
  <meta name="twitter:image" content="{site}/og-image.png" />
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-3NJ5DSPFXL"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","G-3NJ5DSPFXL");</script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Source+Sans+3:wght@300;400;600;700&display=swap" rel="stylesheet" />
  <script type="application/ld+json">
{jsonld}
  </script>
  <style>
    *,*::before,*::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: "Source Sans 3", sans-serif; background: #faf9f7; color: #1a1a1a; font-size: 16px; line-height: 1.5; }}
    .cc-root {{ max-width: 920px; margin: 0 auto; padding: 0 20px 3rem; }}
    .cc-header {{ padding: 0.75rem 0 0; margin-bottom: 1.5rem; }}
    .cc-top-bar {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.75rem; font-size: 12px; }}
    .cc-back-link {{ color: #6b6b6b; text-decoration: none; }}
    .cc-back-link:hover {{ color: #2C4A2E; }}
    .cc-subscribe-btn {{ background: #2C4A2E; color: #fff; padding: 5px 14px; font-size: 12px; border-radius: 3px; text-decoration: none; }}
    .cc-subscribe-btn:hover {{ background: #3a5f3c; }}
    .cc-masthead {{ text-align: center; padding: 0.5rem 0 1rem; border-bottom: 2.5px solid #1a1a1a; }}
    .cc-masthead h1, .cc-masthead p.cc-site {{ margin: 0; }}
    .cc-site-name {{ font-family: "Lora", Georgia, serif; font-size: 46px; font-weight: 600; letter-spacing: -0.02em; line-height: 1; color: #1a1a1a; text-decoration: none; }}
    .cc-site-name:hover {{ color: #2C4A2E; }}
    .cc-tagline {{ font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase; color: #6b6b6b; margin: 8px 0 0; font-weight: 300; }}
    @media (max-width: 600px) {{ .cc-site-name {{ font-size: 32px; }} }}
{nav_css}
    .cc-breadcrumb {{ font-size: 12px; color: #6b6b6b; margin: 0 0 1rem; letter-spacing: 0.02em; }}
    .cc-breadcrumb a {{ color: #2C4A2E; text-decoration: none; }}
    .cc-breadcrumb a:hover {{ text-decoration: underline; }}
    .cc-breadcrumb-sep {{ margin: 0 6px; color: #6b6b6b; }}
    .cc-hub-head {{ border-bottom: 2px solid #1a1a1a; padding-bottom: 1rem; margin-bottom: 1.25rem; }}
    .cc-hub-title {{ font-family: "Lora", Georgia, serif; font-size: 34px; font-weight: 600; line-height: 1.15; margin-bottom: 0.5rem; }}
    .cc-hub-intro {{ font-size: 16px; color: #444; line-height: 1.6; max-width: 680px; }}
    .cc-hub-filter {{ margin: 0 0 1rem; }}
    .cc-hub-filter label {{ display: block; font-size: 11px; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; color: #2C4A2E; margin-bottom: 6px; }}
    .cc-hub-filter input {{ width: 100%; max-width: 460px; font: inherit; font-size: 16px; padding: 9px 12px; border: 1px solid #c9c4bc; border-radius: 4px; background: #fff; color: #1a1a1a; }}
    .cc-hub-filter input:focus {{ outline: 2px solid #2C4A2E; outline-offset: 1px; border-color: #2C4A2E; }}
    .cc-hub-status {{ font-size: 13px; color: #6b6b6b; margin-top: 6px; min-height: 1.2em; }}
    .cc-hub-jump {{ display: flex; flex-wrap: wrap; gap: 6px 18px; padding: 0.75rem 0; border-top: 1px solid #e0ddd8; border-bottom: 1px solid #e0ddd8; margin-bottom: 1.75rem; }}
    .cc-hub-jump a {{ font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #2C4A2E; text-decoration: none; }}
    .cc-hub-jump a:hover {{ text-decoration: underline; }}
    .cc-hub-cat {{ margin-bottom: 2.25rem; scroll-margin-top: 1rem; }}
    .cc-hub-cat-name {{ font-family: "Lora", Georgia, serif; font-size: 21px; font-weight: 600; padding-bottom: 0.4rem; border-bottom: 1px solid #e0ddd8; margin-bottom: 0.9rem; }}
    .cc-hub-list {{ list-style: none; columns: 3 220px; column-gap: 2rem; }}
    .cc-hub-topic {{ break-inside: avoid; padding: 0 0 0.85rem; }}
    .cc-hub-topic a {{ font-family: "Lora", Georgia, serif; font-size: 16px; font-weight: 600; color: #1a1a1a; text-decoration: none; line-height: 1.3; }}
    .cc-hub-topic a:hover {{ color: #2C4A2E; text-decoration: underline; }}
    .cc-hub-line {{ display: block; font-size: 13.5px; color: #666; line-height: 1.45; margin-top: 2px; }}
    .cc-hub-tag {{ display: inline-block; vertical-align: 2px; margin-left: 6px; font-size: 9.5px; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; color: #8B1A1A; border: 1px solid #d9b8b8; border-radius: 3px; padding: 0 5px; line-height: 1.6; }}
    .cc-hub-empty {{ font-size: 15px; color: #555; margin: 0 0 2rem; }}
    .cc-footer {{ margin-top: 2.5rem; padding-top: 1.25rem; border-top: 1px solid #e0ddd8; text-align: center; font-size: 12px; color: #6b6b6b; }}
    .cc-footer a {{ color: #2C4A2E; text-decoration: none; font-weight: 600; }}
    .cc-footer a:hover {{ text-decoration: underline; }}
    @media (max-width: 600px) {{
      .cc-hub-title {{ font-size: 28px; }}
      .cc-hub-jump {{ gap: 8px 14px; }}
    }}
    {A11Y_BLOCK}
  </style>
</head>
<body>
<div class="cc-root">
  <header class="cc-header">
    <div class="cc-top-bar">
      <a href="/" class="cc-back-link">&larr; Christian Curator</a>
      <a href="/#cc-email-box" class="cc-subscribe-btn">Get the Daily Digest</a>
    </div>
    <div class="cc-masthead">
      <p class="cc-site"><a href="/" class="cc-site-name">Christian Curator</a></p>
      <p class="cc-tagline">The Christian conversation, in one place</p>
    </div>
{nav_block}
  </header>

  <main data-pagefind-body>
    <nav aria-label="Breadcrumb" class="cc-breadcrumb"><a href="/">Home</a><span class="cc-breadcrumb-sep">&rsaquo;</span><span aria-current="page">Topics</span></nav>
    <div class="cc-hub-head">
      <h1 class="cc-hub-title">Topics</h1>
      <p class="cc-hub-intro">{intro}</p>
    </div>
    <div class="cc-hub-filter" id="cc-hub-filter" hidden>
      <label for="cc-hub-q">Find a topic</label>
      <input id="cc-hub-q" type="search" autocomplete="off" spellcheck="false" placeholder="Try rapture, communion, or doubt" aria-describedby="cc-hub-status" />
      <p class="cc-hub-status" id="cc-hub-status" aria-live="polite"></p>
    </div>
{jump}
    <p class="cc-hub-empty" id="cc-hub-empty" hidden>No topic matches that word. Try a broader one, or browse the categories.</p>
{sections}
  </main>

  <footer class="cc-footer">
    <p><a href="/">Christian Curator</a> &middot; <a href="/about/">About</a> &middot; <a href="/voices/">Voices</a> &middot; <a href="/archive/">Archive</a> &middot; <a href="/#cc-email-box">Subscribe to the daily email</a></p>
    <p style="margin-top:6px;">&copy; {year} Christian Curator</p>
  </footer>
</div>
<script>
(function () {{
  var wrap = document.getElementById("cc-hub-filter");
  var box = document.getElementById("cc-hub-q");
  var status = document.getElementById("cc-hub-status");
  var empty = document.getElementById("cc-hub-empty");
  if (!wrap || !box) return;
  wrap.hidden = false;
  var items = [].slice.call(document.querySelectorAll(".cc-hub-topic"));
  var cats = [].slice.call(document.querySelectorAll(".cc-hub-cat"));
  var words = items.map(function (li) {{ return (li.getAttribute("data-terms") || "").split(" "); }});
  function tokens(s) {{ return s.toLowerCase().replace(/[’']/g, "").match(/[a-z0-9]+/g) || []; }}
  function matches(ws, q) {{
    return q.every(function (t) {{
      return ws.some(function (w) {{ return w.lastIndexOf(t, 0) === 0; }});
    }});
  }}
  function run() {{
    var q = tokens(box.value);
    var shown = 0;
    items.forEach(function (li, i) {{
      var ok = !q.length || matches(words[i], q);
      li.hidden = !ok;
      if (ok) shown++;
    }});
    cats.forEach(function (c) {{
      c.hidden = !c.querySelector(".cc-hub-topic:not([hidden])");
    }});
    empty.hidden = shown > 0;
    status.textContent = q.length ? (shown === 1 ? "1 topic matches" : shown + " topics match") : "";
  }}
  box.addEventListener("input", run);
  box.addEventListener("keydown", function (e) {{
    if (e.key === "Escape") {{ box.value = ""; run(); }}
  }});
  if (box.value) run();
}})();
(function () {{
  // Topic clicks, as GA4 article_click (the homepage's event). Read per topic
  // and per category in GA4 with position = topics-hub.
  function send(e) {{
    if (e.type === "auxclick" && e.button !== 1) return;
    var a = e.target.closest && e.target.closest("a[data-pos]");
    if (!a || typeof gtag !== "function") return;
    var box = document.getElementById("cc-hub-q");
    gtag("event", "article_click", {{
      article_title: a.textContent.trim().slice(0, 100),
      position: a.getAttribute("data-pos"),
      topic: a.getAttribute("data-topic") || "",
      topic_category: a.getAttribute("data-category") || "",
      hub_filter: box && box.value.trim() ? "filtered" : "browse",
      link_url: a.href,
      transport_type: "beacon"
    }});
  }}
  document.addEventListener("click", send);
  document.addEventListener("auxclick", send);
}})();
</script>
</body>
</html>
"""


def render_page(sections: list[dict]) -> str:
    return PAGE.format(
        title=esc(TITLE),
        description=esc(DESCRIPTION),
        page_url=PAGE_URL,
        site=SITE,
        jsonld=build_jsonld(sections),
        nav_css=nav_css(),
        A11Y_BLOCK=A11Y_BLOCK,
        nav_block=canonical_nav(),
        intro=esc(INTRO),
        jump=build_jump_html(sections),
        sections=build_sections_html(sections),
        year=date.today().year,
    )


def refresh_breadcrumbs() -> int:
    """Home > Topics > Category breadcrumbs on every live topic page."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import add_breadcrumbs  # noqa: E402
    from frontend.topic_redirects import live_topic_dirs
    changed = 0
    for d in live_topic_dirs(TOPICS_DIR):
        status = add_breadcrumbs.process_topic_page(d / "index.html")
        if "updated" in status:
            changed += 1
        elif "skipped" in status:
            print(f"  ! {status}", file=sys.stderr)
    return changed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-breadcrumbs", action="store_true",
                    help="write the hub page only")
    args = ap.parse_args(argv)
    sections = hub_sections(TOPICS_DIR)
    total = sum(len(s["topics"]) for s in sections)
    if not total:
        print("no topics found", file=sys.stderr)
        return 1
    OUTPUT.write_text(render_page(sections), encoding="utf-8")
    print(f"wrote {OUTPUT} with {total} topics in {len(sections)} categories")
    if not args.no_breadcrumbs:
        n = refresh_breadcrumbs()
        print(f"breadcrumbs refreshed on {n} topic page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
