"""
email_sender.py — builds and sends the daily digest email via Brevo API.

Email structure:
  Preheader (invisible, from Daily Pulse first sentence)
  Header (masthead)
  "In the Conversation Today" — one featured topic card
  "In Case You Missed It — Yesterday" — one topic card from yesterday
      (never the same slug that was sent as "today's card" the previous day)
  CTA → christiancurator.com
  Forward nudge
  Footer
"""

import os
import re
import json
import requests
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_LIST_ID = 2
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = "Christian Curator"
BREVO_API_URL = "https://api.brevo.com/v3/emailCampaigns"

DOCS_DIR = Path(__file__).parent.parent / "docs"
FEATURED_TOPIC_LOG_PATH = DOCS_DIR / "featured_topic_log.json"
SENT_TOPIC_LOG_PATH = DOCS_DIR / "sent_topic_log.json"


# ── Topic log helpers ──────────────────────────────────────────────────────────

def _load_json_log(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_json_log(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_topic_cards():
    """
    Return (today_card, yesterday_card) topic dicts, or (None, None) if unavailable.

    - today_card:     the top featured topic for today
    - yesterday_card: the top topic from yesterday that was NOT already sent as
                      yesterday's "today_card" (so readers always see something fresh)

    Also records today's sent slug in sent_topic_log.json.
    """
    today_iso = date.today().isoformat()
    yesterday_iso = (date.today() - timedelta(days=1)).isoformat()

    featured_log = _load_json_log(FEATURED_TOPIC_LOG_PATH)
    sent_log = _load_json_log(SENT_TOPIC_LOG_PATH)

    # ── Today's card ──────────────────────────────────────────────
    today_topics = featured_log.get(today_iso, [])
    today_card = today_topics[0] if today_topics else None

    # Record it so tomorrow's "yesterday" logic can exclude it
    if today_card:
        sent_log[today_iso] = today_card["slug"]
        # Prune sent log to last 30 days
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        sent_log = {k: v for k, v in sent_log.items() if k >= cutoff}
        _save_json_log(SENT_TOPIC_LOG_PATH, sent_log)

    # ── Yesterday's card ─────────────────────────────────────────
    yesterday_topics = featured_log.get(yesterday_iso, [])
    already_sent_slug = sent_log.get(yesterday_iso)  # what ran as "today's card" yesterday
    today_slug = today_card["slug"] if today_card else None

    yesterday_card = None
    for t in yesterday_topics:
        # Skip if it was already shown as yesterday's "today's card"
        # Also skip if it's the same topic as today's card (no point repeating it)
        if t["slug"] != already_sent_slug and t["slug"] != today_slug:
            yesterday_card = t
            break

    return today_card, yesterday_card


# ── Card renderer ──────────────────────────────────────────────────────────────

def _render_topic_card(topic: dict, muted: bool = False) -> str:
    """Render one topic card as email-safe inline HTML."""
    border_color = "#e8e5e0" if muted else "#e0ddd8"
    bg_color = "#fdfdfc" if muted else "#ffffff"
    accent_color = "#b5ccb8" if muted else "#2C4A2E"
    article_link_color = "#333333" if muted else "#1a1a1a"
    cta_color = "#2C4A2E"

    articles_html = ""
    for a in (topic.get("articles") or [])[:2]:
        title = a.get("title") or ""
        url = a.get("url") or "#"
        author = (a.get("author") or "").strip()
        source = (a.get("source_name") or "").strip()
        byline = (
            f'{author} &middot; {source}' if author and author.lower() != source.lower()
            else source
        )
        articles_html += f"""
        <div style="padding:8px 0;border-top:1px solid #f0ede8;">
          <div style="font-family:Georgia,serif;font-size:13.5px;font-weight:600;line-height:1.35;margin-bottom:3px;">
            <a href="{url}" style="color:{article_link_color};text-decoration:none;">{title}</a>
          </div>
          <div style="font-size:11px;color:#aaa;">{byline}</div>
        </div>"""

    articles_label = "What was being written about this" if muted else "What&rsquo;s being written about this"

    slug = topic.get("slug", "")
    explore_url = f"https://www.christiancurator.com/topics/{slug}/"

    return f"""
      <div style="border:1px solid {border_color};border-radius:5px;padding:18px 20px 16px;background:{bg_color};">
        <div style="font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.14em;color:{cta_color};margin-bottom:7px;">{topic.get("category", "")}</div>
        <div style="font-family:Georgia,serif;font-size:20px;font-weight:700;line-height:1.25;color:#1a1a1a;margin-bottom:12px;">{topic.get("name", "")}</div>
        <div style="font-size:13.5px;color:#555;font-style:italic;line-height:1.6;border-left:2px solid {accent_color};padding-left:10px;margin-bottom:16px;">{topic.get("hook", "")}</div>
        <div style="font-size:9.5px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#aaa;margin-bottom:9px;">{articles_label}</div>
        {articles_html}
        <div style="border-top:1px solid #e0ddd8;margin-top:12px;padding-top:12px;">
          <a href="{explore_url}" style="font-size:13px;font-weight:700;color:{cta_color};text-decoration:none;">Explore this topic &rarr;</a>
        </div>
      </div>"""


# ── Main email builder ─────────────────────────────────────────────────────────

def build_email_html(articles: list[dict], yesterday_articles: list[dict],
                     daily_summary: dict = None, research_articles: list[dict] = None) -> str:
    if isinstance(articles, dict):
        articles = articles.get("articles", [])

    today = date.today().strftime("%B %-d, %Y")

    # ── Preheader (invisible inbox preview text) ───────────────────────────────
    preheader_text = ""
    if daily_summary and daily_summary.get("paragraphs_plain"):
        first_para = daily_summary["paragraphs_plain"][0]
        first_sentence = re.split(r'(?<=[.!?])\s', first_para)[0]
        preheader_text = first_sentence[:150]
    elif articles:
        lead = next((a for a in articles if a.get("source_type") != "world_news"), None)
        if lead:
            preheader_text = (lead.get("rewritten_title") or lead.get("title", ""))[:150]

    preheader_html = f"""
    <div style="display:none;max-height:0;overflow:hidden;font-size:1px;color:#faf9f7;">
      {preheader_text}&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌
    </div>""" if preheader_text else ""

    # ── Topic cards ────────────────────────────────────────────────────────────
    today_card, yesterday_card = _get_topic_cards()

    today_section_html = ""
    if today_card:
        today_section_html = f"""
    <div style="margin-bottom:8px;">
      <div style="font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#1a1a1a;border-bottom:2px solid #1a1a1a;padding-bottom:6px;margin-bottom:16px;">
        In the Conversation Today
      </div>
      {_render_topic_card(today_card, muted=False)}
    </div>"""

    yesterday_section_html = ""
    if yesterday_card:
        yesterday_section_html = f"""
    <div style="margin-top:28px;margin-bottom:28px;">
      <div style="font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#aaa;border-bottom:1px solid #e0ddd8;padding-bottom:6px;margin-bottom:16px;">
        In Case You Missed It &mdash; Yesterday
      </div>
      {_render_topic_card(yesterday_card, muted=True)}
    </div>"""

    # ── CTA ────────────────────────────────────────────────────────────────────
    cta_html = """
    <div style="text-align:center;margin:32px 0;padding:24px 20px;background:#EFF4F0;border:1px solid #B5CCB8;border-radius:6px;">
      <div style="font-family:Georgia,serif;font-size:17px;font-weight:700;color:#1a1a1a;margin-bottom:6px;">See all the conversations happening today</div>
      <div style="font-size:13px;color:#555;margin-bottom:18px;">Theology &middot; Church Life &middot; Spiritual Formation &middot; Culture &amp; Society</div>
      <a href="https://www.christiancurator.com/"
         style="display:inline-block;background:#2C4A2E;color:#fff;font-family:Georgia,serif;
                font-size:15px;font-weight:700;padding:13px 28px;border-radius:4px;
                text-decoration:none;letter-spacing:0.02em;">
        Visit Christian Curator &rarr;
      </a>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#faf9f7;font-family:Arial,sans-serif;color:#1a1a1a;">
  {preheader_html}
  <div style="max-width:600px;margin:0 auto;padding:24px 20px;">

    <!-- Forwarded banner -->
    <div style="background:#EFF4F0;border:1px solid #B5CCB8;border-radius:4px;padding:10px 16px;margin-bottom:16px;text-align:center;">
      <span style="font-size:12px;color:#2C4A2E;">Was this forwarded to you?</span>
      <a href="https://www.christiancurator.com/#cc-email-box" style="display:inline-block;margin-left:10px;background:#2C4A2E;color:#fff;font-size:12px;font-weight:700;padding:5px 14px;border-radius:3px;text-decoration:none;">Subscribe Free &rarr;</a>
    </div>

    <!-- Header -->
    <div style="border-bottom:2px solid #1a1a1a;padding-bottom:16px;margin-bottom:28px;text-align:center;">
      <div style="font-size:11px;color:#888;letter-spacing:0.05em;margin-bottom:8px;">{today}</div>
      <div style="font-family:Georgia,serif;font-size:34px;font-weight:700;color:#1a1a1a;">Christian Curator</div>
      <div style="font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#888;margin-top:6px;">For curious Christians seeking clarity on the questions that matter most</div>
    </div>

    {today_section_html}
    {yesterday_section_html}
    {cta_html}

    <!-- Forward nudge -->
    <div style="text-align:center;margin:28px 0 0;padding:18px 20px;border:1px dashed #c8d9c9;border-radius:4px;background:#f7fbf7;">
      <div style="font-size:13px;color:#3a3a3a;margin-bottom:8px;">Know someone who&rsquo;d enjoy this?</div>
      <div style="font-size:12px;color:#666;">Forward this email — it takes two seconds and means a lot.</div>
      <div style="margin-top:10px;">
        <a href="https://www.christiancurator.com/#cc-email-box" style="font-size:12px;font-weight:700;color:#2C4A2E;text-decoration:none;">christiancurator.com &rarr;</a>
      </div>
    </div>

    <!-- Footer -->
    <div style="border-top:2px solid #1a1a1a;margin-top:28px;padding-top:16px;font-size:11px;color:#aaa;text-align:center;">
      <p>All links go to original sources. We curate; they create.</p>
      <p style="margin-top:8px;"><a href="https://www.christiancurator.com" style="color:#2C4A2E;">christiancurator.com</a></p>
    </div>

  </div>
</body>
</html>"""


def save_email_html(html_content: str) -> str:
    path = DOCS_DIR / "email_draft.html"
    path.write_text(html_content, encoding="utf-8")
    return str(path.resolve())


def send_email(articles: list[dict], yesterday_articles: list[dict],
               daily_summary: dict = None, research_articles: list[dict] = None) -> bool:
    if isinstance(articles, dict):
        articles = articles.get("articles", [])

    today = date.today().strftime("%B %-d, %Y")
    subject = f"Christian Curator — {today}"
    html_content = build_email_html(articles, yesterday_articles, daily_summary=daily_summary,
                                    research_articles=research_articles)

    path = save_email_html(html_content)
    print(f"  Email HTML saved to: {path}")

    if not BREVO_API_KEY:
        print("  Warning: BREVO_API_KEY not set. Skipping email send.")
        return False
    if not BREVO_SENDER_EMAIL:
        print("  Warning: BREVO_SENDER_EMAIL not set. Skipping email send.")
        return False

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "name": f"Christian Curator — {today}",
        "subject": subject,
        "sender": {"name": BREVO_SENDER_NAME, "email": BREVO_SENDER_EMAIL},
        "type": "classic",
        "htmlContent": html_content,
        "recipients": {"listIds": [BREVO_LIST_ID]},
    }

    try:
        response = requests.post(BREVO_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        campaign_id = response.json().get("id")
        print(f"  Campaign created: ID {campaign_id}")
    except requests.exceptions.HTTPError as e:
        print(f"  Brevo campaign creation error: {e}")
        print(f"  Brevo response: {e.response.text}")
        return False

    try:
        send_url = f"{BREVO_API_URL}/{campaign_id}/sendNow"
        response = requests.post(send_url, headers=headers, timeout=30)
        response.raise_for_status()
        print(f"  Email sent successfully via Brevo: '{subject}'")
        return True
    except requests.exceptions.HTTPError as e:
        print(f"  Brevo send error: {e}")
        print(f"  Brevo response: {e.response.text}")
        print(f"  Campaign was created (ID {campaign_id}) — log into Brevo to send manually.")
        return False
