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
from frontend import render_html
from output import load_yesterday

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

    # Reconstruct pairings in the format render_html expects
    raw_pairings = data.get("pairings", []) if isinstance(data, dict) else []
    pairings = [
        {
            "topic": p["topic"],
            "point": {"rewritten_title": p["point_title"], "title": p["point_title"], "url": p["point_url"]},
            "counterpoint": {"rewritten_title": p["counterpoint_title"], "title": p["counterpoint_title"], "url": p["counterpoint_url"]},
        }
        for p in raw_pairings
    ]

    print(f"  Loaded {len(articles)} articles and {len(pairings)} pairings from output/articles.json")

    print("  Generating daily summary...")
    daily_summary = generate_daily_summary(articles)

    if not daily_summary:
        print("  ERROR: Daily summary generation failed.")
        return

    print(f"  Summary generated for {daily_summary['date']}.")
    save_theme_history(daily_summary)

    # Re-render index.html so the Today's Pulse sidebar link appears
    yesterday_articles = load_yesterday()
    render_html(articles, pairings, yesterday_articles, daily_summary=daily_summary)

    print("\n=== Done. index.html and docs/daily/ updated. ===")
    print("Remember to: git add docs/ && git commit -m '...' && git push")


if __name__ == "__main__":
    main()
