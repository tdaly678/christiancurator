"""
email_sender.py: builds and sends the daily email via Brevo API.

Email structure follows homepage v2 (frontend/layout.py, P1 Wave 2), trimmed
for the inbox:
  Preheader     (invisible inbox preview: first Pulse sentence, else two subleads)
  Top bar       (date · Forwarded? Subscribe)
  Masthead      (Christian Curator wordmark + tagline)
  The Lead      (lead story + three subleads, by importance)
  Daily Pulse   (plain lead + subleads fallback when the Claude summary failed)
  The Debate    (Claude point/counterpoint pairs only, omitted when none)
  Board         (News / Commentary & Debate / Church & Theology, 3 each)
  CTA box       (see all of today's headlines on the site)
  Worth Your Time (depth lane, 3 picks)
  Watch and Listen (2 picks: a video and a podcast when both exist)
  Go Deeper (rotating topic spotlight), forward nudge, footer

Every headline links straight to the article URL. Links to christiancurator.com
carry UTM parameters (utm_content = section); publisher links stay clean.
"""

import html
import os
import json
import re
import requests
from datetime import date, timedelta
from urllib.parse import urlsplit, urlunsplit
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

SITE_URL = "https://www.christiancurator.com"


def _site_link(url: str, section: str) -> str:
    """Add email UTM parameters to a christiancurator.com URL.

    Publisher URLs are returned unchanged: Brevo's click tracking covers
    those, and their owners should see a clean link.
    """
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host not in ("christiancurator.com", "www.christiancurator.com"):
        return url
    utm = (f"utm_source=cc_email&utm_medium=email"
           f"&utm_campaign=daily_{date.today().isoformat()}&utm_content={section}")
    query = f"{parts.query}&{utm}" if parts.query else utm
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


def _tag_site_hrefs(fragment: str, section: str) -> str:
    """Apply _site_link() to every href inside a block of HTML (Pulse paragraphs)."""
    def _tag(m):
        url = html.unescape(m.group(1))
        tagged = _site_link(url, section)
        return m.group(0) if tagged == url else f'href="{tagged}"'
    return re.sub(r'href="([^"]+)"', _tag, fragment)


def _article_link(url: str) -> str:
    """Link straight to the article.

    Emails used to link to homepage anchors (/#a<hash>), but the next morning's
    re-render removes those anchors, so late or forwarded opens landed on a
    different day's page. If an article has no URL, fall back to today's
    dated archive page, which never changes.
    """
    if url:
        return url
    return _site_link(f"{SITE_URL}/archive/{date.today().isoformat()}/", "archive")


def _clip(text: str, limit: int) -> str:
    """Collapse whitespace and cut to `limit` characters on a word boundary."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"


SUBJECT_MAX = 60    # mobile inboxes show about 40 to 60 characters
PREHEADER_MAX = 90


def build_subject(lead_title: str) -> str:
    """The lead headline alone, cut to 60 characters on a word boundary.

    No story count: it used mobile characters and signalled volume, not value.
    """
    lead = _clip(lead_title, SUBJECT_MAX)
    if not lead:
        return f"Christian Curator · {date.today().strftime('%B %-d, %Y')}"
    return lead


def build_preheader(layout: dict, daily_summary: dict | None) -> str:
    """Inbox preview line (plain text). The subject already shows the lead,
    so this is the first Pulse sentence, else 'Also: {sublead 1} | {sublead 2}'.
    """
    from frontend.layout import pulse_line
    if daily_summary and not daily_summary.get("fallback"):
        sentence = pulse_line(daily_summary, max_words=200)
        if sentence:
            return _clip(sentence, PREHEADER_MAX)
    subs = [_clip(a.get("rewritten_title") or a.get("title") or "", 60)
            for a in layout.get("subleads", [])[:2]]
    subs = [t for t in subs if t]
    return f"Also: {' | '.join(subs)}" if subs else ""


def fallback_pulse(layout: dict) -> dict | None:
    """A plain Pulse built from the lead block, for days the Claude summary
    failed, so the email never opens straight into headlines."""
    lead = layout.get("lead")
    if not lead:
        return None
    def _t(a):
        return html.escape(a.get("rewritten_title") or a.get("title") or "", quote=False)
    text = f"Today&rsquo;s lead: {_t(lead)}"
    if lead.get("source_name"):
        text += f" ({html.escape(lead['source_name'], quote=False)})"
    text += "."
    subs = [_t(a) for a in layout.get("subleads", [])[:2] if _t(a)]
    if subs:
        text += f" Also leading: {' and '.join(subs)}."
    return {"paragraphs_html": [text], "fallback": True}


# Email-only caps; the homepage layout keeps its own sizes.
EMAIL_BOARD_PER_COLUMN = 3  # headlines per board section
EMAIL_WYT_MAX          = 3  # Worth Your Time picks
EMAIL_WATCH_LISTEN_MAX = 2  # Watch and Listen picks


def _email_watch_listen(picks: list[dict]) -> list[dict]:
    """First pick, plus the first pick of the other format when there is one."""
    if len(picks) <= EMAIL_WATCH_LISTEN_MAX:
        return picks
    first = picks[0]
    other = next((a for a in picks[1:] if a.get("media_format") != first.get("media_format")),
                 picks[1])
    return [first, other]


def _email_debate(debates: list[dict]) -> list[dict]:
    """Only Claude point/counterpoint pairs (validated in build_homepage_layout),
    and only with both theses when the pairing recorded them. The scorer's
    Pro/Con fallback is fine on the page but costs trust in an inbox."""
    keep = []
    for d in debates:
        if d.get("kind") != "claude":
            continue
        if ("thesis_a" in d or "thesis_b" in d) and not (
                (d.get("thesis_a") or "").strip() and (d.get("thesis_b") or "").strip()):
            continue
        keep.append(d)
    return keep


def _email_layout(articles: list[dict], research_articles: list[dict] = None,
                  layout: dict = None) -> dict:
    """The homepage v2 layout, trimmed for email.

    main.py passes the layout render_html() returned so the email matches the
    page exactly; send_email.py (cached run) rebuilds it from the cached
    pairings and media items in output/articles.json.
    """
    if layout is None:
        from frontend.layout import build_homepage_layout
        layout = build_homepage_layout(articles, None, research_articles)
    return {
        **layout,
        "board": [{**col, "articles": col["articles"][:EMAIL_BOARD_PER_COLUMN]}
                  for col in layout.get("board", [])],
        "debate": _email_debate(layout.get("debate") or []),
        "worth_your_time": (layout.get("worth_your_time") or [])[:EMAIL_WYT_MAX],
        "watch_listen": _email_watch_listen(layout.get("watch_listen") or []),
    }


# ── Section renderers ──────────────────────────────────────────────────────────

_LABEL_STYLE = ("font-size:9px;font-weight:700;text-transform:uppercase;"
                "letter-spacing:0.18em;color:#888;border-bottom:2.5px solid #1a1a1a;"
                "padding-bottom:8px;margin-bottom:0;")


def _byline(a: dict, show_author: bool = True) -> str:
    author = (a.get("author") or "").strip()
    source = (a.get("source_name") or "").strip()
    if show_author and author and author.lower() != source.lower():
        return f"{author} &nbsp;·&nbsp; {source}"
    return source


def _headline_row(a: dict, size: int, last: bool, show_author: bool = True) -> str:
    title  = a.get("rewritten_title") or a.get("title") or ""
    href   = _article_link(a.get("url") or "")
    border = "" if last else "border-bottom:1px solid #eceae6;"
    pad    = 14 if size >= 16 else 9
    return f"""
      <div style="padding:{pad}px 0;{border}">
        <a href="{href}" target="_blank"
           style="font-family:Georgia,'Times New Roman',serif;font-size:{size}px;
                  font-weight:600;line-height:1.35;color:#1a1a1a;text-decoration:none;
                  display:block;margin-bottom:3px;">
          {title}
        </a>
        <div style="font-size:10.5px;color:#aaa;letter-spacing:0.03em;font-variant:small-caps;">{_byline(a, show_author)}</div>
      </div>"""


def _render_lead(layout: dict) -> str:
    """Lead story large, then the three subleads."""
    lead = layout.get("lead")
    if not lead:
        return ""
    title = lead.get("rewritten_title") or lead.get("title") or ""
    href  = _article_link(lead.get("url") or "")
    subs  = layout.get("subleads", [])
    rows  = "".join(_headline_row(a, 16, last=(i == len(subs) - 1)) for i, a in enumerate(subs))
    return f"""
    <div style="padding:24px 28px 0;">
      <div style="{_LABEL_STYLE}">The Lead</div>
      <div style="padding:16px 0 12px;border-bottom:1px solid #d8d4cd;">
        <a href="{href}" target="_blank"
           style="font-family:Georgia,'Times New Roman',serif;font-size:24px;
                  font-weight:600;line-height:1.2;color:#1a1a1a;text-decoration:none;
                  display:block;margin-bottom:6px;">
          {title}
        </a>
        <div style="font-size:11px;color:#999;letter-spacing:0.03em;font-variant:small-caps;">{_byline(lead)}</div>
      </div>
      {rows}
    </div>"""


def _render_board(layout: dict) -> str:
    """The three board columns, stacked: News, Commentary & Debate, Church & Theology."""
    sections = ""
    for col in layout.get("board", []):
        arts = col["articles"]
        if not arts:
            continue
        rows = "".join(_headline_row(a, 14, last=(i == len(arts) - 1), show_author=False)
                       for i, a in enumerate(arts))
        sections += f"""
    <div style="padding:24px 28px 0;">
      <div style="{_LABEL_STYLE}">{col['label'].replace('&', '&amp;')}</div>
      {rows}
    </div>"""
    return sections


def _render_debate(layout: dict) -> str:
    """Point / counterpoint pairs, side by side; omitted when nothing pairs."""
    debates = layout.get("debate") or []
    if not debates:
        return ""

    def _cell(a: dict, label: str, color: str) -> str:
        title = a.get("rewritten_title") or a.get("title") or ""
        return f"""
          <td width="50%" valign="top" style="padding:10px 12px;background:#fff;border:1px solid #e0ddd8;border-top:3px solid {color};">
            <div style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.14em;color:{color};margin-bottom:4px;">{label}</div>
            <a href="{_article_link(a.get('url') or '')}" target="_blank"
               style="font-family:Georgia,'Times New Roman',serif;font-size:14px;font-weight:600;
                      line-height:1.35;color:#1a1a1a;text-decoration:none;display:block;margin-bottom:3px;">{title}</a>
            <div style="font-size:10.5px;color:#aaa;font-variant:small-caps;">{_byline(a, False)}</div>
          </td>"""

    pairs = ""
    for d in debates:
        topic = f'<div style="font-family:Georgia,serif;font-style:italic;font-size:14px;color:#555;margin:14px 0 6px;">{d["topic"]}</div>' if d.get("topic") else '<div style="height:14px;"></div>'
        pairs += f"""
      {topic}
      <table width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;border-spacing:6px 0;">
        <tr>{_cell(d['a'], d['label_a'], '#2C4A2E')}{_cell(d['b'], d['label_b'], '#8B4513')}</tr>
      </table>"""
    return f"""
    <div style="padding:24px 28px 0;">
      <div style="{_LABEL_STYLE}color:#8B1A1A;border-bottom-color:#8B1A1A;">The Debate</div>
      {pairs}
    </div>"""


def _render_worth_your_time(layout: dict) -> str:
    """Depth lane: slower formative reads."""
    picks = layout.get("worth_your_time") or []
    if not picks:
        return ""
    rows = "".join(_headline_row(a, 15, last=(i == len(picks) - 1)) for i, a in enumerate(picks))
    return f"""
    <div style="padding:24px 28px 0;">
      <div style="{_LABEL_STYLE}">Worth Your Time</div>
      {rows}
    </div>"""


def _render_watch_listen(layout: dict) -> str:
    """Media lane: a few videos and podcast episodes, format and length up front."""
    picks = layout.get("watch_listen") or []
    if not picks:
        return ""
    rows = []
    for i, a in enumerate(picks):
        fmt = "Video" if a.get("media_format") == "video" else "Podcast"
        if a.get("duration_display"):
            fmt += f" &nbsp;·&nbsp; {a['duration_display']}"
        border = "" if i == len(picks) - 1 else "border-bottom:1px solid #eceae6;"
        rows.append(f"""
      <div style="padding:9px 0;{border}">
        <div style="font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:0.14em;
                    color:#2C4A2E;margin-bottom:3px;">{fmt}</div>
        <a href="{_article_link(a.get("url") or "")}" target="_blank"
           style="font-family:Georgia,'Times New Roman',serif;font-size:15px;
                  font-weight:600;line-height:1.35;color:#1a1a1a;text-decoration:none;
                  display:block;margin-bottom:3px;">
          {html.escape(a.get("title") or "", quote=False)}
        </a>
        <div style="font-size:10.5px;color:#aaa;letter-spacing:0.03em;font-variant:small-caps;">{_byline(a, False)}</div>
      </div>""")
    return f"""
    <div style="padding:24px 28px 0;">
      <div style="{_LABEL_STYLE}">Watch and Listen</div>
      {"".join(rows)}
    </div>"""


def _render_pulse(daily_summary: dict | None) -> str:
    """The Daily Pulse paragraphs, or "" when the summary is missing/empty."""
    if not daily_summary:
        return ""
    paragraphs = [p for p in (daily_summary.get("paragraphs_html") or []) if p and p.strip()]
    if not paragraphs:
        return ""
    slug = daily_summary.get("slug") or date.today().isoformat()
    body = "".join(
        f'<p style="margin:0 0 12px;font-family:Georgia,\'Times New Roman\',serif;'
        f'font-size:15px;line-height:1.6;color:#333;">{_tag_site_hrefs(p, "pulse")}</p>'
        for p in paragraphs
    )
    # The fallback Pulse has no /daily/ page behind it.
    more = "" if daily_summary.get("fallback") else f"""
      <a href="{_site_link(f"{SITE_URL}/daily/{slug}/", "pulse")}"
         style="font-size:12px;color:#2C4A2E;font-weight:700;text-decoration:none;">
        Read today&rsquo;s Pulse on the site &rarr;
      </a>"""
    return f"""
    <div style="padding:24px 28px 0;">
      <div style="font-size:9px;font-weight:700;text-transform:uppercase;
                  letter-spacing:0.18em;color:#888;border-bottom:2.5px solid #1a1a1a;
                  padding-bottom:8px;margin-bottom:14px;">
        The Daily Pulse
      </div>
      {body}{more}
    </div>"""


def _render_cta() -> str:
    """Primary CTA, right below the board: the email shows a few headlines per
    section, the front page has the rest."""
    return f"""
    <div style="padding:24px 28px 0;">
      <div style="background:#f3f1ed;border:1px solid #e0ddd8;border-radius:6px;
                  padding:22px 20px;text-align:center;">
        <div style="font-size:12px;color:#888;margin-bottom:6px;letter-spacing:0.04em;
                    text-transform:uppercase;font-weight:600;">
          The email has the top few
        </div>
        <div style="font-family:Georgia,'Times New Roman',serif;font-size:18px;
                    font-weight:600;color:#1a1a1a;line-height:1.3;margin-bottom:18px;">
          Theology &nbsp;·&nbsp; Church Life &nbsp;·&nbsp; Culture &nbsp;·&nbsp; World News
        </div>
        <a href="{_site_link(f"{SITE_URL}/", "cta")}"
           style="display:inline-block;background:#2C4A2E;color:#fff;
                  font-size:14px;font-weight:700;padding:13px 32px;
                  border-radius:4px;text-decoration:none;letter-spacing:0.03em;">
          See all of today&rsquo;s headlines on the front page &rarr;
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
    url      = _site_link(f"{SITE_URL}/topics/{slug}/", "go_deeper")

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
                     daily_summary: dict = None, research_articles: list[dict] = None,
                     layout: dict = None) -> str:

    if isinstance(articles, dict):
        articles = articles.get("articles", [])

    today_long = date.today().strftime("%A, %B %-d, %Y")

    spotlight_topic  = _get_spotlight_topic()

    # Same picks as the homepage (frontend/layout.py), trimmed for email.
    layout = _email_layout(articles, research_articles, layout)

    preheader = html.escape(build_preheader(layout, daily_summary), quote=False)

    # Never open straight into headlines: if the Claude Pulse is missing,
    # use the plain lead + subleads version.
    if not _render_pulse(daily_summary):
        daily_summary = fallback_pulse(layout)

    lead_html           = _render_lead(layout)
    pulse_html          = _render_pulse(daily_summary)
    board_html          = _render_board(layout)
    debate_html         = _render_debate(layout)
    wyt_html            = _render_worth_your_time(layout)
    watch_listen_html   = _render_watch_listen(layout)
    cta_html            = _render_cta()
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
        <a href="{_site_link(f"{SITE_URL}/#cc-email-box", "subscribe")}"
           style="background:#2C4A2E;color:#fff;font-size:11px;font-weight:700;
                  padding:4px 12px;border-radius:3px;text-decoration:none;
                  display:inline-block;letter-spacing:0.04em;">
          Subscribe Free
        </a>
      </div>
    </div>

    <div style="text-align:center;padding:8px 28px 18px;border-bottom:2.5px solid #1a1a1a;margin:0 28px;">
      <a href="{_site_link(f"{SITE_URL}/", "masthead")}" style="text-decoration:none;">
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

    {lead_html}
    {pulse_html}
    {debate_html}
    {board_html}
    {cta_html}
    {wyt_html}
    {watch_listen_html}
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
            <a href="{_site_link(f"{SITE_URL}/", "footer")}"
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
               daily_summary: dict = None, research_articles: list[dict] = None,
               layout: dict = None) -> bool:

    if isinstance(articles, dict):
        articles = articles.get("articles", [])

    today        = date.today().strftime("%B %-d, %Y")
    email_layout = _email_layout(articles, research_articles, layout)
    lead_article = email_layout.get("lead") or {}
    lead         = lead_article.get("rewritten_title") or lead_article.get("title", "")
    subject      = build_subject(lead)
    html_content = build_email_html(articles, yesterday_articles,
                                    daily_summary=daily_summary,
                                    research_articles=research_articles,
                                    layout=layout)
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
