#!/usr/bin/env python3
"""build_topic_og.py: link preview cards and head tags for every topic page.

For each docs/topics/<slug>/index.html this script

1. renders a 1200 x 630 PNG preview card to docs/og/topics/<slug>-<hash>.png:
   the category, the page's question in Lora, then either the debate card's
   position names (in the card colors green, brown, blue) or, on pages with no
   debate card, a one-line deck; "christiancurator.com" small at the bottom.
   The file name carries a hash of the card's text and the renderer version,
   so when the text changes the URL changes and Meta, X and iMessage fetch the
   new image (they cache by URL). Older cards for the slug are deleted.
2. writes the preview tags in <head> between <!-- CC-OG:START/END -->:
   og:title (the <title> without the " — Christian Curator" suffix; og:site_name
   already names the site), og:description, og:image with width, height, type
   and alt, twitter:card summary_large_image, twitter:title, twitter:description,
   twitter:image and twitter:image:alt. The same tags found anywhere else in
   <head> are removed first, so each appears once. og:type, og:site_name and
   og:url stay where they are (they are added inside the block only when a page
   lacks them). Nothing else on the page is touched, including the
   CC-TOPIC-ASSETS block.

The card text lives in data/topic_og/cards.json (one entry per slug):
  question        the debate in plain words, no dashes, at most 70 characters
  positions       short names of the debate card's positions, in page order;
                  the count must match the page's id="position-N" cards
  deck            instead of positions, on pages with no debate card
  og_description  optional; otherwise the page's meta description is used

Usage:
  python scripts/build_topic_og.py               # render missing cards, write head tags
  python scripts/build_topic_og.py --slug baptism
  python scripts/build_topic_og.py --check       # validate; exit 1 on any problem or stale page
  python scripts/build_topic_og.py --dry-run     # report what would change, write nothing
  python scripts/build_topic_og.py --force       # re-render cards even when the file exists
  python scripts/build_topic_og.py --site-image  # also redraw docs/og-image.png (site default card)

Needs Pillow (pip install Pillow); it is not in requirements.txt because the
daily workflow never runs this script. --check needs Pillow only to confirm the
image files exist, which it does without it. Fonts: data/fonts (SIL OFL 1.1).
Rerun after editing cards.json, after a page's title, description or debate
positions change, or after changing the renderer (bump RENDER_VERSION).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DOCS = REPO_ROOT / "docs"
TOPICS_DIR = DOCS / "topics"
OG_DIR = DOCS / "og" / "topics"
SITE_IMAGE = DOCS / "og-image.png"
CARDS = REPO_ROOT / "data" / "topic_og" / "cards.json"
FONTS = REPO_ROOT / "data" / "fonts"
LORA = FONTS / "Lora-Variable.ttf"
SANS = FONTS / "SourceSans3-Variable.ttf"
SITE = "https://www.christiancurator.com"

OG_START = "<!-- CC-OG:START -->"
OG_END = "<!-- CC-OG:END -->"
RENDER_VERSION = "1"

WIDTH, HEIGHT = 1200, 630
MARGIN = 84
BG = "#faf9f7"
INK = "#1a1a1a"
GREEN = "#2C4A2E"
MUTED = "#6b6b6b"
RULE = "#d9d5ce"
SIDE_COLORS = ["#2C4A2E", "#8B4513", "#4A4A8B", "#8B1A1A"]

MAX_QUESTION = 70
MAX_POSITION = 48
MAX_DECK = 90
MAX_DESCRIPTION = 200
TITLE_SUFFIX_RE = re.compile(r"\s*(?:[—–|-])\s*Christian Curator\s*$")
DASH_RE = re.compile("[–—]")
TRACKING_RE = re.compile(r"[?&](?:utm_[a-z]+|fbclid|gclid|mc_eid|ref)=", re.I)
POSITION_ID_RE = re.compile(r'\bid="position-(\d)"')
MANAGED = (
    r"og:title|og:description|og:image(?::(?:width|height|type|alt|secure_url))?"
    r"|twitter:(?:card|title|description|image(?::alt)?)"
)
MANAGED_TAG_RE = re.compile(
    r'[ \t]*<meta\b[^>]*\b(?:property|name)="(?:' + MANAGED + r')"[^>]*>[ \t]*\n?')
BLOCK_RE = re.compile(re.escape(OG_START) + r".*?" + re.escape(OG_END) + r"\n?", re.DOTALL)


# ---------------------------------------------------------------- page reading

def meta_content(page_html: str, attr: str, key: str) -> str | None:
    for tag in re.findall(r"<meta\b[^>]*>", page_html):
        if re.search(rf'\b{attr}="{re.escape(key)}"', tag):
            m = re.search(r'\bcontent="([^"]*)"', tag)
            if m:
                return html.unescape(m.group(1))
    return None


def page_title(page_html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", page_html, re.DOTALL)
    title = html.unescape(m.group(1)).strip() if m else ""
    return TITLE_SUFFIX_RE.sub("", title).strip()


def page_canonical(page_html: str, slug: str) -> str:
    m = re.search(r'<link\b[^>]*href="([^"]+)"[^>]*rel="canonical"', page_html) or \
        re.search(r'<link\b[^>]*rel="canonical"[^>]*href="([^"]+)"', page_html)
    return m.group(1) if m else f"{SITE}/topics/{slug}/"


def position_count(page_html: str) -> int:
    return len(set(POSITION_ID_RE.findall(page_html)))


def head_split(page_html: str) -> tuple[str, str]:
    i = page_html.find("</head>")
    if i < 0:
        raise ValueError("page has no </head>")
    return page_html[:i], page_html[i:]


# ---------------------------------------------------------------- card data

def load_cards(path: Path = CARDS) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["cards"]


def topic_slugs() -> list[str]:
    return sorted(p.parent.name for p in TOPICS_DIR.glob("*/index.html"))


def topic_category(slug: str) -> str:
    try:
        from frontend.topics_data import TOPICS
    except Exception:  # pragma: no cover - only when run outside the repo
        return ""
    for t in TOPICS:
        if t["slug"] == slug:
            return t.get("category", "")
    return ""


def og_description(card: dict, page_html: str) -> str:
    return (card.get("og_description") or meta_content(page_html, "name", "description") or "").strip()


def validate(slug: str, card: dict | None, page_html: str) -> list[str]:
    """Problems with one page's card text; empty when it can be built."""
    if card is None:
        return [f"{slug}: no entry in {CARDS.relative_to(REPO_ROOT)}"]
    errs = []
    q = card.get("question", "")
    positions = card.get("positions") or []
    deck = card.get("deck", "")
    if not q:
        errs.append(f"{slug}: question is empty")
    if len(q) > MAX_QUESTION:
        errs.append(f"{slug}: question is {len(q)} characters (max {MAX_QUESTION})")
    n = position_count(page_html)
    if n:
        if len(positions) != n:
            errs.append(f"{slug}: page has {n} debate positions, card lists {len(positions)}")
    elif not deck:
        errs.append(f"{slug}: page has no debate card, so the card needs a deck")
    if positions and deck:
        errs.append(f"{slug}: use positions or deck, not both")
    for p in positions:
        if len(p) > MAX_POSITION:
            errs.append(f"{slug}: position {p!r} is over {MAX_POSITION} characters")
    if len(deck) > MAX_DECK:
        errs.append(f"{slug}: deck is over {MAX_DECK} characters")
    desc = og_description(card, page_html)
    if not desc:
        errs.append(f"{slug}: no og:description (no meta description and no override)")
    if len(desc) > MAX_DESCRIPTION:
        errs.append(f"{slug}: og:description is {len(desc)} characters (max {MAX_DESCRIPTION})")
    if not page_title(page_html):
        errs.append(f"{slug}: page has no <title>")
    for label, text in [("question", q), ("deck", deck), ("og:description", desc),
                        ("og:title", page_title(page_html))] + [("position", p) for p in positions]:
        if DASH_RE.search(text) or " - " in text:
            errs.append(f"{slug}: {label} contains a dash: {text!r}")
        if TRACKING_RE.search(text):
            errs.append(f"{slug}: {label} contains a tracking parameter")
    return errs


# ---------------------------------------------------------------- image

def card_hash(slug: str, card: dict, category: str) -> str:
    payload = json.dumps({"v": RENDER_VERSION, "slug": slug, "category": category,
                          "question": card.get("question", ""),
                          "positions": card.get("positions") or [],
                          "deck": card.get("deck", "")}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def image_name(slug: str, card: dict, category: str) -> str:
    return f"{slug}-{card_hash(slug, card, category)}.png"


def _font(path: Path, size: int, weight: int):
    from PIL import ImageFont
    font = ImageFont.truetype(str(path), size)
    try:
        font.set_variation_by_axes([weight])
    except Exception:  # static font or no variation support: keep the default instance
        pass
    return font


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if not line or draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _spaced(draw, xy, text, font, fill, spacing):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + spacing


def render_card(question: str, *, category: str = "", positions: list[str] | None = None,
                deck: str = ""):
    """The preview card as a PIL image."""
    from PIL import Image, ImageDraw
    positions = positions or []
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)
    inner = WIDTH - 2 * MARGIN
    d.rectangle([0, 0, WIDTH, 10], fill=GREEN)

    kicker = _font(SANS, 24, 600)
    if category:
        _spaced(d, (MARGIN, 58), category.upper(), kicker, GREEN, 3)

    top, bottom = 108, HEIGHT - 96
    label_font = _font(SANS, 22, 600)
    for scale in (1.0, 0.94, 0.88, 0.82, 0.76, 0.70, 0.64):
        q_size = round(76 * scale)
        q_font = _font(LORA, q_size, 600)
        q_lines = _wrap(d, question, q_font, inner)
        q_lead = int(q_size * 1.16)
        if positions:
            p_size = round(42 * scale)
            p_font = _font(SANS, p_size, 600)
            while p_size > 26 and any(d.textlength(p, font=p_font) > inner - 44 for p in positions):
                p_size -= 2
                p_font = _font(SANS, p_size, 600)
            p_lead = int(p_size * 1.5)
            body_h = 60 + 40 + p_lead * len(positions)
        else:
            deck_size = round(40 * scale)
            deck_font = _font(SANS, deck_size, 400)
            deck_lines = _wrap(d, deck, deck_font, inner)
            deck_lead = int(deck_size * 1.35)
            body_h = 60 + deck_lead * len(deck_lines)
        block_h = q_lead * len(q_lines) + body_h
        if len(q_lines) <= 2 and block_h <= bottom - top:
            break
    y = top + max(0, (bottom - top - block_h) // 2)

    for line in q_lines:
        d.text((MARGIN, y), line, font=q_font, fill=INK)
        y += q_lead
    y += 30
    d.line([MARGIN, y, MARGIN + 160, y], fill=INK, width=3)
    y += 30

    if positions:
        _spaced(d, (MARGIN, y), "WHERE EVANGELICALS DISAGREE", label_font, MUTED, 2)
        y += 40
        for i, name in enumerate(positions):
            color = SIDE_COLORS[i % len(SIDE_COLORS)]
            box = int(p_size * 0.5)
            by = y + int(p_size * 0.62) - box // 2
            d.rectangle([MARGIN, by, MARGIN + box, by + box], fill=color)
            d.text((MARGIN + box + 22, y), name, font=p_font, fill=INK)
            y += p_lead
    else:
        for line in deck_lines:
            d.text((MARGIN, y), line, font=deck_font, fill=MUTED)
            y += deck_lead

    d.line([MARGIN, HEIGHT - 76, WIDTH - MARGIN, HEIGHT - 76], fill=RULE, width=2)
    foot = _font(SANS, 26, 600)
    d.text((MARGIN, HEIGHT - 60), "christiancurator.com", font=foot, fill=GREEN)
    return img


def render_site_image():
    """The site default card (docs/og-image.png), without the old em dash."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, WIDTH, 10], fill=GREEN)
    d.rectangle([0, HEIGHT - 5, WIDTH, HEIGHT], fill=INK)
    d.line([60, 182, WIDTH - 60, 182], fill=INK, width=4)
    title = _font(LORA, 104, 700)
    t = "Christian Curator"
    d.text(((WIDTH - d.textlength(t, font=title)) / 2, 205), t, font=title, fill=INK)
    tag_font = _font(SANS, 30, 400)
    tag = "EVANGELICAL NEWS AND THEOLOGY, CURATED DAILY"
    spacing = 2
    w = sum(d.textlength(c, font=tag_font) + spacing for c in tag) - spacing
    _spaced(d, ((WIDTH - w) / 2, 345), tag, tag_font, MUTED, spacing)
    d.line([60, 440, WIDTH - 60, 440], fill=RULE, width=3)
    url_font = _font(SANS, 36, 400)
    u = "christiancurator.com"
    d.text(((WIDTH - d.textlength(u, font=url_font)) / 2, 462), u, font=url_font, fill=GREEN)
    return img


def save_png(img, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="PNG", optimize=True)


def image_alt(question: str, positions: list[str], deck: str) -> str:
    if positions:
        rest = "Where evangelicals disagree: " + "; ".join(positions) + "."
    else:
        rest = deck
    return f"{question} {rest} christiancurator.com".strip()[:420]


# ---------------------------------------------------------------- head tags

def _tag(attr: str, key: str, value: str) -> str:
    return f'<meta content="{html.escape(value, quote=True)}" {attr}="{key}"/>'


def render_head_block(slug: str, page_html: str, card: dict, image_url: str) -> str:
    title = page_title(page_html)
    desc = og_description(card, page_html)
    alt = image_alt(card["question"], card.get("positions") or [], card.get("deck", ""))
    lines = [OG_START]
    head, _ = head_split(BLOCK_RE.sub("", page_html))
    if meta_content(head, "property", "og:type") is None:
        lines.append(_tag("property", "og:type", "article"))
    if meta_content(head, "property", "og:site_name") is None:
        lines.append(_tag("property", "og:site_name", "Christian Curator"))
    if meta_content(head, "property", "og:url") is None:
        lines.append(_tag("property", "og:url", page_canonical(page_html, slug)))
    lines += [
        _tag("property", "og:title", title),
        _tag("property", "og:description", desc),
        _tag("property", "og:image", image_url),
        _tag("property", "og:image:width", str(WIDTH)),
        _tag("property", "og:image:height", str(HEIGHT)),
        _tag("property", "og:image:type", "image/png"),
        _tag("property", "og:image:alt", alt),
        _tag("name", "twitter:card", "summary_large_image"),
        _tag("name", "twitter:title", title),
        _tag("name", "twitter:description", desc),
        _tag("name", "twitter:image", image_url),
        _tag("name", "twitter:image:alt", alt),
        OG_END,
    ]
    return "\n".join(lines) + "\n"


def apply_head(page_html: str, block: str) -> str:
    """Put the block in <head>: in place when it exists, else where the first
    managed tag was (or before </head>), removing managed tags outside it."""
    head, rest = head_split(page_html)
    if OG_START in head:
        before, _, after = head.partition(OG_START)
        _, _, after = after.partition(OG_END)
        after = after[1:] if after.startswith("\n") else after
        before = MANAGED_TAG_RE.sub("", before)
        after = MANAGED_TAG_RE.sub("", after)
        return before + block + after + rest
    m = MANAGED_TAG_RE.search(head)
    if m:
        at = m.start()
        before = head[:at]
        after = MANAGED_TAG_RE.sub("", head[at:])
        if before and not before.endswith("\n"):
            before += "\n"
        return before + block + after + rest
    if not head.endswith("\n"):
        head += "\n"
    return head + block + rest


# ---------------------------------------------------------------- driver

def build_page(slug: str, page_html: str, card: dict, category: str) -> tuple[str, str]:
    """(new page html, image file name)."""
    name = image_name(slug, card, category)
    block = render_head_block(slug, page_html, card, f"{SITE}/og/topics/{name}")
    return apply_head(page_html, block), name


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--slug", action="append", help="limit to one slug (repeatable)")
    ap.add_argument("--check", action="store_true", help="validate; exit 1 on problems or stale pages")
    ap.add_argument("--dry-run", action="store_true", help="write nothing")
    ap.add_argument("--force", action="store_true", help="re-render cards that already exist")
    ap.add_argument("--site-image", action="store_true", help="also redraw docs/og-image.png")
    args = ap.parse_args(argv)

    cards = load_cards()
    slugs = args.slug or topic_slugs()
    problems: list[str] = []
    stale: list[str] = []
    changed = rendered = 0

    for slug in slugs:
        path = TOPICS_DIR / slug / "index.html"
        if not path.exists():
            problems.append(f"{slug}: no page at {path.relative_to(REPO_ROOT)}")
            continue
        page_html = path.read_text(encoding="utf-8")
        card = cards.get(slug)
        errs = validate(slug, card, page_html)
        if errs:
            problems += errs
            continue
        category = topic_category(slug)
        new_html, name = build_page(slug, page_html, card, category)
        img_path = OG_DIR / name
        if args.check:
            if new_html != page_html:
                stale.append(f"{slug}: head tags are stale")
            if not img_path.exists():
                stale.append(f"{slug}: missing image {img_path.relative_to(REPO_ROOT)}")
            continue
        if args.dry_run:
            if new_html != page_html:
                print(f"would update head: {slug}")
            if not img_path.exists() or args.force:
                print(f"would render: {img_path.relative_to(REPO_ROOT)}")
            continue
        if not img_path.exists() or args.force:
            save_png(render_card(card["question"], category=category,
                                 positions=card.get("positions") or [], deck=card.get("deck", "")),
                     img_path)
            rendered += 1
        for old in OG_DIR.glob(f"{slug}-*.png"):
            if old.name != name and re.fullmatch(re.escape(slug) + r"-[0-9a-f]{10}\.png", old.name):
                old.unlink()
        if new_html != page_html:
            path.write_text(new_html, encoding="utf-8")
            changed += 1

    if args.site_image and not (args.check or args.dry_run):
        save_png(render_site_image(), SITE_IMAGE)
        print(f"redrew {SITE_IMAGE.relative_to(REPO_ROOT)}")

    for p in problems + stale:
        print(p)
    if args.check:
        print(f"checked {len(slugs)} pages: {len(problems)} problems, {len(stale)} stale")
        return 1 if problems or stale else 0
    if not args.dry_run:
        print(f"rendered {rendered} cards, updated {changed} pages, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
