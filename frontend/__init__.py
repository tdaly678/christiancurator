"""
frontend package — renders the HTML digest from the Jinja2 template.
"""

from pathlib import Path
from datetime import date
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent
DOCS_DIR = Path(__file__).parent.parent / "docs"
OUTPUT_HTML = DOCS_DIR / "index.html"
DAILY_DIR = DOCS_DIR / "daily"
ARCHIVE_DIR = DOCS_DIR / "archive"
SITEMAP_PATH = DOCS_DIR / "sitemap.xml"


def render_html(articles: list[dict], pairings: list[dict], yesterday_articles: list[dict] = None,
                daily_summary: dict = None):
    """Render index.html from template.html using Jinja2."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    env.tests['contains'] = lambda value, item: item in (value or [])
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

    html = template.render(
        articles=articles,
        pairings=template_pairings,
        yesterday_articles=yesterday_articles or [],
        date=date.today().strftime("%B %-d, %Y"),
        daily_summary=daily_summary,
    )

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Rendered HTML to {OUTPUT_HTML}")

    # Render the standalone daily summary page if we have one
    if daily_summary:
        render_daily_page(daily_summary, env)

    # Render the daily archive snapshot and update the archive index
    render_archive_page(articles, template_pairings, env)
    render_archive_index(env)

    # Regenerate sitemap to include all daily and archive pages
    regenerate_sitemap()


def render_daily_page(daily_summary: dict, env: Environment):
    """Render a standalone daily pulse page to docs/daily/YYYY-MM-DD/index.html."""
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    slug = daily_summary["slug"]
    page_dir = DAILY_DIR / slug
    page_dir.mkdir(parents=True, exist_ok=True)

    template = env.get_template("daily_template.html")
    html = template.render(**daily_summary)

    output_path = page_dir / "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Rendered daily page to {output_path}")


def render_archive_page(articles: list[dict], pairings: list[dict], env: Environment):
    """Render a daily archive snapshot to docs/archive/YYYY-MM-DD/index.html."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    today = date.today()
    date_iso = today.isoformat()                          # e.g. "2026-03-22"
    date_display = today.strftime("%B %-d, %Y")           # e.g. "March 22, 2026"

    # Determine prev/next dates based on existing archive pages
    existing = sorted(
        [p.name for p in ARCHIVE_DIR.iterdir() if p.is_dir() and (p / "index.html").exists()]
    )

    prev_date_iso = existing[-1] if existing else None
    prev_date_display = None
    if prev_date_iso:
        try:
            prev_date_display = date.fromisoformat(prev_date_iso).strftime("%B %-d, %Y")
        except ValueError:
            prev_date_iso = None

    template = env.get_template("archive_template.html")
    html = template.render(
        articles=articles,
        pairings=pairings,
        date_iso=date_iso,
        date_display=date_display,
        prev_date_iso=prev_date_iso,
        prev_date_display=prev_date_display,
        next_date_iso=None,
        next_date_display=None,
    )

    page_dir = ARCHIVE_DIR / date_iso
    page_dir.mkdir(parents=True, exist_ok=True)
    output_path = page_dir / "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Rendered archive page to {output_path}")

    # Back-patch: update the previous day's page so its "next" link points to today
    if prev_date_iso:
        _patch_archive_next_link(prev_date_iso, date_iso, date_display, env, articles, pairings)


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
    new_nav_inner += f'      <a href="/archive/{next_iso}/">{next_display} →</a>\n    '

    new_content = nav_pattern.sub(
        lambda m: m.group(1) + new_nav_inner + m.group(3),
        content,
        count=1
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  Updated archive nav on {output_path}")


def render_archive_index(env: Environment):
    """Regenerate docs/archive/index.html — a chronological listing of all archive days."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # Collect all dated subdirectories that contain index.html
    days = []
    for day_dir in ARCHIVE_DIR.iterdir():
        if day_dir.is_dir() and day_dir.name != "index.html" and (day_dir / "index.html").exists():
            try:
                d = date.fromisoformat(day_dir.name)
                days.append((day_dir.name, d.strftime("%B %-d, %Y"), d.strftime("%A")))
            except ValueError:
                pass
    days.sort(key=lambda x: x[0], reverse=True)  # Most recent first

    # Group by month for display
    from collections import OrderedDict
    months: dict = OrderedDict()
    for iso, display, weekday in days:
        month_key = iso[:7]  # "2026-03"
        try:
            month_label = date.fromisoformat(iso).strftime("%B %Y")
        except ValueError:
            month_label = month_key
        if month_key not in months:
            months[month_key] = {"label": month_label, "days": []}
        months[month_key]["days"].append({"iso": iso, "display": display, "weekday": weekday})

    # Build HTML
    lines = [
        '<!DOCTYPE html>',
        '<html lang="en">',
        '<head>',
        '  <meta charset="UTF-8" />',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />',
        '  <title>Christian Curator — Archive</title>',
        '  <meta name="description" content="Browse all past issues of Christian Curator — a daily digest of evangelical Christian news, theology, and culture." />',
        '  <link rel="canonical" href="https://christiancurator.com/archive/" />',
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
        '    .cc-archive-intro{font-size:14px;color:#666;margin-bottom:2rem;}',
        '    .cc-month{margin-bottom:2rem;}',
        '    .cc-month-label{font-size:10px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;padding-bottom:0.5rem;border-bottom:1px solid #e0ddd8;margin-bottom:0.75rem;}',
        '    .cc-day-link{display:flex;align-items:baseline;gap:10px;padding:0.6rem 0;border-bottom:1px solid #f0ede8;text-decoration:none;color:#1a1a1a;}',
        '    .cc-day-link:last-child{border-bottom:none;}',
        '    .cc-day-link:hover .cc-day-display{text-decoration:underline;text-decoration-color:#2C4A2E;}',
        '    .cc-day-weekday{font-size:11px;color:#aaa;min-width:60px;}',
        '    .cc-day-display{font-family:"Lora",Georgia,serif;font-size:15px;font-weight:500;}',
        '    .cc-footer{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #e0ddd8;text-align:center;font-size:12px;color:#aaa;}',
        '    .cc-footer a{color:#2C4A2E;text-decoration:none;}',
        '    .cc-footer a:hover{text-decoration:underline;}',
        '    @media(max-width:600px){.cc-site-name{font-size:32px;}}',
        '  </style>',
        '</head>',
        '<body>',
        '  <div class="cc-root">',
        '    <header class="cc-header">',
        '      <div class="cc-top-bar">',
        '        <a href="/" class="cc-back-link">← Today\'s Digest</a>',
        '        <a href="/#subscribe" class="cc-subscribe-btn">Get the Daily Digest</a>',
        '      </div>',
        '      <div class="cc-masthead">',
        '        <a href="/" class="cc-site-name">Christian Curator</a>',
        '        <p class="cc-tagline">Evangelical News &amp; Theology — Curated Daily</p>',
        '      </div>',
        '    </header>',
        '    <h1>Archive</h1>',
        f'    <p class="cc-archive-intro">Browse {len(days)} past issue{"s" if len(days) != 1 else ""} of Christian Curator.</p>',
    ]

    for month_data in months.values():
        lines.append(f'    <div class="cc-month">')
        lines.append(f'      <div class="cc-month-label">{month_data["label"]}</div>')
        for day in month_data["days"]:
            lines.append(
                f'      <a href="/archive/{day["iso"]}/" class="cc-day-link">'
                f'<span class="cc-day-weekday">{day["weekday"]}</span>'
                f'<span class="cc-day-display">{day["display"]}</span>'
                f'</a>'
            )
        lines.append('    </div>')

    lines += [
        '    <footer class="cc-footer">',
        '      <p><a href="/">Christian Curator</a> — A daily digest of the best evangelical Christian writing.</p>',
        '      <p style="margin-top:6px;"><a href="/#subscribe">Subscribe to the daily email</a></p>',
        '    </footer>',
        '  </div>',
        '</body>',
        '</html>',
    ]

    output_path = ARCHIVE_DIR / "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Rendered archive index to {output_path} ({len(days)} days listed)")


def regenerate_sitemap():
    """Regenerate sitemap.xml to include the homepage + all daily and archive pages."""
    today_iso = date.today().isoformat()

    # Each entry: (url, changefreq, priority, lastmod)
    entries = [("https://christiancurator.com/", "daily", "1.0", today_iso)]

    # Daily pulse pages
    if DAILY_DIR.exists():
        for day_dir in sorted(DAILY_DIR.iterdir()):
            if day_dir.is_dir() and (day_dir / "index.html").exists():
                entries.append((
                    f"https://christiancurator.com/daily/{day_dir.name}/",
                    "never", "0.8", day_dir.name,
                ))

    # Archive index (changes every day)
    entries.append(("https://christiancurator.com/archive/", "daily", "0.7", today_iso))

    # Individual archive pages
    if ARCHIVE_DIR.exists():
        for day_dir in sorted(ARCHIVE_DIR.iterdir()):
            if day_dir.is_dir() and (day_dir / "index.html").exists():
                entries.append((
                    f"https://christiancurator.com/archive/{day_dir.name}/",
                    "never", "0.6", day_dir.name,
                ))

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

    with open(SITEMAP_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Regenerated sitemap with {len(entries)} URL(s).")
