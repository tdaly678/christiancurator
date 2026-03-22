"""
main.py — orchestrates the full ChristianCurator pipeline.

Usage:
    python main.py

Steps:
    1. Fetch articles from RSS sources (fetcher layer)
    2. Score, tag, and rewrite titles (curator layer)
    3. Generate point/counterpoint pairs (curator layer)
    4. Write output JSON and regenerate HTML (output layer)
"""

import json
from fetcher.rss_fetcher import fetch_all
from curator.scorer import score_articles
from curator.title_rewriter import rewrite_titles
from curator.point_counterpoint import build_point_counterpoint
from curator.daily_summary import generate_daily_summary, save_theme_history
from curator.email_sender import send_email
from curator.x_poster import post_to_x
from output import OUTPUT_JSON_PATH, write_output, save_yesterday, load_yesterday, load_shown_urls, save_article_history
from frontend import render_html


def main():
    print("=== ChristianCurator Pipeline Starting ===\n")

    # --- Load yesterday's top 3 for the digest ---
    yesterday_articles = load_yesterday()
    print(f"      Loaded {len(yesterday_articles)} articles from yesterday.")

    # --- Load previously shown article URLs ---
    shown_urls = load_shown_urls()
    print(f"      Tracking {len(shown_urls)} previously shown articles.\n")

    # --- Layer 1: Fetch ---
    print("[1/4] Fetching articles from RSS sources...")
    articles = fetch_all()
    print(f"      Fetched {len(articles)} articles.\n")

    # --- Layer 2: Score & Tag ---
    print("[2/4] Scoring and tagging articles...")
    articles = score_articles(articles, shown_urls=shown_urls)
    boosted = sum(1 for a in articles if a.get("recency_boost", 0) > 0)
    print(f"      Scoring complete. ({boosted} articles received a recency boost)\n")

    # --- Layer 3: Rewrite Titles ---
    print("[3/4] Rewriting titles...")
    articles = rewrite_titles(articles)
    print("      Title rewriting complete.\n")

    # --- Layer 4: Point / Counterpoint ---
    print("[4/4] Building point/counterpoint pairs...")
    pairings = build_point_counterpoint(articles)
    print(f"      Built {len(pairings)} pairings.\n")

    # --- Layer 5: Daily Summary ---
    print("[5/5] Generating daily summary...")
    daily_summary = generate_daily_summary(articles)
    if daily_summary:
        print(f"      Daily summary generated for {daily_summary['date']}.")
        save_theme_history(daily_summary)
    else:
        print("      Daily summary skipped.\n")

    # --- Output ---
    write_output(articles, pairings)
    save_yesterday(articles)
    # Only mark the top 20 articles as "shown" — saves Substack/independent authors
    # from having ALL their recent content penalised the next day just because it
    # was scored but never actually featured on the site.
    save_article_history(articles[:20])
    render_html(articles, pairings, yesterday_articles, daily_summary=daily_summary)

    # --- Send Email ---
    print("\n[6/7] Sending daily email via Brevo...")
    send_email(articles, yesterday_articles, daily_summary=daily_summary)

    # --- Post to X ---
    print("\n[7/7] Posting to X (@ChristCurator)...")
    post_to_x(articles)

    print("=== Pipeline Complete ===")
    print(f"Output written to {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    main()
