"""
frontend package — renders the HTML digest from the Jinja2 template.
"""

from pathlib import Path
from datetime import date
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent
OUTPUT_HTML = Path(__file__).parent.parent / "docs" / "index.html"


def render_html(articles: list[dict], pairings: list[dict]):
    """Render index.html from template.html using Jinja2."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
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
        date=date.today().strftime("%B %-d, %Y"),
    )

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Rendered HTML to {OUTPUT_HTML}")
