"""
title_rewriter.py: uses Claude to rewrite article titles in RealClear house voice.

Goal: understated news curation headlines in the RealClearPolitics /
RealClearReligion style that state a claim, never clickbait or promo copy.
The original title is preserved; the rewritten version is stored separately.

ON for the daily product: .github/workflows/daily_run.yml sets
CC_REWRITE_TITLES=1 on the "Run pipeline" step, so main.py rewrites titles
after scoring. Without the flag (local runs, tests) articles keep the cleaned
publisher headline. Every display path reads `rewritten_title or title`.

Every rewrite is gated by headline_voice.rewrite_rejection() (hard rejects,
dated column check, listicle and claimless-label rules, voice demotions). A
rewrite that fails falls back to the cleaned original, display_title().
"""

import os
import time
import anthropic
from dotenv import load_dotenv

from curator.ai_health import record_failure
from curator.headline_voice import display_title, rewrite_rejection, strip_dashes

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

REWRITE_TITLES_ENABLED = os.environ.get("CC_REWRITE_TITLES", "").strip() == "1"

REWRITE_PROMPT = """\
You are a headline editor for Christian Curator, a news curation front page for \
evangelical readers written in RealClear Media house voice (RealClearPolitics, \
RealClearReligion). RealClear headlines are understated and plain. They state what \
happened or what the writer argues, in the words of a wire editor, and let the \
claim carry the weight.

Rewrite the article title using these rules:
- Make a claim: a subject and a verb that say what happened, what changed, or what \
the writer argues. A question is fine only when it names a real dispute.
- Understated, not punchy: no hype, no teasers, no cliffhangers, no "here's why"
- Use specific nouns and verbs from the article (not "discusses," "explores," or "looks at")
- Name the person, church, court or body when the summary does
- Between 5 and 12 words
- Title Case, no ALL CAPS words except acronyms such as SBC or PCA
- No exclamation points, emoji, em dashes or en dashes
- No issue, episode or volume numbers, and no dates
- No promo or launch copy (out now, now available, pre-order, giveaway, subscribe)
- No newsletter or first person voice (my week, what I'm reading, a note to readers)
- No listicles ("5 Ways", "7 Reasons", "10 Things")
- No review labels ("Review:", "A Review of")
- Never return a dated show or column title such as \
"The World and Everything in It: November 3, 2026" or "Works & Wonders (November 1)". \
For a dated show or briefing, drop the show name and the date and headline the \
single most important news item in the summary.
- Never return a bare label such as "The Tyranny of Preferences"; say what it claims
- Do NOT invent facts, names, numbers or topics not in the original title or summary
- If the original title already makes a clear claim in this voice, return it unchanged
- Return ONLY the headline, nothing else

Examples of the voice to aim for:
  Original: "Reflections on the Role of the Church in Modern Society"
  RealClear: "Churches Are Losing Their Civic Role, Pastor Argues"

  Original: "The World and Everything in It: November 3, 2026"
  (summary leads with a Supreme Court hearing on a religious charter school)
  RealClear: "Supreme Court Weighs Faith-Based Charter School Case"

  Original: "5 Things Every Pastor Should Know About AI"
  RealClear: "Pastors Should Treat AI Sermon Tools With Caution"

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


def _fallback_title(article: dict) -> str:
    """The cleaned publisher title shown when a rewrite is skipped or rejected."""
    return display_title(article["title"], article.get("source_name")) or article["title"]


def accept_rewrite(article: dict, candidate: str) -> str:
    """Return the headline to show: the rewrite if it passes the voice gate, else the fallback.

    The candidate is cleaned first (quotes, dashes, emoji, service tails), then
    checked with headline_voice.rewrite_rejection(). A rejection is logged and
    recorded on the article as rewrite_rejected.
    """
    cleaned = strip_dashes(display_title((candidate or "").strip().strip('"'),
                                         article.get("source_name")))
    if not _looks_like_headline(cleaned):
        article["rewrite_rejected"] = "META_REPLY"
        return _fallback_title(article)
    reason = rewrite_rejection(cleaned, article["title"])
    if reason:
        print(f"  Rewrite rejected ({reason}): '{cleaned}' for '{article['title']}'")
        article["rewrite_rejected"] = reason
        return _fallback_title(article)
    return cleaned


def rewrite_title(article: dict) -> dict:
    """Rewrite a single article title using Claude, with retry on 529 overload."""
    import re
    summary = article.get("summary") or ""
    # Strip HTML tags from summary for cleaner context
    summary_text = re.sub(r"<[^>]+>", "", summary).strip()[:300]

    # Skip rewrite entirely if there's nothing to ground it on
    if not summary_text:
        article["rewritten_title"] = _fallback_title(article)
        return article

    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=60,
                messages=[{"role": "user", "content": REWRITE_PROMPT.format(title=article["title"], summary=summary_text)}],
            )
            article["rewritten_title"] = accept_rewrite(article, message.content[0].text)
            return article
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt <= MAX_RETRIES:
                print(f"  Title rewrite overloaded (attempt {attempt}/{MAX_RETRIES}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                print(f"  Title rewrite error for '{article['title']}': {e}")
                record_failure("title_rewriter", e)
                article["rewritten_title"] = _fallback_title(article)
                return article
        except Exception as e:
            print(f"  Title rewrite error for '{article['title']}': {e}")
            record_failure("title_rewriter", e)
            article["rewritten_title"] = _fallback_title(article)
            return article
    article["rewritten_title"] = _fallback_title(article)
    return article


def rewrite_titles(articles: list[dict], enabled: bool | None = None) -> list[dict]:
    """Rewrite titles for all articles, only when enabled.

    The daily workflow enables it with CC_REWRITE_TITLES=1. When disabled,
    articles are returned untouched and keep the cleaned publisher headline.
    """
    if enabled is None:
        enabled = REWRITE_TITLES_ENABLED
    if not enabled:
        return articles
    return [rewrite_title(a) for a in articles]
