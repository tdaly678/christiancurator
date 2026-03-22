"""
email_sender.py — builds and sends the daily digest email via Brevo API.

Email structure:
  Preheader (invisible, from Daily Pulse first sentence)
  Header (masthead)
  Daily Pulse teaser (2 sentences + link to full dispatch)
  Lead Story
  3 Other Highlights (top article from each of 3 different categories)
  Big CTA → full digest on site
  Yesterday's Best box
  Footer
"""

import os
import re
import requests
from datetime import date
from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_LIST_ID = 2
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = "Christian Curator"
BREVO_API_URL = "https://api.brevo.com/v3/emailCampaigns"

# Categories to draw highlights from, in priority order
HIGHLIGHT_CATEGORIES = ["theology", "culture", "church life", "world_news"]


def strip_tags(html: str) -> str:
    return re.sub(r'<[^>]+>', '', html or '').strip()


def render_byline(article: dict) -> str:
    author = (article.get("author") or "").strip()
    source = (article.get("source_name") or "").strip()
    if author and author.lower() != source.lower():
        return (f'<span style="font-weight:600;color:#3a3a3a;">{author}</span>'
                f'<span style="color:#ccc;"> · </span>'
                f'<span style="color:#aaa;">{source}</span>')
    return f'<span style="color:#aaa;">{source}</span>'


def pick_highlights(articles: list[dict], exclude_urls: set, n: int = 3) -> list[dict]:
    """Pick the top-scoring article from each category until n highlights found."""
    highlights = []
    seen_categories = set()

    # First pass: one best article per category
    for category in HIGHLIGHT_CATEGORIES:
        if len(highlights) >= n:
            break
        for a in articles:
            url = a.get("url", "")
            if url in exclude_urls:
                continue
            tags = a.get("tags") or []
            source_type = a.get("source_type", "")
            in_category = (
                category in tags or
                (category == "world_news" and source_type == "world_news")
            )
            if in_category and category not in seen_categories:
                highlights.append(a)
                exclude_urls.add(url)
                seen_categories.add(category)
                break

    # Second pass: fill any remaining slots with next best articles
    if len(highlights) < n:
        for a in articles:
            if len(highlights) >= n:
                break
            if a.get("url") not in exclude_urls:
                highlights.append(a)
                exclude_urls.add(a.get("url", ""))

    return highlights


def build_email_html(articles: list[dict], yesterday_articles: list[dict],
                     daily_summary: dict = None) -> str:
    if isinstance(articles, dict):
        articles = articles.get("articles", [])
    today = date.today().strftime("%B %-d, %Y")
    today_slug = date.today().strftime("%Y-%m-%d")

    christian = [a for a in articles if a.get("source_type") != "world_news"]
    world_news = [a for a in articles if a.get("source_type") == "world_news"]
    all_articles = christian + world_news

    lead = christian[0] if christian else None
    seen = {lead["url"]} if lead else set()

    highlights = pick_highlights(all_articles, seen, n=3)

    # ── Preheader (invisible inbox preview text) ───────────────────────────
    preheader_text = ""
    if daily_summary and daily_summary.get("paragraphs_plain"):
        # Use first sentence of the daily pulse as preheader
        first_para = daily_summary["paragraphs_plain"][0]
        first_sentence = re.split(r'(?<=[.!?])\s', first_para)[0]
        preheader_text = first_sentence[:150]
    elif lead:
        preheader_text = (lead.get("rewritten_title") or lead.get("title", ""))[:150]

    preheader_html = f"""
    <div style="display:none;max-height:0;overflow:hidden;font-size:1px;color:#faf9f7;">
      {preheader_text}&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌
    </div>""" if preheader_text else ""

    # ── Daily Pulse teaser ─────────────────────────────────────────────────
    pulse_html = ""
    if daily_summary and daily_summary.get("paragraphs_plain"):
        first_para = daily_summary["paragraphs_plain"][0]
        # Trim to ~2 sentences for the teaser
        sentences = re.split(r'(?<=[.!?])\s', first_para)
        teaser = " ".join(sentences[:2])
        pulse_url = f"https://christiancurator.com/daily/{today_slug}/"
        pulse_html = f"""
    <div style="border-left:3px solid #2C4A2E; padding:12px 16px; margin-bottom:28px; background:#f5f8f5;">
      <div style="font-size:10px; font-weight:700; letter-spacing:0.15em; text-transform:uppercase; color:#2C4A2E; margin-bottom:8px;">Today's Pulse</div>
      <div style="font-family:Georgia,serif; font-size:15px; line-height:1.65; color:#333; margin-bottom:10px;">{teaser}</div>
      <a href="{pulse_url}" style="font-size:12px; color:#2C4A2E; font-weight:700; text-decoration:none;">Read today's full dispatch &rarr;</a>
    </div>"""

    # ── Lead story ─────────────────────────────────────────────────────────
    lead_html = ""
    if lead:
        title = lead.get("rewritten_title") or lead.get("title", "")
        excerpt = strip_tags(lead.get("summary", ""))[:220]
        lead_html = f"""
    <div style="margin-bottom:28px;">
      <div style="font-size:10px; font-weight:700; letter-spacing:0.15em; text-transform:uppercase; color:#2C4A2E; margin-bottom:10px;">Lead Story</div>
      <div style="font-family:Georgia,serif; font-size:22px; font-weight:700; line-height:1.3; margin-bottom:8px;">
        <a href="{lead['url']}" style="color:#1a1a1a; text-decoration:none;">{title}</a>
      </div>
      <div style="font-size:11.5px; margin-bottom:8px;">{render_byline(lead)}</div>
      {"<div style='font-size:14px;color:#555;line-height:1.6;'>" + excerpt + "…</div>" if excerpt else ""}
    </div>"""

    # ── Other Highlights ───────────────────────────────────────────────────
    highlights_html = ""
    if highlights:
        rows = ""
        for a in highlights:
            title = a.get("rewritten_title") or a.get("title", "")
            rows += f"""
      <div style="padding:12px 0; border-bottom:1px solid #e0ddd8;">
        <div style="font-family:Georgia,serif; font-size:15px; font-weight:600; line-height:1.35; margin-bottom:5px;">
          <a href="{a['url']}" style="color:#1a1a1a; text-decoration:none;">{title}</a>
        </div>
        <div style="font-size:11.5px;">{render_byline(a)}</div>
      </div>"""
        highlights_html = f"""
    <div style="margin:28px 0; border-top:1px solid #e0ddd8; padding-top:16px;">
      <div style="font-size:10px; font-weight:700; letter-spacing:0.15em; text-transform:uppercase; color:#2C4A2E; margin-bottom:4px;">Other Highlights</div>
      {rows}
    </div>"""

    # ── Big CTA ────────────────────────────────────────────────────────────
    cta_html = f"""
    <div style="text-align:center; margin:32px 0;">
      <a href="https://christiancurator.com"
         style="display:inline-block; background:#2C4A2E; color:#fff; font-family:Georgia,serif;
                font-size:16px; font-weight:700; padding:14px 32px; border-radius:4px;
                text-decoration:none; letter-spacing:0.02em;">
        See all of today's articles &rarr;
      </a>
      <div style="margin-top:10px; font-size:12px; color:#aaa;">
        Full digest · topic filters · reader personas
      </div>
    </div>"""

    # ── Yesterday's Best ───────────────────────────────────────────────────
    yesterday_html = ""
    if yesterday_articles:
        rows = ""
        for a in yesterday_articles:
            rows += f"""
        <div style="padding:8px 0; border-bottom:1px solid #B5CCB8;">
          <div style="font-family:Georgia,serif; font-size:14px; font-weight:600; margin-bottom:4px;">
            <a href="{a['url']}" style="color:#1a1a1a; text-decoration:none;">{a.get('title','')}</a>
          </div>
          <span style="background:#d4e6d5; border:1px solid #B5CCB8; padding:2px 7px; font-size:11px; font-weight:600; color:#2C4A2E; border-radius:2px;">{a.get('source_name','')}</span>
        </div>"""
        yesterday_html = f"""
    <div style="background:#EFF4F0; border:1px solid #B5CCB8; border-radius:6px; padding:16px; margin:28px 0;">
      <div style="font-size:10px; font-weight:700; letter-spacing:0.15em; text-transform:uppercase; color:#2C4A2E; margin-bottom:10px;">Yesterday's Best</div>
      {rows}
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
      <a href="https://christiancurator.com/#cc-email-box" style="display:inline-block;margin-left:10px;background:#2C4A2E;color:#fff;font-size:12px;font-weight:700;padding:5px 14px;border-radius:3px;text-decoration:none;">Subscribe Free &rarr;</a>
    </div>

    <!-- Header -->
    <div style="border-bottom:2px solid #1a1a1a;padding-bottom:16px;margin-bottom:28px;text-align:center;">
      <div style="font-size:11px;color:#888;letter-spacing:0.05em;margin-bottom:8px;">{today}</div>
      <div style="font-family:Georgia,serif;font-size:34px;font-weight:700;color:#1a1a1a;">Christian Curator</div>
      <div style="font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#888;margin-top:6px;">Curated for the curious Christian</div>
    </div>

    {pulse_html}
    {lead_html}
    {highlights_html}
    {cta_html}
    {yesterday_html}

    <!-- Forward nudge -->
    <div style="text-align:center;margin:28px 0 0;padding:18px 20px;border:1px dashed #c8d9c9;border-radius:4px;background:#f7fbf7;">
      <div style="font-size:13px;color:#3a3a3a;margin-bottom:8px;">Know someone who'd enjoy this?</div>
      <div style="font-size:12px;color:#666;">Forward this email — it takes two seconds and means a lot.<br>They can subscribe free at the link below.</div>
      <div style="margin-top:10px;">
        <a href="https://christiancurator.com/#cc-email-box" style="font-size:12px;font-weight:700;color:#2C4A2E;text-decoration:none;">christiancurator.com &rarr;</a>
      </div>
    </div>

    <!-- Footer -->
    <div style="border-top:2px solid #1a1a1a;margin-top:28px;padding-top:16px;font-size:11px;color:#aaa;text-align:center;">
      <p>All links go to original sources. We curate; they create.</p>
      <p style="margin-top:8px;"><a href="https://christiancurator.com" style="color:#2C4A2E;">christiancurator.com</a></p>
    </div>

  </div>
</body>
</html>"""


def save_email_html(html_content: str) -> str:
    docs_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    path = os.path.join(docs_dir, "email_draft.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return os.path.abspath(path)


def send_email(articles: list[dict], yesterday_articles: list[dict],
               daily_summary: dict = None) -> bool:
    if isinstance(articles, dict):
        articles = articles.get("articles", [])

    today = date.today().strftime("%B %-d, %Y")
    subject = f"Christian Curator — {today}"
    html_content = build_email_html(articles, yesterday_articles, daily_summary=daily_summary)

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
