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
    "subject":          "What the local church owes lonely people",  # email subject
    "related_days":     [{"slug": "2026-03-19", "date": "March 19, 2026",
                          "excerpt": "...", "shared_themes": ["..."]}],
    "date":  "March 21, 2026",
    "slug":  "2026-03-21",
  }
"""

from __future__ import annotations

import html
import os
import re
import json
import time
import anthropic
from datetime import date
from pathlib import Path
from dotenv import load_dotenv

from curator.ai_health import record_failure
from curator.headline_voice import SCANDAL_RE, strip_dashes

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MAX_RETRIES = 4
RETRY_DELAYS = [5, 15, 30, 60]  # seconds between retries


def _extract_json(text: str) -> str:
    """Extract JSON from a response that may contain markdown fences or extra text."""
    # Prefer the last ```json ... ``` block (Claude sometimes self-corrects after an error)
    matches = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if matches:
        return matches[-1].strip()
    # Fall back to stripping any leading/trailing fences
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


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
Write a 2-paragraph dispatch (8 to 10 sentences total) surveying the live conversations in
evangelical publishing today. Use the articles listed below as your source material.
{history_section}
WHAT THE PULSE IS: a survey of the debates evangelical writers are having, not a news
roundup. Look for three kinds of conversation: theological questions (doctrine, Scripture,
the church's teaching), philosophical and cultural arguments (how Christians should think
about public life, technology, art, ideas), and praxis (church life, ministry, discipleship,
family, mission). Name the positions being argued and who is arguing them, writer and
outlet, wherever the articles support it. Never invent a position or a disagreement the
articles do not support. Lean on essays, opinion, reviews and long-form pieces; each item
below is marked with its kind, and a news report should appear only when it moves one of
these conversations forward.

TONE: hopeful and constructive, never alarmist. Write as someone who thinks the church's
arguments are worth having and that good people are having them well. Scandal, abuse,
lawsuit, resignation and crisis stories must not lead the Pulse. Mention one only when it is
clearly the dominant story of the day, and then in one sober clause at most, with no lurid
detail, before turning to what writers are thinking and building. Understated RealClear
voice: no hype, no promo language ("must-read", "don't miss", "powerful", "game-changing"),
no exclamation points.

STUDY THIS EXAMPLE CAREFULLY. Write in exactly this style:

---EXAMPLE START---
Evangelical writers are arguing this week about what the local church owes lonely people,
and they disagree in useful ways. [Mere Orthodoxy](https://example.com) treats loneliness
as a formation problem: thin Sunday gatherings form thin people. [Desiring God](https://example.com)
starts somewhere else. Friendship, it says, grows out of shared joy in God, not programs.
Two diagnoses. Both take the congregation seriously.

[Christianity Today](https://example.com) brings the question down to Tuesday night, profiling
churches that rebuilt the midweek meal and watched new members follow. [The Gospel Coalition](https://example.com)
pushes back gently: a table helps, but preaching that names sin and grace is what turns a
meal into fellowship. A Barna release puts numbers under the debate, with adults under 30
reporting the fewest close friends of any age group. The pastors writing about it sound
less worried than curious about what faithful hospitality could look like next year.
---EXAMPLE END---

Notice what this example does:
- Opens by naming the conversation, not "Today's content raises the question of..."
- Names each position and who holds it, and says plainly where they part ways
- Covers the theological angle and the praxis angle of the same question
- Sentences are SHORT. Many are under 12 words. Some are fragments.
- Paragraph 2 starts mid-thought, not with a transition word
- No transition words between paragraphs: not "Meanwhile", "Additionally", "On a different
  note", "Furthermore", "However", "Notably", "Interestingly", or any variant
- Hopeful without being sentimental; the last sentence adds a new observation
- Links mid-sentence, not announced
- No em dashes (—) or en dashes (–) anywhere. Use commas, periods, colons or parentheses

NEVER WRITE THESE PHRASES (AI tells that detectors flag immediately):
"on a different/completely different register", "both X and Y feel true",
"makes the case that", "it's worth noting", "underscores", "navigating",
"in the realm of", "a testament to", "shed light on", "delve into",
"at the same time", "collectively", "ultimately", "moreover", "additionally",
"it is important to", "the argument is simple", "in today's world"

Now write the actual dispatch using TODAY'S ARTICLES below.
Use 2 to 4 markdown links [title](url) placed naturally.
Surface the real theological, philosophical or practical tension, not just what the
articles are about. Name writers and outlets by name.
Where they disagree, say so plainly and fairly, giving each side its best form.

CRITICAL: State the main theme in the very first sentence. A lay reader should know
what the day is about before reading the second sentence. The theme should be a question
or debate the church is working through, never a scandal or a crisis. Then show how the
individual pieces connect to that theme. Don't make the reader figure out the connection
themselves.

ONE THEME, EVERY SENTENCE: Every sentence must advance the theme stated in sentence 1.
Choose your articles AFTER you choose the theme. Use only the pieces that honestly bear
on it, even if that means you mention just two or three outlets. If an article cannot
honestly be tied to the theme, leave it out of the Pulse entirely. Never name-drop an
article mid-paragraph and then invent a bridge back to the theme. Never close with a
sentence whose only job is to force a link between unrelated pieces. Before you answer,
check each sentence: if you deleted it, would the reader lose part of the argument about
the theme? If not, cut it.

Example of the failure to avoid: the theme was election eve and whether the church can
be trusted, paragraph 2 turned to abuse and pastoral power, and then "First Things is
running a piece on global Christian martyrs" appeared out of nowhere, followed by a
closing line straining to connect martyrs to trust. The martyrs piece did not serve the
theme, so it should have been left out.

NO REDUNDANCY: One theme does not mean one point made ten times. Each sentence must
advance a distinct facet, fact, or source of the one theme. Never restate the same idea
in different words. Do not repeat or paraphrase the theme sentence as a closer; the last
sentence must add something the reader has not heard yet. Each source you cite must
contribute something new: a fact, an argument, or a disagreement no other sentence
already carries. If two sentences say the same thing, keep the sharper one and cut the
other. If cutting repeats leaves fewer than 8 sentences, add another honest facet of the
theme from the articles, never a restatement.

TODAY'S ARTICLES (title | source and author | kind | url, then a short excerpt):
{article_list}

Respond with a JSON object in this exact format and nothing else:
{{
  "paragraphs": ["paragraph 1 text", "paragraph 2 text"],
  "themes": ["theme 1", "theme 2", "theme 3"],
  "subject": "email subject line"
}}

Themes should be 3 to 5 short theological/topical labels (e.g. "pastoral authority",
"church and culture", "sanctification", "suffering and lament").

The subject is the daily email's subject line: one plain sentence or phrase of 40 to 75
characters that names the theme of sentence 1 (e.g. "What the local church owes lonely
people"). Understated and hopeful. Never a scandal, crime or crisis. No emoji, no
exclamation point, no hype, no "today's", no dashes, no closing period.
"""

HISTORY_SECTION_TEMPLATE = """\
RECENT THEOLOGICAL CONVERSATIONS (from previous days; use these to create continuity):
{history_lines}

If today's content revisits one of these themes, weave in a natural reference in your prose,
e.g. "Earlier this week we were watching [this same tension](https://www.christiancurator.com/daily/SLUG/) play out..."
or "That question hasn't gone away. [On March 19](https://www.christiancurator.com/daily/2026-03-19/) several
writers approached it from a different angle."
Only reference previous days when it's genuinely relevant and adds insight. Don't force it.
A callback to an earlier day must advance today's theme like any other sentence.

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


def sanitize_pulse(text: str) -> str:
    """Strip em and en dashes from Pulse copy (Tom's standing no-em-dash rule)."""
    return strip_dashes(text or "")


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _sentence_key(sentence: str) -> str:
    plain = _strip_markdown_links(sentence).lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", plain).split())


def drop_repeated_sentences(paragraphs: list[str]) -> list[str]:
    """Remove a sentence that repeats an earlier Pulse sentence word for word.

    Backstop for the NO REDUNDANCY prompt rule. Only exact repeats (ignoring
    case, punctuation and link markup) are cut, so paraphrase is left to the
    prompt. A paragraph with no repeat is returned unchanged; one emptied by
    the cut is dropped.
    """
    seen: set[str] = set()
    out = []
    for para in paragraphs:
        kept, changed = [], False
        for sentence in _SENTENCE_SPLIT_RE.split(para.strip()):
            key = _sentence_key(sentence)
            if key and key in seen:
                changed = True
                continue
            if key:
                seen.add(key)
            kept.append(sentence)
        text = " ".join(kept) if changed else para
        if text.strip():
            out.append(text)
    return out


def _strip_markdown_links(text: str) -> str:
    return re.sub(r'\[([^\]]+)\]\(https?://[^\)]+\)', r'\1', text)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

STRICT_JSON_REMINDER = """

IMPORTANT: a previous reply could not be parsed. Return ONLY one valid JSON object
with the keys shown above. No prose before or after it, no code fences, and use straight
ASCII double quotes for JSON strings (never curly quotes)."""


def _parse_summary_json(raw: str):
    """(data, None) on success, (None, error) when the reply isn't valid JSON."""
    try:
        return json.loads(raw), None
    except json.JSONDecodeError as json_err:
        # Second attempt: replace smart quotes and common non-standard characters
        cleaned = (raw
                   .replace('\u201c', '\\"').replace('\u201d', '\\"')  # curly double quotes
                   .replace('\u2018', "\\'").replace('\u2019', "\\'")  # curly single quotes
                   .replace('\u2014', '-').replace('\u2013', '-')      # em/en dashes
                   .replace('\u2026', '...'))                          # ellipsis
        try:
            return json.loads(cleaned), None
        except json.JSONDecodeError:
            return None, json_err


# ---------------------------------------------------------------------------
# Pulse source selection (2026-11-08)
# ---------------------------------------------------------------------------
# Tom: the Pulse had skewed negative and scandal heavy because it read the top
# 15 by importance, which is news value. The Pulse now surveys the debates in
# evangelical publishing, so it reads essays, opinion, reviews and long-form
# first, caps straight news, and admits a scandal story only when it is the
# dominant story of the day.

PULSE_MAX_ITEMS = 15
PULSE_MAX_NEWS = 4      # straight news reports (scandal items count here too)
PULSE_MAX_SCANDAL = 1   # and only when dominant (see is_dominant_story)
PULSE_DOMINANT_OUTLETS = 3
PULSE_EXCERPT_CHARS = 220

# SCANDAL_RE lives in curator/headline_voice.py so the email subject can share it.


def is_scandal(a: dict) -> bool:
    """True for scandal, abuse, lawsuit, resignation and crisis stories (title)."""
    title = a.get("rewritten_title") or a.get("title") or ""
    return bool(SCANDAL_RE.search(title))


def is_news_report(a: dict) -> bool:
    """Straight news, as opposed to essay, opinion, review or data analysis."""
    return (a.get("perspective") == "news"
            or a.get("source_type") == "world_news"
            or "news" in (a.get("tags") or []))


def pulse_kind(a: dict) -> str:
    """The label the prompt shows for each item."""
    if is_scandal(a):
        return "news (scandal)"
    if is_news_report(a):
        return "news"
    if "data" in (a.get("tags") or []):
        return "data"
    return "essay"


def pulse_rank(a: dict) -> float:
    """Blend of importance and depth, so formative essays outrank headlines."""
    importance = a.get("final_score") or 0
    depth = a.get("depth")
    if depth is None:
        depth = importance
    return 0.5 * importance + 0.5 * depth


def is_dominant_story(a: dict, pool: list[dict]) -> bool:
    """A scandal is dominant when it tops the day or 3+ outlets carry it."""
    if pool and a is max(pool, key=lambda x: x.get("final_score") or 0):
        return True
    cluster = a.get("topic_cluster")
    if not cluster or cluster == "unique":
        return False
    outlets = {x.get("source_name") for x in pool if x.get("topic_cluster") == cluster}
    outlets.update(a.get("also_from") or [])
    return len(outlets) >= PULSE_DOMINANT_OUTLETS


def select_pulse_candidates(articles: list[dict],
                            limit: int = PULSE_MAX_ITEMS) -> list[dict]:
    """Pick the Pulse's source articles: essays first, news capped, scandal rare."""
    pool = [a for a in articles if (a.get("final_score") or 0) > 0]
    picked, n_news, n_scandal = [], 0, 0
    for a in sorted(pool, key=pulse_rank, reverse=True):
        if len(picked) >= limit:
            break
        scandal = is_scandal(a)
        if scandal and (n_scandal >= PULSE_MAX_SCANDAL
                        or not is_dominant_story(a, pool)):
            continue
        if (scandal or is_news_report(a)) and n_news >= PULSE_MAX_NEWS:
            continue
        picked.append(a)
        n_scandal += scandal
        n_news += scandal or is_news_report(a)
    return picked


def _excerpt(a: dict) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", a.get("summary") or ""))
    text = re.sub(r"\s*The post .*$", "", text)  # WordPress feed footer
    text = sanitize_pulse(" ".join(text.split()))
    if len(text) > PULSE_EXCERPT_CHARS:
        text = text[:PULSE_EXCERPT_CHARS].rsplit(" ", 1)[0] + "..."
    return text


def format_pulse_article(a: dict) -> str:
    byline = a.get("source_name", "")
    if a.get("author") and a["author"] != byline:
        byline = f"{byline}, {a['author']}"
    line = (f"- {a.get('rewritten_title') or a['title']} | {byline} | "
            f"{pulse_kind(a)} | {a['url']}")
    excerpt = _excerpt(a)
    return f"{line}\n  {excerpt}" if excerpt else line


def generate_daily_summary(articles: list[dict]) -> dict | None:
    """Generate a 2-paragraph Pulse surveying the day's evangelical debates."""
    today = date.today()
    today_slug = today.strftime("%Y-%m-%d")
    candidates = select_pulse_candidates(articles)

    if len(candidates) < 5:
        print("  Daily summary: not enough articles, skipping.")
        return None

    # Build article list for prompt
    article_list = "\n".join(format_pulse_article(a) for a in candidates)

    # Load history and build context section for prompt
    history = load_theme_history()
    recent = [h for h in history if h["slug"] != today_slug][-14:]  # last 14 days

    if recent:
        history_lines = "\n".join(
            f"- {h['date']} (https://www.christiancurator.com/daily/{h['slug']}/): "
            f"{', '.join(h['themes'])}: \"{sanitize_pulse(h['excerpt'][:120])}...\""
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
        data = None
        for attempt, content in enumerate((prompt, prompt + STRICT_JSON_REMINDER), 1):
            def _call():
                return client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=800,
                    messages=[{"role": "user", "content": content}],
                )
            message = _api_call_with_retry(_call, "Daily summary")
            raw = _extract_json(message.content[0].text.strip())
            data, json_err = _parse_summary_json(raw)
            if data is not None:
                break
            print(f"  Daily summary: JSON parse error (attempt {attempt}): {json_err}")
            print(f"  Raw response was: {raw[:300]}")
        if data is None:
            # The email builds a plain lead + subleads Pulse when this is None.
            record_failure("daily_summary", f"JSON parse error after retry: {json_err}")
            return None
        paragraphs_raw = drop_repeated_sentences(
            [sanitize_pulse(p) for p in data.get("paragraphs", [])])
        themes = data.get("themes", [])
        subject = sanitize_pulse(str(data.get("subject") or "")).strip()

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
            "subject":          subject,
            "related_days":     related_days,
            "date":             today.strftime("%B %-d, %Y"),
            "slug":             today_slug,
        }

    except Exception as e:
        print(f"  Daily summary error: {e}")
        record_failure("daily_summary", e)
        return None
