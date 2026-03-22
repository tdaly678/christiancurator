"""
x_poster.py — posts the daily digest highlights to @ChristCurator on X.

Post format (Option C, 3 titles):

    Today's best evangelical writing, curated:

    → "Title one here" (Author)
    → "Title two here" (Source)
    → "Title three here" (Author)

    christiancurator.com

Requires four environment variables / GitHub Secrets:
    X_API_KEY
    X_API_SECRET
    X_ACCESS_TOKEN
    X_ACCESS_TOKEN_SECRET
"""

import os
import tweepy
from dotenv import load_dotenv

load_dotenv()

MAX_TWEET_LENGTH = 280
SITE_URL = "christiancurator.com"
HEADER = "Today's best evangelical writing, curated:\n\n"
FOOTER = f"\n{SITE_URL}"


def _byline(article: dict) -> str:
    """Return '(Author)' if author differs from source, otherwise '(Source)'."""
    author = (article.get("author") or "").strip()
    source = (article.get("source_name") or "").strip()
    label = author if author and author.lower() != source.lower() else source
    return f"({label})" if label else ""


def _truncate(title: str, max_len: int) -> str:
    """Truncate a title to max_len characters, appending … if needed."""
    if len(title) <= max_len:
        return title
    return title[:max_len - 1].rstrip() + "…"


def build_post(articles: list[dict]) -> str:
    """Build the daily X post from the top 3 non-world-news articles."""
    candidates = [a for a in articles if a.get("source_type") != "world_news"][:3]
    if not candidates:
        return ""

    # Calculate per-title budget so the full post fits within 280 chars
    # Fixed overhead: header + footer + 3 lines of "→ "" (byline)\n"
    # Each arrow line: '→ "' + title + '" ' + byline + '\n'
    # Minimum per-line overhead (excluding title): len('→ "" ()\n') = 8 chars + byline
    bylines = [_byline(a) for a in candidates]
    overhead = len(HEADER) + len(FOOTER)
    for b in bylines:
        overhead += len(f'→ "" {b}\n')

    remaining = MAX_TWEET_LENGTH - overhead
    title_budget = remaining // len(candidates) if candidates else 40
    title_budget = max(20, title_budget)  # always allow at least 20 chars

    lines = []
    for a, byline in zip(candidates, bylines):
        raw_title = (a.get("rewritten_title") or a.get("title", "")).strip()
        title = _truncate(raw_title, title_budget)
        lines.append(f'→ "{title}" {byline}')

    post = HEADER + "\n".join(lines) + FOOTER
    return post


def post_to_x(articles: list[dict]) -> bool:
    """Build and post the daily digest to X. Returns True on success."""
    api_key = os.environ.get("X_API_KEY", "")
    api_secret = os.environ.get("X_API_SECRET", "")
    access_token = os.environ.get("X_ACCESS_TOKEN", "")
    access_token_secret = os.environ.get("X_ACCESS_TOKEN_SECRET", "")

    if not all([api_key, api_secret, access_token, access_token_secret]):
        print("  Skipping X post: one or more X API credentials not set.")
        return False

    post_text = build_post(articles)
    if not post_text:
        print("  Skipping X post: no articles available.")
        return False

    print(f"  X post preview ({len(post_text)} chars):\n{post_text}\n")

    try:
        client = tweepy.Client(
            consumer_key=api_key,
            consumer_secret=api_secret,
            access_token=access_token,
            access_token_secret=access_token_secret,
        )
        response = client.create_tweet(text=post_text)
        tweet_id = response.data["id"]
        print(f"  Posted to X: https://x.com/ChristCurator/status/{tweet_id}")
        return True
    except tweepy.TweepyException as e:
        print(f"  X post failed: {e}")
        return False
