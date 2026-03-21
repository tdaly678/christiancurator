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
import anthropic
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

THEME_HISTORY_PATH = Path(__file__).parent.parent / "docs" / "theme_history.json"
MAX_HISTORY_DAYS = 60   # how many days to keep in the file
RELATED_DAYS_SHOWN = 3  # how many related days to surface on each daily page


SUMMARY_PROMPT = """\
You are the voice of Christian Curator, a daily digest for evangelical Protestant Christians.
Write a 3-paragraph pastoral editorial surfacing the real theological conversation happening
in the church today.

WHAT TO AIM FOR:
- Go beneath the headlines. What question is the church actually wrestling with today?
  What theological tension is showing up across multiple outlets?
- Look for the deeper thread: authority, suffering, justice, sanctification, ecclesiology,
  the Christian's relationship to culture, eschatology, soteriology — name it directly.
- Reference specific articles by linking to them: [article title](url)
  Use 3–5 links spread naturally — don't force them, but do use them where useful.
- Where writers disagree, name the tension honestly. That's interesting.
{history_section}
VOICE GUIDE:
- Warm, personal, pastoral — like a thoughtful friend who reads widely and loves the church
- First-person plural ("we're seeing", "what strikes us today") or occasional first-person
  ("I find it striking that...")
- Speak directly to the reader ("you", "your faith", "your church")
- Honest and grounded — acknowledge complexity without alarm
- Specific and concrete — name theological concepts, name writers, name debates
- Varied sentence rhythm — punchy and flowing
- Never preachy, never scolding; always encouraging and curious
- Do NOT mention "Christian Curator" by name in the prose

STRUCTURE:
- Paragraph 1 (~3-4 sentences): The dominant theological theme or tension today.
  Open with a specific, grounded observation. What conversation keeps surfacing?
- Paragraph 2 (~3-4 sentences): A second thread — a contrast, a quieter theological story,
  or a world news angle that raises a genuine faith question worth sitting with.
- Paragraph 3 (~2-3 sentences): A brief, encouraging close — a question worth carrying
  into the day, or what today's reading invites us toward.

TODAY'S ARTICLES (title | source | url):
{article_list}

Respond with a JSON object in this exact format — nothing else:
{{
  "paragraphs": ["paragraph 1 text", "paragraph 2 text", "paragraph 3 text"],
  "themes": ["theme 1", "theme 2", "theme 3"]
}}

Use markdown links [title](url) naturally inside the paragraph strings.
Themes should be 3–5 short theological/topical labels (e.g. "pastoral authority",
"church and culture", "sanctification", "suffering and lament").
"""

HISTORY_SECTION_TEMPLATE = """\
RECENT THEOLOGICAL CONVERSATIONS (from previous days — use these to create continuity):
{history_lines}

If today's content revisits one of these themes, weave in a natural reference in your prose
— e.g. "Earlier this week we were watching [this same tension](https://christiancurator.com/daily/SLUG/) play out..."
or "That question hasn't gone away — [on March 19](https://christiancurator.com/daily/2026-03-19/) several
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
            f"- {h['date']} (https://christiancurator.com/daily/{h['slug']}/): "
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
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=900,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()

        # Strip markdown code fences if present
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

        data = json.loads(raw)
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
