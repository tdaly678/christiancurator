"""
regenerate_daily.py — Re-runs only the daily summary step using already-scored articles.

Use this to iterate on the daily pulse writing WITHOUT re-running the full pipeline.
Only use this on the SAME day the pipeline ran — it uses cached articles from output/articles.json.

Usage:
    python3 regenerate_daily.py
"""

import json
import datetime
from pathlib import Path
from curator.daily_summary import generate_daily_summary, save_theme_history
from frontend import render_daily_page, regenerate_sitemap
from jinja2 import Environment, FileSystemLoader

ARTICLES_PATH = Path(__file__).parent / "output" / "articles.json"
TEMPLATE_DIR = Path(__file__).parent / "frontend"


def main():
    print("=== Regenerating Daily Pulse Only ===\n")

    if not ARTICLES_PATH.exists():
        print(f"ERROR: {ARTICLES_PATH} not found. Run main.py first.")
        return

    # Check if articles.json is from today — warn if stale
    articles_date = datetime.date.fromtimestamp(ARTICLES_PATH.stat().st_mtime)
    today = datetime.date.today()
    if articles_date < today:
        print(f"  WARNING: output/articles.json was generated on {articles_date}, not today ({today}).")
        print("  The daily pulse will use stale articles. Run main.py first for fresh content.")
        print("  Aborting. Use --force to override.\n")
        import sys
        if "--force" not in sys.argv:
            return
        print("  --force flag detected. Proceeding with stale articles.\n")

    with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    articles = data.get("articles", data) if isinstance(data, dict) else data

    print(f"  Loaded {len(articles)} articles from output/articles.json")

    print("  Generating daily summary...")
    daily_summary = generate_daily_summary(articles)

    if not daily_summary:
        print("  ERROR: Daily summary generation failed.")
        return

    print(f"  Summary generated for {daily_summary['date']}.")
    save_theme_history(daily_summary)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    render_daily_page(daily_summary, env)
    regenerate_sitemap()

    print("\n=== Done. Check docs/daily/ for the updated page. ===")
    print("Remember to: git add docs/ && git commit -m '...' && git push")


if __name__ == "__main__":
    main()
