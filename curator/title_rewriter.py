"""
title_rewriter.py — uses Claude to rewrite article titles for a Christian audience.

Goal: make titles more engaging and clear without being clickbait.
The original title is preserved; the rewritten version is stored separately.
"""

import os
import time
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

REWRITE_PROMPT = """\
You are a headline editor for a Christian news aggregator, writing in the style of \
RealClearPolitics or RealClearReligion — punchy, direct, and compelling enough to make \
a reader stop scrolling.

Rewrite the article title using these principles:
- Lead with the stakes, tension, or conflict — what is at risk or being debated?
- Use strong, specific verbs and nouns (not "discusses," "explores," or "looks at")
- Reveal the angle: who's arguing what, what's changing, what's surprising
- A little editorial edge is fine — don't sand down every opinion into mush
- Under 12 words
- Do NOT invent facts or topics not in the original article
- The rewrite must be accurate to the article summary below
- Return ONLY the rewritten title, nothing else

Examples of the tone to aim for:
  Flat: "Reflections on the Role of the Church in Modern Society"
  Better: "The Church Is Losing Culture — and Deserves to Know Why"

  Flat: "An Overview of Current Debates on Penal Substitution"
  Better: "Evangelicalism's Atonement War Is Back. Here's What's at Stake."

  Flat: "Christian Perspectives on Artificial Intelligence"
  Better: "AI Can't Preach the Gospel. But It's Trying."

Original title: {title}
Article summary: {summary}
"""

MAX_RETRIES = 4
RETRY_DELAYS = [5, 15, 30, 60]


def _looks_like_headline(text: str) -> bool:
    """Return False if the model's response looks like a meta-reply rather than a rewritten title."""
    if not text:
        return False
    # Too long to be a headline (>120 chars), or contains phrases typical of a confused/refusal response
    if len(text) > 120:
        return False
    lower = text.lower()
    refusal_phrases = [
        "i need to see", "could you provide", "article summary", "please provide",
        "i cannot", "i'm unable", "i don't have", "you've included",
    ]
    return not any(p in lower for p in refusal_phrases)


def rewrite_title(article: dict) -> dict:
    """Rewrite a single article title using Claude, with retry on 529 overload."""
    import re
    summary = article.get("summary") or ""
    # Strip HTML tags from summary for cleaner context
    summary_text = re.sub(r"<[^>]+>", "", summary).strip()[:300]

    # Skip rewrite entirely if there's nothing to ground it on
    if not summary_text:
        article["rewritten_title"] = article["title"]
        return article

    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=60,
                messages=[{"role": "user", "content": REWRITE_PROMPT.format(title=article["title"], summary=summary_text)}],
            )
            candidate = message.content[0].text.strip().strip('"')
            # Guard against meta-replies leaking through as headlines
            article["rewritten_title"] = candidate if _looks_like_headline(candidate) else article["title"]
            return article
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt <= MAX_RETRIES:
                print(f"  Title rewrite overloaded (attempt {attempt}/{MAX_RETRIES}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"  Title rewrite error for '{article['title']}': {e}")
                article["rewritten_title"] = article["title"]
                return article
        except Exception as e:
            print(f"  Title rewrite error for '{article['title']}': {e}")
            article["rewritten_title"] = article["title"]
            return article
    article["rewritten_title"] = article["title"]
    return article


def rewrite_titles(articles: list[dict]) -> list[dict]:
    """Rewrite titles for all articles."""
    return [rewrite_title(a) for a in articles]
