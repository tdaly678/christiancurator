"""
daily_summary.py — generates a short pastoral editorial summarizing what the
Christian world is talking about today, based on the day's top-scored articles.

Also maintains docs/theme_history.json — a rolling record of daily themes used
to surface cross-day theological conversations in the editorial prose.

Returns a dict:
  {
    "paragraphs_html":  ["<p>para with <a href=...> links</a></p>", ...],
    "paragraphs_plain": ["para plain text...", ...],   # for sidebar / meta
    "themes":           ["pastoral authority", "sanctification", ...],
    "related_days":     [{"slug": "2026-03-19", "date": "March 19, 2026",
                          "excerpt": "...", "shared_themes": ["..."]}],
    "date":  "March 21, 2026",
    "slug":  "2026-03-21",
  }
"""

from __future__ import annotations

import os
import re
import json
import time
import anthropic
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MAX_RETRIES = 4
RETRY_DELAYS = [5, 15, 30, 60]  # seconds between retries


def _api_call_with_retry(fn, label="API call"):
    """Call fn() with exponential backoff on 529 overload errors."""
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            return fn()
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt <= MAX_RETRIES:
                print(f"  {label}: API overloaded (attempt {attempt}/{MAX_RETRIES}), retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise
    return None

THEME_HISTORY_PATH = Path(__file__).parent.parent / "docs" / "theme_history.json"
MAX_HISTORY_DAYS = 60   # how many days to keep in the file
RELATED_DAYS_SHOWN = 3  # how many related days to surface on each daily page


SUMMARY_PROMPT = """\
You are a writer for Christian Curator, a daily digest for evangelical Protestant Christians.
Write a 2-paragraph dispatch — 8 to 10 sentences total — about what the church is talking
about today. Use the articles listed below as your source material.
{history_section}
STUDY THIS EXAMPLE CAREFULLY. Write in exactly this style:

---EXAMPLE START---
Russell Moore said something last year that keeps coming back to me. He was writing about
the temptation for Christians to turn every news cycle into a referendum on their identity,
and he put it plainly: the church is not a political party with better songs.
[The Gospel Coalition](https://example.com) and [Christianity Today](https://example.com)
are circling the same problem this week. TGC says the threat is doctrinal — bad theology
quietly replacing good. CT says the problem is pace. The speed of social media leaves no
room for the kind of slow discernment faith actually requires. Neither outlet is wrong.

[Mere Orthodoxy](https://example.com) ran a piece for World Down Syndrome Day asking who
the church counts as a full theological participant. Not a rhetorical question. A real one
with stakes. A federal judge also ordered an ICE facility in Minneapolis to allow clergy
access to detainees — [World Magazine](https://example.com) had the item. Small legal
story. Larger question about who the church shows up for.
---EXAMPLE END---

Notice what this example does:
- Opens with a person and a specific memory, not "Today's content raises the question of..."
- Sentences are SHORT. Many are under 12 words. Some are fragments.
- First person ("keeps coming back to me") but not overdone
- Paragraph 2 starts mid-thought, not with a transition word
- No transition words between paragraphs: not "Meanwhile", "Additionally", "On a different
  note", "Furthermore", "However", "Notably", "Interestingly", or any variant
- "Neither outlet is wrong" — direct, not "both diagnoses feel true at the same time"
- Links mid-sentence, not announced

NEVER WRITE THESE PHRASES (AI tells that detectors flag immediately):
"on a different/completely different register", "both X and Y feel true",
"makes the case that", "it's worth noting", "underscores", "navigating",
"in the realm of", "a testament to", "shed light on", "delve into",
"at the same time", "collectively", "ultimately", "moreover", "additionally",
"it is important to", "the argument is simple", "in today's world"

Now write the actual dispatch using TODAY'S ARTICLES below.
Use 2–4 markdown links [title](url) placed naturally.
Surface the real theological tension, not just what the articles are about.
Name writers and outlets by name.
Where they disagree, say so plainly.

CRITICAL: State the main theme in the very first sentence. A lay reader should know
what the day is about before reading the second sentence. Then show how the individual
pieces connect to that theme. Don't make the reader figure out the connection themselves.

TODAY'S ARTICLES (title | source | url):
{article_list}

Respond with a JSON object in this exact format — nothing else:
{{
  "paragraphs": ["paragraph 1 text", "paragraph 2 text"],
  "themes": ["theme 1", "theme 2", "theme 3"]
}}

Themes should be 3–5 short theological/topical labels (e.g. "pastoral authority",
"church and culture", "sanctification", "suffering and lament").
"""

HISTORY_SECTION_TEMPLATE = """\
RECENT THEOLOGICAL CONVERSATIONS (from previous days — use these to create continuity):
{history_lines}

If today's content revisits one of these themes, weave in a natural reference in your prose
— e.g. "Earlier this week we were watching [this same tension](https://www.christiancurator.com/daily/SLUG/) play out..."
or "That question hasn't gone away — [on March 19](https://www.christiancurator.com/daily/2026-03-19/) several
writers approached it from a different angle."
Only reference previous days when it's genuinely relevant and adds insight. Don't force it.

"""


# ---------------------------------------------------------------------------
# Theme history helpers
# ---------------------------------------------------------------------------

def load_theme_history() -> list[dict]:
    """Load the rolling theme history from docs/theme_history.json."""
    if not THEME_HISTORY_PATH.exists():
        return []
    try:
        with open(THEME_HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_theme_history(summary: dict) -> None:
    """Append today's entry to theme_history.json, keeping last MAX_HISTORY_DAYS days."""
    if not summary:
        return

    history = load_theme_history()

    # Remove any existing entry for today (idempotent re-runs)
    history = [h for h in history if h.get("slug") != summary["slug"]]

    history.append({
        "slug": summary["slug"],
        "date": summary["date"],
        "themes": summary.get("themes", []),
        "excerpt": summary.get("paragraphs_plain", [""])[0][:200],
    })

    # Keep only the most recent N days
    history = sorted(history, key=lambda h: h["slug"])[-MAX_HISTORY_DAYS:]

    THEME_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(THEME_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"  Theme history saved ({len(history)} days on record).")


# ---------------------------------------------------------------------------
# Related days
# ---------------------------------------------------------------------------

def find_related_days(today_themes: list[str], history: list[dict], today_slug: str) -> list[dict]:
    """Return up to RELATED_DAYS_SHOWN previous days that share themes with today."""
    scored = []
    today_set = {t.lower() for t in today_themes}

    for entry in history:
        if entry["slug"] == today_slug:
            continue
        entry_set = {t.lower() for t in entry.get("themes", [])}
        shared = today_set & entry_set
        if shared:
            scored.append({
                "slug": entry["slug"],
                "date": entry["date"],
                "excerpt": entry.get("excerpt", ""),
                "shared_themes": sorted(shared),
                "_score": len(shared),
            })

    scored.sort(key=lambda x: (x["_score"], x["slug"]), reverse=True)
    for s in scored:
        del s["_score"]
    return scored[:RELATED_DAYS_SHOWN]


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _markdown_links_to_html(text: str) -> str:
    return re.sub(
        r'\[([^\]]+)\]\((https?://[^\)]+)\)',
        r'<a href="\2" target="_blank" rel="noopener">\1</a>',
        text
    )


def _strip_markdown_links(text: str) -> str:
    return re.sub(r'\[([^\]]+)\]\(https?://[^\)]+\)', r'\1', text)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_daily_summary(articles: list[dict]) -> dict | None:
    """Generate a 3-paragraph pastoral daily summary from the top articles."""
    today = date.today()
    today_slug = today.strftime("%Y-%m-%d")
    candidates = [a for a in articles if (a.get("final_score") or 0) > 0][:15]

    if len(candidates) < 5:
        print("  Daily summary: not enough articles, skipping.")
        return None

    # Build article list for prompt
    article_list = "\n".join(
        f"- {a.get('rewritten_title') or a['title']} | {a.get('source_name', '')} | {a['url']}"
        for a in candidates
    )

    # Load history and build context section for prompt
    history = load_theme_history()
    recent = [h for h in history if h["slug"] != today_slug][-14:]  # last 14 days

    if recent:
        history_lines = "\n".join(
            f"- {h['date']} (https://www.christiancurator.com/daily/{h['slug']}/): "
            f"{', '.join(h['themes'])} — \"{h['excerpt'][:120]}...\""
            for h in reversed(recent)  # most recent first
        )
        history_section = HISTORY_SECTION_TEMPLATE.format(history_lines=history_lines)
    else:
        history_section = ""

    prompt = SUMMARY_PROMPT.format(
        article_list=article_list,
        history_section=history_section,
    )

    try:
        def _call():
            return client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
        message = _api_call_with_retry(_call, "Daily summary")
        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as json_err:
            print(f"  Daily summary: JSON parse error — {json_err}")
            print(f"  Raw response was: {raw[:300]}")
            return None
        paragraphs_raw = data.get("paragraphs", [])
        themes = data.get("themes", [])

        if not paragraphs_raw:
            print("  Daily summary: empty paragraphs, skipping.")
            return None

        paragraphs_html = [_markdown_links_to_html(p) for p in paragraphs_raw]
        paragraphs_plain = [_strip_markdown_links(p) for p in paragraphs_raw]

        related_days = find_related_days(themes, history, today_slug)

        return {
            "paragraphs_html":  paragraphs_html,
            "paragraphs_plain": paragraphs_plain,
            "themes":           themes,
            "related_days":     related_days,
            "date":             today.strftime("%B %-d, %Y"),
            "slug":             today_slug,
        }

    except Exception as e:
        print(f"  Daily summary error: {e}")
        return None
