"""
main.py — orchestrates the full ChristianCurator pipeline.

Usage:
    python main.py              # full run including email
    python main.py --no-email   # full run, skip email (use send_email.py to send later)
    python main.py --force-email  # send email even if pipeline already ran today

Steps:
    1. Fetch articles from RSS sources (fetcher layer)
    2. Score, tag, and rewrite titles (curator layer)
    3. Generate point/counterpoint pairs (curator layer)
    4. Write output JSON and regenerate HTML (output layer)
    5. Generate daily summary
    6. Update Research & Data section
    7. Send email (skipped with --no-email, or if already sent today)
"""

import json
import os
import sys
from datetime import date
from fetcher.rss_fetcher import fetch_all
from curator.scorer import score_articles
from curator.title_rewriter import rewrite_titles
from curator.point_counterpoint import build_point_counterpoint
from curator.daily_summary import generate_daily_summary, save_theme_history
from curator.email_sender import send_email
from curator.voice_generator import generate_new_voice_pages
from output import OUTPUT_JSON_PATH, write_output, save_yesterday, load_yesterday, load_shown_urls, save_article_history
from frontend import render_html, update_research_articles


def already_ran_today() -> bool:
    """Check if the pipeline already ran today by looking for today's archive page."""
    today = date.today().isoformat()
    archive_path = os.path.join(
        os.path.dirname(__file__), "docs", "archive", today, "index.html"
    )
    return os.path.exists(archive_path)


def main():
    send_email_flag = "--no-email" not in sys.argv
    force_email = "--force-email" in sys.argv
    print("=== ChristianCurator Pipeline Starting ===\n")

    # --- Duplicate-run guard: skip email if pipeline already ran today ---
    if send_email_flag and not force_email and already_ran_today():
        print(f"  ⚠️  Pipeline already ran today ({date.today().isoformat()}).")
        print("      Email will be skipped to avoid duplicates.")
        print("      To send anyway, re-run with: python main.py --force-email\n")
        send_email_flag = False

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

    # --- Research & Data section (persistent) ---
    print("\n[6/7] Updating Research & Data section...")
    research_articles = update_research_articles(articles)

    # --- Voices: auto-generate pages for new authors (must run BEFORE render_html
    #     so voices_data.json is up-to-date when the homepage builds author links) ---
    print("\n[7/8] Checking for new Voices...")
    generate_new_voice_pages(articles)

    render_html(articles, pairings, yesterday_articles, daily_summary=daily_summary,
                research_articles=research_articles)

    # --- Voice ↔ Topic cross-links: refresh "Featured in Deep-Dive Topics" block
    #     on each voice page from the latest featured_topic_log + current digest.
    #     Must run AFTER render_html so today's co-occurrences are visible. Wrapped
    #     in try/except so a failure here never breaks the daily run. ---
    try:
        import subprocess
        subprocess.run(
            [sys.executable, "scripts/update_voice_backlinks.py"],
            check=False, timeout=60,
        )
    except Exception as e:
        print(f"  (voice backlinks refresh skipped: {e})")

    # --- Send Email ---
    if send_email_flag:
        print("\n[8/8] Sending daily email via Brevo...")
        send_email(articles, yesterday_articles, daily_summary=daily_summary,
                   research_articles=research_articles)
    else:
        print("\n[8/8] Email skipped (--no-email). Run send_email.py when ready to send.")

    print("=== Pipeline Complete ===")
    print(f"Output written to {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    main()
