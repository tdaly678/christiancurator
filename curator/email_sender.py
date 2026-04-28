"""
email_sender.py — builds and sends the daily digest email via Brevo API.

Email structure:
  Preheader     (invisible inbox preview — first 3 headline titles)
  Top bar       (date · Forwarded? Subscribe)
  Masthead      (Christian Curator wordmark + tagline)
  Top Stories   (5 highest-scored non-world-news headlines — title + source)
  More Headlines(remaining ~15 non-world-news + ~3 world-news — compact list)
  CTA box       (Visit today's digest → christiancurator.com)
  Go Deeper     (rotating topic spotlight — cycles through all topics)
  Forward nudge
  Footer

Every headline links to https://www.christiancurator.com/#<article_anchor>
where <article_anchor> = "a" + md5(article.url)[:8] — the same anchor id
the homepage template.html applies to its article cards, so a click on an
email headline lands at that exact article on the live site.
"""

import hashlib
import os
import json
import requests
from datetime import date, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY        = os.environ.get("BREVO_API_KEY", "")
BREVO_LIST_ID        = 2
BREVO_SENDER_EMAIL   = os.environ.get("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME    = "Christian Curator"
BREVO_API_URL        = "https://api.brevo.com/v3/emailCampaigns"

DOCS_DIR           = Path(__file__).parent.parent / "docs"
SPOTLIGHT_LOG_PATH = DOCS_DIR / "spotlight_topic_log.json"


# ── Spotlight topic rotation ───────────────────────────────────────────────────

def _load_spotlight_log() -> dict:
    if SPOTLIGHT_LOG_PATH.exists():
        try:
            return json.loads(SPOTLIGHT_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_spotlight_log(data: dict):
    SPOTLIGHT_LOG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _get_spotlight_topic() -> dict | None:
    """
    Return the next topic to spotlight, cycling through all topics without
    repeating until every topic has been shown. Records today's pick in
    spotlight_topic_log.json.
    """
    try:
        from frontend.topics_data import TOPICS
    except ImportError:
        return None

    today_iso = date.today().isoformat()
    log = _load_spotlight_log()

    # Already picked today — return same topic
    if today_iso in log:
        slug = log[today_iso]
        return next((t for t in TOPICS if t["slug"] == slug), None)

    # Find slugs already used in last 70 days so the cycle can reset naturally
    cutoff = (date.today() - timedelta(days=70)).isoformat()
    recent_slugs = {v for k, v in log.items() if k >= cutoff}

    # Pick first topic not recently spotlighted; fall back to full list if all used
    candidates = [t for t in TOPICS if t["slug"] not in recent_slugs] or list(TOPICS)
    chosen = candidates[0]

    log[today_iso] = chosen["slug"]
    # Prune log to last 90 days
    log = {k: v for k, v in log.items()
           if k >= (date.today() - timedelta(days=90)).isoformat()}
    _save_spotlight_log(log)
    return chosen


# ── Helpers ────────────────────────────────────────────────────────────────────

def _article_anchor_url(url: str) -> str:
    """Return the homepage URL anchored to this article — matches the id
    applied in frontend/template.html via the `article_anchor` Jinja filter."""
    if not url:
        return "https://www.christiancurator.com/"
    anchor = "a" + hashlib.md5(url.encode()).hexdigest()[:8]
    return f"https://www.christiancurator.com/#{anchor}"


def _split_homepage_articles(articles: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Return (top5, remaining, world_news_top3) using the *same* diversified
    selection the homepage uses, so every headline in the email has a matching
    anchor id on christiancurator.com.

    - top5: first 5 of the diversified front-page cards (10 total)
    - remaining: the other 5 front-page cards + up to 10 'other_headlines' (~15)
    - world_news_top3: top 3 world-news articles by score
    """
    try:
        # Reuse the homepage's own diversification helpers so anchors line up.
        from frontend import _build_diversified_cards, _build_diversified_headlines
        from frontend.topics_data import TOPICS_BY_SLUG
    except ImportError:
        # Fallback: simple top-by-score split if frontend isn't importable.
        non_world = sorted(
            [a for a in articles if a.get("source_type") != "world_news"],
            key=lambda a: a.get("final_score", a.get("score", 0)),
            reverse=True,
        )
        world = sorted(
            [a for a in articles if a.get("source_type") == "world_news"],
            key=lambda a: a.get("final_score", a.get("score", 0)),
            reverse=True,
        )[:3]
        return non_world[:5], non_world[5:20], world

    front_page_cards = _build_diversified_cards(
        articles, TOPICS_BY_SLUG, max_per_topic=2, total=10
    )
    front_page_articles = [c["article"] for c in front_page_cards]
    front_page_urls = {a.get("url", "") for a in front_page_articles}

    other_headlines = _build_diversified_headlines(
        articles, TOPICS_BY_SLUG, front_page_urls, max_per_topic=2, total=10
    )

    world_news = sorted(
        [a for a in articles if a.get("source_type") == "world_news"],
        key=lambda a: a.get("final_score", a.get("score", 0)),
        reverse=True,
    )[:3]

    top5 = front_page_articles[:5]
    remaining = front_page_articles[5:] + other_headlines  # up to 15 items
    return top5, remaining, world_news


# ── Section renderers ──────────────────────────────────────────────────────────

def _render_top_stories(top5: list[dict]) -> str:
    """5 lead headlines — larger style, title + byline + source."""
    if not top5:
        return ""

    rows = ""
    for i, a in enumerate(top5):
        title  = a.get("rewritten_title") or a.get("title") or ""
        author = (a.get("author") or "").strip()
        source = (a.get("source_name") or "").strip()
        url    = a.get("url") or ""
        byline = (
            f"{author} &nbsp;·&nbsp; {source}"
            if author and author.lower() != source.lower()
            else source
        )
        href   = _article_anchor_url(url)
        border = "" if i == len(top5) - 1 else "border-bottom:1px solid #eceae6;"

        rows += f"""
      <div style="padding:14px 0;{border}">
        <a href="{href}"
           style="font-family:Georgia,'Times New Roman',serif;font-size:16px;
                  font-weight:600;line-height:1.35;color:#1a1a1a;text-decoration:none;
                  display:block;margin-bottom:5px;">
          {title}
        </a>
        <div style="font-size:11px;color:#aaa;letter-spacing:0.01em;">{byline}</div>
      </div>"""

    return f"""
    <div style="padding:24px 28px 0;">
      <div style="font-size:9px;font-weight:700;text-transform:uppercase;
                  letter-spacing:0.18em;color:#888;border-bottom:2.5px solid #1a1a1a;
                  padding-bottom:8px;margin-bottom:0;">
        Today&rsquo;s Top Stories
      </div>
      {rows}
    </div>"""


def _render_more_headlines(remaining: list[dict], world_news: list[dict]) -> str:
    """Compact list of all remaining homepage headlines, plus world news.

    Every entry links to the homepage anchor so the click lands at the
    article's spot on christiancurator.com (just like the top stories do).
    """
    if not remaining and not world_news:
        return ""

    def _row(a: dict, last: bool) -> str:
        title  = a.get("rewritten_title") or a.get("title") or ""
        source = (a.get("source_name") or "").strip()
        url    = a.get("url") or ""
        href   = _article_anchor_url(url)
        border = "" if last else "border-bottom:1px solid #eceae6;"
        return f"""
      <div style="padding:10px 0;{border}">
        <a href="{href}"
           style="font-family:Georgia,'Times New Roman',serif;font-size:14px;
                  font-weight:600;line-height:1.35;color:#1a1a1a;text-decoration:none;
                  display:block;margin-bottom:3px;">
          {title}
        </a>
        <div style="font-size:10.5px;color:#aaa;letter-spacing:0.01em;">{source}</div>
      </div>"""

    main_rows = ""
    if remaining:
        for i, a in enumerate(remaining):
            last = (i == len(remaining) - 1) and not world_news
            main_rows += _row(a, last)

    world_section = ""
    if world_news:
        world_rows = ""
        for i, a in enumerate(world_news):
            world_rows += _row(a, last=(i == len(world_news) - 1))
        world_section = f"""
      <div style="margin-top:18px;padding-top:14px;border-top:1px solid #d8d4cd;">
        <div style="font-size:9px;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.18em;color:#888;margin-bottom:4px;">
          World News &amp; Culture
        </div>
        {world_rows}
      </div>"""

    return f"""
    <div style="padding:24px 28px 0;">
      <div style="font-size:9px;font-weight:700;text-transform:uppercase;
                  letter-spacing:0.18em;color:#888;border-bottom:2.5px solid #1a1a1a;
                  padding-bottom:8px;margin-bottom:0;">
        More Headlines
      </div>
      {main_rows}
      {world_section}
    </div>"""


def _render_cta(non_world_count: int) -> str:
    """CTA box — invites readers to the live site for full context + commentary."""
    return f"""
    <div style="padding:24px 28px 0;">
      <div style="background:#f3f1ed;border:1px solid #e0ddd8;border-radius:6px;
                  padding:22px 20px;text-align:center;">
        <div style="font-size:12px;color:#888;margin-bottom:6px;letter-spacing:0.04em;
                    text-transform:uppercase;font-weight:600;">
          Read on the site for full context
        </div>
        <div style="font-family:Georgia,'Times New Roman',serif;font-size:18px;
                    font-weight:600;color:#1a1a1a;line-height:1.3;margin-bottom:18px;">
          Theology &nbsp;·&nbsp; Church Life &nbsp;·&nbsp; Culture &nbsp;·&nbsp; World News
        </div>
        <a href="https://www.christiancurator.com/"
           style="display:inline-block;background:#2C4A2E;color:#fff;
                  font-size:14px;font-weight:700;padding:13px 32px;
                  border-radius:4px;text-decoration:none;letter-spacing:0.03em;">
          Read today&rsquo;s digest &rarr;
        </a>
      </div>
    </div>"""


def _render_go_deeper(topic: dict) -> str:
    """Rotating topic spotlight card."""
    if not topic:
        return ""

    name     = topic.get("name", "")
    slug     = topic.get("slug", "")
    category = topic.get("category", "")
    question = topic.get("hook", "")
    summary  = topic.get("summary") or topic.get("hook", "")
    url      = f"https://www.christiancurator.com/topics/{slug}/"

    return f"""
    <div style="padding:28px 28px 0;">
      <div style="border:1px solid #e0ddd8;border-radius:6px;overflow:hidden;">

        <div style="background:#2C4A2E;padding:10px 18px;">
          <div style="font-size:9px;font-weight:700;text-transform:uppercase;
                      letter-spacing:0.2em;color:#b5ccb8;">
            Go Deeper &nbsp;·&nbsp; Topic Spotlight
          </div>
        </div>

        <div style="padding:18px 18px 20px;background:#faf9f7;">
          <div style="font-size:9.5px;font-weight:700;text-transform:uppercase;
                      letter-spacing:0.14em;color:#2C4A2E;margin-bottom:7px;">
            {category}
          </div>
          <div style="font-family:Georgia,'Times New Roman',serif;font-size:21px;
                      font-weight:600;line-height:1.2;color:#1a1a1a;margin-bottom:10px;">
            {name}
          </div>
          <div style="font-size:13.5px;color:#555;font-style:italic;line-height:1.65;
                      border-left:2px solid #b5ccb8;padding-left:12px;margin-bottom:16px;">
            {question}
          </div>
          <div style="font-size:13px;color:#444;line-height:1.65;margin-bottom:18px;">
            {summary}
          </div>
          <a href="{url}"
             style="display:inline-block;background:#faf9f7;color:#2C4A2E;
                    font-size:12.5px;font-weight:700;padding:9px 20px;
                    border-radius:4px;text-decoration:none;letter-spacing:0.02em;
                    border:1.5px solid #2C4A2E;">
            Explore this topic &rarr;
          </a>
        </div>

      </div>
    </div>"""


# ── Main builder ───────────────────────────────────────────────────────────────

def build_email_html(articles: list[dict], yesterday_articles: list[dict] = None,
                     daily_summary: dict = None, research_articles: list[dict] = None) -> str:

    if isinstance(articles, dict):
        articles = articles.get("articles", [])

    today_long = date.today().strftime("%A, %B %-d, %Y")

    non_world_count  = len([a for a in articles if a.get("source_type") != "world_news"])
    spotlight_topic  = _get_spotlight_topic()

    # Mirror the homepage's diversification so every headline below has a
    # matching anchor id on christiancurator.com.
    top5, remaining, world_news = _split_homepage_articles(articles)

    # Preheader: first 3 headline titles from the top stories shown above
    top_titles = [
        a.get("rewritten_title") or a.get("title", "")
        for a in top5[:3]
    ]
    preheader = " &nbsp;·&nbsp; ".join(t for t in top_titles if t)
    if preheader:
        preheader += " &nbsp;·&nbsp; and more."

    top_stories_html    = _render_top_stories(top5)
    more_headlines_html = _render_more_headlines(remaining, world_news)
    cta_html            = _render_cta(non_world_count)
    go_deeper_html      = _render_go_deeper(spotlight_topic)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#e8e5e0;font-family:'Helvetica Neue',Arial,sans-serif;color:#1a1a1a;">

  <div style="display:none;max-height:0;overflow:hidden;font-size:1px;color:#e8e5e0;">
    {preheader}&nbsp;&#8204;&nbsp;&#8204;&nbsp;&#8204;&nbsp;&#8204;&nbsp;&#8204;&nbsp;&#8204;&nbsp;&#8204;&nbsp;&#8204;
  </div>

  <div style="max-width:600px;margin:0 auto;background:#faf9f7;padding:0 0 40px;">

    <div style="padding:14px 28px 12px;display:table;width:100%;box-sizing:border-box;">
      <div style="display:table-cell;font-size:11px;color:#999;letter-spacing:0.05em;
                  vertical-align:middle;text-transform:uppercase;">
        {today_long}
      </div>
      <div style="display:table-cell;text-align:right;vertical-align:middle;">
        <span style="font-size:11px;color:#aaa;">Forwarded to you?&nbsp;</span>
        <a href="https://www.christiancurator.com/#cc-email-box"
           style="background:#2C4A2E;color:#fff;font-size:11px;font-weight:700;
                  padding:4px 12px;border-radius:3px;text-decoration:none;
                  display:inline-block;letter-spacing:0.04em;">
          Subscribe Free
        </a>
      </div>
    </div>

    <div style="text-align:center;padding:8px 28px 18px;border-bottom:2.5px solid #1a1a1a;margin:0 28px;">
      <a href="https://www.christiancurator.com/" style="text-decoration:none;">
        <div style="font-family:Georgia,'Times New Roman',serif;font-size:42px;font-weight:600;
                    letter-spacing:-0.02em;color:#1a1a1a;line-height:1;">
          Christian Curator
        </div>
      </a>
      <div style="font-size:10.5px;letter-spacing:0.2em;text-transform:uppercase;
                  color:#aaa;margin-top:9px;font-weight:400;">
        For curious Christians seeking clarity on the questions that matter most
      </div>
    </div>

    {top_stories_html}
    {more_headlines_html}
    {cta_html}
    {go_deeper_html}

    <div style="padding:20px 28px 0;text-align:center;">
      <div style="font-size:12px;color:#bbb;line-height:1.7;">
        Know a curious Christian who&rsquo;d enjoy this?&nbsp;
        <a href="mailto:?subject=Christian%20Curator%20%E2%80%94%20Daily%20Digest&body=Thought%20you%27d%20enjoy%20this%3A%20https%3A%2F%2Fwww.christiancurator.com%2F"
           style="color:#2C4A2E;font-weight:700;text-decoration:none;">
          Forward this email.
        </a>
      </div>
    </div>

    <div style="margin:24px 28px 0;padding-top:14px;border-top:2.5px solid #1a1a1a;">
      <table width="100%" cellpadding="0" cellspacing="0" border="0">
        <tr>
          <td style="font-family:Georgia,'Times New Roman',serif;font-size:14px;
                     font-weight:600;color:#1a1a1a;vertical-align:middle;">
            Christian Curator
          </td>
          <td style="text-align:right;vertical-align:middle;">
            <a href="https://www.christiancurator.com/"
               style="font-size:11px;color:#aaa;text-decoration:none;font-weight:600;
                      letter-spacing:0.04em;text-transform:uppercase;">
              Visit Site
            </a>
          </td>
        </tr>
      </table>
      <div style="font-size:11px;color:#ccc;margin-top:8px;line-height:1.6;">
        Curated from across the evangelical web.
      </div>
    </div>

  </div>
</body>
</html>"""


# ── File save ──────────────────────────────────────────────────────────────────

def save_email_html(html_content: str) -> str:
    path = DOCS_DIR / "email_draft.html"
    path.write_text(html_content, encoding="utf-8")
    return str(path.resolve())


# ── Send ───────────────────────────────────────────────────────────────────────

def send_email(articles: list[dict], yesterday_articles: list[dict] = None,
               daily_summary: dict = None, research_articles: list[dict] = None) -> bool:

    if isinstance(articles, dict):
        articles = articles.get("articles", [])

    today        = date.today().strftime("%B %-d, %Y")
    subject      = f"Christian Curator — {today}"
    html_content = build_email_html(articles, yesterday_articles,
                                    daily_summary=daily_summary,
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
