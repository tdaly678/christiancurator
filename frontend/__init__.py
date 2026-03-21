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

    # Regenerate sitemap to include all daily pages
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


def regenerate_sitemap():
    """Regenerate sitemap.xml to include the homepage + all daily pages."""
    urls = ["https://christiancurator.com/"]

    # Collect all daily page slugs from docs/daily/
    if DAILY_DIR.exists():
        for day_dir in sorted(DAILY_DIR.iterdir()):
            if day_dir.is_dir() and (day_dir / "index.html").exists():
                urls.append(f"https://christiancurator.com/daily/{day_dir.name}/")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for i, url in enumerate(urls):
        priority = "1.0" if i == 0 else "0.8"
        changefreq = "daily" if i == 0 else "never"
        lines.append(f"  <url>")
        lines.append(f"    <loc>{url}</loc>")
        lines.append(f"    <changefreq>{changefreq}</changefreq>")
        lines.append(f"    <priority>{priority}</priority>")
        lines.append(f"  </url>")
    lines.append("</urlset>")

    with open(SITEMAP_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Regenerated sitemap with {len(urls)} URL(s).")
