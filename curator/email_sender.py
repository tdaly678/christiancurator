"""
email_sender.py — builds and sends the daily digest email via Brevo API.
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


def strip_tags(html: str) -> str:
    """Strip HTML tags from a string."""
    return re.sub(r'<[^>]+>', '', html or '').strip()


def render_articles(articles: list[dict]) -> str:
    """Render a list of articles as HTML email rows."""
    out = ""
    for a in articles:
        title = a.get("rewritten_title") or a.get("title", "")
        out += f"""
        <div style="padding:10px 0; border-bottom:1px solid #e0ddd8;">
          <div style="font-family:Georgia,serif; font-size:15px; font-weight:600; line-height:1.35; margin:0 0 5px;">
            <a href="{a['url']}" style="color:#1a1a1a; text-decoration:none;">{title}</a>
          </div>
          <div style="font-size:11px; color:#aaa;">
            <span style="background:#f0ede8; border:1px solid #ddd; padding:2px 7px; font-size:11px; font-weight:600; color:#555; border-radius:2px;">{a['source_name']}</span>
          </div>
        </div>"""
    return out


def build_email_html(articles: list[dict], yesterday_articles: list[dict]) -> str:
    """Build the full HTML email content."""
    if isinstance(articles, dict):
        articles = articles.get("articles", [])
    today = date.today().strftime("%B %-d, %Y")

    christian = [a for a in articles if a.get("source_type") != "world_news"]
    world_news = [a for a in articles if a.get("source_type") == "world_news"]

    lead = christian[0] if christian else None
    theology  = [a for a in christian[1:] if "theology"    in (a.get("tags") or [])][:2]
    culture   = [a for a in christian[1:] if "culture"     in (a.get("tags") or [])][:2]
    church    = [a for a in christian[1:] if "church life" in (a.get("tags") or [])][:2]

    seen = {lead["url"]} if lead else set()
    for a in theology + culture + church:
        seen.add(a["url"])

    # Cap total christian articles at 10 (lead + sections + remainder)
    used = len(theology) + len(culture) + len(church)
    remaining = max(0, 9 - used)  # 9 more after lead = 10 total
    more = [a for a in christian[1:] if a["url"] not in seen][:remaining]

    # ── Lead story block ──────────────────────────────────────────────────────
    lead_html = ""
    if lead:
        title   = lead.get("rewritten_title") or lead.get("title", "")
        excerpt = strip_tags(lead.get("summary", ""))[:220]
        lead_html = f"""
        <div style="margin-bottom:24px;">
          <div style="font-size:10px; font-weight:700; letter-spacing:0.15em; text-transform:uppercase; color:#2C4A2E; margin-bottom:10px;">Lead Story</div>
          <div style="font-family:Georgia,serif; font-size:22px; font-weight:700; line-height:1.3; margin-bottom:8px;">
            <a href="{lead['url']}" style="color:#1a1a1a; text-decoration:none;">{title}</a>
          </div>
          <div style="margin-bottom:8px;">
            <span style="background:#f0ede8; border:1px solid #ddd; padding:2px 7px; font-size:11px; font-weight:600; color:#555; border-radius:2px;">{lead['source_name']}</span>
          </div>
          {"<div style='font-size:14px; color:#555; line-height:1.6;'>" + excerpt + "…</div>" if excerpt else ""}
        </div>"""

    # ── Section helper ────────────────────────────────────────────────────────
    def section(label, arts):
        if not arts:
            return ""
        return f"""
        <div style="margin:24px 0; border-top:1px solid #e0ddd8; padding-top:16px;">
          <div style="font-size:10px; font-weight:700; letter-spacing:0.15em; text-transform:uppercase; color:#2C4A2E; margin-bottom:10px;">{label}</div>
          {render_articles(arts)}
        </div>"""

    # ── Yesterday's Best ──────────────────────────────────────────────────────
    yesterday_html = ""
    if yesterday_articles:
        rows = ""
        for a in yesterday_articles:
            rows += f"""
            <div style="padding:8px 0; border-bottom:1px solid #B5CCB8;">
              <div style="font-family:Georgia,serif; font-size:14px; font-weight:600; margin-bottom:4px;">
                <a href="{a['url']}" style="color:#1a1a1a; text-decoration:none;">{a.get('title','')}</a>
              </div>
              <span style="background:#d4e6d5; border:1px solid #B5CCB8; padding:2px 7px; font-size:11px; font-weight:600; color:#2C4A2E; border-radius:2px;">{a['source_name']}</span>
            </div>"""
        yesterday_html = f"""
        <div style="background:#EFF4F0; border:1px solid #B5CCB8; border-radius:6px; padding:16px; margin:24px 0;">
          <div style="font-size:10px; font-weight:700; letter-spacing:0.15em; text-transform:uppercase; color:#2C4A2E; margin-bottom:10px;">Yesterday's Best</div>
          {rows}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#faf9f7; font-family:'Source Sans 3',Arial,sans-serif; color:#1a1a1a;">
  <div style="max-width:600px; margin:0 auto; padding:24px 20px;">

    <!-- Forwarded banner -->
    <div style="background:#EFF4F0; border:1px solid #B5CCB8; border-radius:4px; padding:10px 16px; margin-bottom:16px; text-align:center;">
      <span style="font-size:12px; color:#2C4A2E;">Was this forwarded to you?</span>
      <a href="https://christiancurator.com/#cc-email-box" style="display:inline-block; margin-left:10px; background:#2C4A2E; color:#fff; font-size:12px; font-weight:700; padding:5px 14px; border-radius:3px; text-decoration:none;">Subscribe Free →</a>
    </div>

    <!-- Header -->
    <div style="border-bottom:2px solid #1a1a1a; padding-bottom:16px; margin-bottom:24px; text-align:center;">
      <div style="font-size:11px; color:#888; letter-spacing:0.05em; margin-bottom:8px;">{today}</div>
      <div style="font-family:Georgia,serif; font-size:34px; font-weight:700; color:#1a1a1a;">Christian Curator</div>
      <div style="font-size:11px; letter-spacing:0.18em; text-transform:uppercase; color:#888; margin-top:6px;">Curated for the curious Christian</div>
    </div>

    <!-- Front page callout -->
    <div style="border-left:3px solid #2C4A2E; padding:10px 14px; margin-bottom:24px; background:#faf9f7;">
      <div style="font-size:13px; color:#1a1a1a; line-height:1.6;">
        This is your <strong>daily highlight reel</strong> — today's best picks from across the Christian web.
        For the full digest, including more articles, topic filters, and reader personas,
        <a href="https://christiancurator.com" style="color:#2C4A2E; font-weight:700;">visit the site →</a>
      </div>
    </div>

    {lead_html}
    {section("Theology &amp; Doctrine", theology)}
    {section("Culture &amp; Society", culture)}
    {section("Church Life", church)}
    {section("More from Today", more)}
    {section("World News", world_news[:3]) if world_news else ""}
    {yesterday_html}

    <!-- Forward CTA -->
    <div style="background:#f0ede8; border-radius:4px; padding:14px 16px; margin:24px 0; text-align:center;">
      <div style="font-size:13px; color:#1a1a1a; font-weight:600; margin-bottom:6px;">Know someone who'd enjoy this?</div>
      <div style="font-size:12px; color:#555;">Forward this email to a friend who loves thoughtful Christian writing.</div>
    </div>

    <!-- Footer -->
    <div style="border-top:2px solid #1a1a1a; margin-top:24px; padding-top:16px; font-size:11px; color:#aaa; text-align:center;">
      <p>All links go to original sources. We curate; they create.</p>
      <p style="margin-top:8px;"><a href="https://christiancurator.com" style="color:#2C4A2E;">christiancurator.com</a></p>
      <p style="margin-top:12px;">
        <a href="https://christiancurator.com/#cc-email-box" style="display:inline-block; background:#2C4A2E; color:#fff; font-size:12px; font-weight:700; padding:7px 18px; border-radius:3px; text-decoration:none;">Subscribe to the Daily Digest</a>
      </p>
    </div>

  </div>
</body>
</html>"""


def save_email_html(html_content: str) -> str:
    """Save the email HTML to docs/email_draft.html and return the path."""
    docs_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    path = os.path.join(docs_dir, "email_draft.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return os.path.abspath(path)


def send_email(articles: list[dict], yesterday_articles: list[dict]) -> bool:
    """Build the daily digest and send via Brevo API."""
    if isinstance(articles, dict):
        articles = articles.get("articles", [])

    today = date.today().strftime("%B %-d, %Y")
    subject = f"Christian Curator — {today}"
    html_content = build_email_html(articles, yesterday_articles)

    # Always save locally as a backup
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

    # Step 1: Create the campaign
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

    # Step 2: Send it immediately
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
