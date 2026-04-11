"""
email_sender.py — builds and sends the daily digest email via Brevo API.

Email structure:
  Preheader (invisible, from Daily Pulse first sentence)
  Header (masthead)
  "In the Conversation Today" — up to 3 featured topic cards for today
      All article links direct readers to christiancurator.com homepage
  CTA → christiancurator.com
  Forward nudge
  Footer
"""

import hashlib
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
    Return a list of up to 3 featured topic dicts for today, or [] if unavailable.

    Also records today's top slug in sent_topic_log.json for downstream use.
    """
    today_iso = date.today().isoformat()

    featured_log = _load_json_log(FEATURED_TOPIC_LOG_PATH)
    sent_log = _load_json_log(SENT_TOPIC_LOG_PATH)

    today_topics = featured_log.get(today_iso, [])
    today_cards = today_topics[:3]

    # Record the top slug so it can be used by other logic if needed
    if today_cards:
        sent_log[today_iso] = today_cards[0]["slug"]
        # Prune sent log to last 30 days
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        sent_log = {k: v for k, v in sent_log.items() if k >= cutoff}
        _save_json_log(SENT_TOPIC_LOG_PATH, sent_log)

    return today_cards


# ── Anchor helper ──────────────────────────────────────────────────────────────

def _article_anchor(url: str) -> str:
    """Return the same stable anchor id used in the homepage template."""
    return "a" + hashlib.md5((url or "").encode()).hexdigest()[:8]


# ── Card renderer ──────────────────────────────────────────────────────────────

def _render_topic_card(topic: dict, muted: bool = False) -> str:
    """Render one topic card as email-safe inline HTML, styled to match the site."""
    accent_color = "#b5ccb8" if muted else "#2C4A2E"
    title_color  = "#444444" if muted else "#1a1a1a"

    articles_html = ""
    for a in (topic.get("articles") or [])[:2]:
        title  = a.get("title") or ""
        url    = a.get("url") or ""
        author = (a.get("author") or "").strip()
        source = (a.get("source_name") or "").strip()
        byline = (
            f'{author} &middot; {source}' if author and author.lower() != source.lower()
            else source
        )
        anchor = _article_anchor(url)
        href   = f"https://www.christiancurator.com/#{anchor}" if url else "https://www.christiancurator.com/"
        articles_html += f"""
        <div style="padding:9px 0;border-top:1px solid #f0ede8;">
          <a href="{href}" style="font-family:Georgia,'Times New Roman',serif;font-size:15px;font-weight:600;line-height:1.35;color:{title_color};text-decoration:none;display:block;margin-bottom:3px;">{title}</a>
          <div style="font-size:11px;color:#aaa;">{byline}</div>
        </div>"""

    return f"""
      <div style="border-top:2px solid {'#d0ccc6' if muted else '#1a1a1a'};padding-top:14px;margin-bottom:4px;">
        <div style="font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.14em;color:{accent_color};margin-bottom:6px;">{topic.get("category", "")}</div>
        <div style="font-family:Georgia,'Times New Roman',serif;font-size:23px;font-weight:600;line-height:1.2;color:{title_color};margin-bottom:10px;">{topic.get("name", "")}</div>
        <div style="font-size:13.5px;color:#555;font-style:italic;line-height:1.6;border-left:2px solid {accent_color};padding-left:10px;margin-bottom:14px;">{topic.get("summary") or topic.get("hook", "")}</div>
        {articles_html}
        <div style="margin-top:12px;">
          <a href="https://www.christiancurator.com/topics/{topic.get('slug', '')}/" style="font-size:12px;font-weight:700;color:#2C4A2E;text-decoration:none;">More on {topic.get('name','')} &rarr;</a>
        </div>
      </div>"""


# ── World news card renderer ───────────────────────────────────────────────────

def _render_world_news_card(world_articles: list[dict]) -> str:
    """Render a single navy-toned world news card for up to 3 articles."""
    if not world_articles:
        return ""

    rows_html = ""
    for i, a in enumerate(world_articles[:3]):
        title  = a.get("rewritten_title") or a.get("title") or ""
        author = (a.get("author") or "").strip()
        source = (a.get("source_name") or "").strip()
        byline = (
            f'{author} &middot; {source}'
            if author and author.lower() != source.lower()
            else source
        )
        border_top = "border-top:1px solid #c5d4ea;" if i > 0 else ""
        anchor = _article_anchor(a.get("url", ""))
        href = f"https://www.christiancurator.com/#{anchor}" if a.get("url") else "https://www.christiancurator.com/"
        rows_html += f"""
        <div style="padding:10px 0;{border_top}display:table;width:100%;">
          <div style="display:table-cell;width:26px;font-size:11px;font-weight:700;color:#7a93b8;vertical-align:top;padding-top:2px;">{i + 1}</div>
          <div style="display:table-cell;vertical-align:top;">
            <div style="font-family:Georgia,'Times New Roman',serif;font-size:14px;font-weight:600;line-height:1.35;margin-bottom:3px;">
              <a href="{href}" style="color:#12284a;text-decoration:none;">{title}</a>
            </div>
            <div style="font-size:11px;color:#7a93b8;">{byline}</div>
          </div>
        </div>"""

    return f"""
      <div style="background:#f0f4fb;border:1px solid #c5d4ea;border-radius:6px;padding:18px 20px 14px;">
        <div style="font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.16em;color:#1E3A6E;border-bottom:2px solid #1E3A6E;padding-bottom:6px;margin-bottom:12px;">
          World News &amp; Culture
        </div>
        <div style="font-size:11.5px;color:#5a7099;margin-bottom:12px;font-style:italic;">
          From the broader world — filtered for what matters to Christians
        </div>
        {rows_html}
        <div style="border-top:1px solid #c5d4ea;margin-top:12px;padding-top:12px;">
          <a href="https://www.christiancurator.com/digest/" style="font-size:13px;font-weight:700;color:#1E3A6E;text-decoration:none;">Read today&rsquo;s full digest &rarr;</a>
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
    today_cards = _get_topic_cards()

    cards_html = ""
    for card in today_cards:
        cards_html += f"""
        <div style="margin-bottom:20px;">
          {_render_topic_card(card, muted=False)}
        </div>"""

    # ── World news card ────────────────────────────────────────────────────────
    world_top3 = sorted(
        [a for a in articles if a.get("source_type") == "world_news"],
        key=lambda a: a.get("final_score", a.get("score", 0)), reverse=True
    )[:3]
    world_card_html = ""
    if world_top3:
        world_card_html = f"""
        <div style="margin-bottom:20px;">
          {_render_world_news_card(world_top3)}
        </div>"""

    today_section_html = ""
    if cards_html or world_card_html:
        today_section_html = f"""
    <div style="margin-bottom:8px;">
      <div style="font-size:10px;font-weight:600;letter-spacing:0.16em;text-transform:uppercase;color:#1a1a1a;border-bottom:2.5px solid #1a1a1a;padding-bottom:6px;margin-bottom:20px;">
        In the Conversation Today
      </div>
      {cards_html}
      {world_card_html}
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
<body style="margin:0;padding:0;background:#faf9f7;font-family:'Helvetica Neue',Arial,sans-serif;color:#1a1a1a;">
  {preheader_html}
  <div style="max-width:600px;margin:0 auto;padding:20px 20px 32px;">

    <!-- Top bar: date left, subscribe right (mirrors site cc-top-bar) -->
    <div style="display:table;width:100%;margin-bottom:14px;">
      <div style="display:table-cell;font-size:12px;color:#888;letter-spacing:0.02em;vertical-align:middle;">{today}</div>
      <div style="display:table-cell;text-align:right;vertical-align:middle;">
        <span style="font-size:12px;color:#888;">Forwarded to you? </span>
        <a href="https://www.christiancurator.com/#cc-email-box" style="background:#2C4A2E;color:#fff;font-size:12px;font-weight:700;padding:5px 14px;border-radius:3px;text-decoration:none;display:inline-block;margin-left:6px;">Subscribe Free &rarr;</a>
      </div>
    </div>

    <!-- Masthead (mirrors site cc-masthead) -->
    <div style="text-align:center;padding-bottom:14px;border-bottom:2.5px solid #1a1a1a;margin-bottom:26px;">
      <div style="font-family:Georgia,'Times New Roman',serif;font-size:38px;font-weight:600;letter-spacing:-0.02em;color:#1a1a1a;line-height:1;">Christian Curator</div>
      <div style="font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#888;margin-top:8px;font-weight:400;">For curious Christians seeking clarity on the questions that matter most</div>
    </div>

    {today_section_html}
    {cta_html}

    <!-- Forward nudge -->
    <div style="margin-top:28px;padding:16px 20px;border:1px solid #e0ddd8;border-radius:4px;">
      <div style="font-size:13px;color:#3a3a3a;margin-bottom:6px;">Know someone who&rsquo;d enjoy this?</div>
      <div style="font-size:12px;color:#888;">Forward this email &mdash; it takes two seconds and means a lot.</div>
      <div style="margin-top:10px;">
        <a href="https://www.christiancurator.com/#cc-email-box" style="font-size:12px;font-weight:700;color:#2C4A2E;text-decoration:none;">christiancurator.com &rarr;</a>
      </div>
    </div>

    <!-- Footer (mirrors site cc-footer) -->
    <div style="border-top:2.5px solid #1a1a1a;margin-top:28px;padding-top:14px;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="font-family:Georgia,'Times New Roman',serif;font-size:15px;font-weight:600;color:#1a1a1a;">Christian Curator</td>
          <td style="text-align:right;font-size:11px;color:#888;">
            <a href="https://www.christiancurator.com/digest/" style="color:#888;text-decoration:none;font-weight:600;">Daily Digest</a>
            &nbsp;&nbsp;
            <a href="https://www.christiancurator.com/archive/" style="color:#888;text-decoration:none;font-weight:600;">Archive</a>
          </td>
        </tr>
      </table>
      <div style="font-size:11px;color:#aaa;margin-top:8px;">Curated from across the evangelical web.</div>
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
