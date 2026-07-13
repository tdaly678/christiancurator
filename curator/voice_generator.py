"""
voice_generator.py — Auto-generates Voices pages for new authors found in curated articles.

Called from main.py after render_html. For each author in today's articles that doesn't
already have a voice page, it uses the Claude API to generate a structured bio, then
writes the HTML page and updates docs/voices_data.json.

Author data schema (voices_data.json):
  [{"name", "slug", "bio", "affiliation", "role", "education", "website",
    "books": [{"title", "amazon_url"}], "initials"}, ...]
"""

import json
import os
import re
import anthropic
from pathlib import Path

DOCS_DIR = Path(__file__).parent.parent / "docs"
VOICES_DIR = DOCS_DIR / "voices"
VOICES_DATA_PATH = DOCS_DIR / "voices_data.json"

SKIP_AUTHORS = {
    "staff", "editor", "admin", "contributor", "guest", "anonymous", "unknown",
    "the editors", "fm editors", "beshay", "the new york times", "reuters",
    "associated press", "ap", "staff writer", "guest writer",
}

AVATAR_COLORS = [
    "#2C4A2E", "#3a5f3c", "#4a7a4e", "#1e3520",
    "#5a7a3e", "#3d6b4f", "#2e5540", "#4a6030",
    "#385e35", "#2a4a3a", "#506840", "#3b5e2e",
]

NAV_HTML = """    <nav class="cc-nav">
      <a href="/">Home</a>
      <div class="cc-nav-dropdown">
        <button class="cc-nav-dropdown-toggle" style="color:#1a1a1a;">Resources</button>
        <div class="cc-nav-dropdown-menu">
          <a href="/about/">About</a>
          <a href="/voices/" class="active">Voices</a>
          <a href="/archive/">Archive</a>
        </div>
      </div>
    </nav>"""

NAV_CSS = """
    .cc-nav{display:flex;justify-content:center;align-items:center;gap:2rem;padding:0.6rem 0 0;border-top:1px solid #e0ddd8;margin-top:0.75rem;}
    .cc-nav a{font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#888;text-decoration:none;}
    .cc-nav a:hover{color:#2C4A2E;}
    .cc-nav a.active{color:#1a1a1a;border-bottom:2px solid #1a1a1a;padding-bottom:2px;}
    .cc-nav-dropdown{position:relative;display:inline-block;}
    .cc-nav-dropdown-toggle{font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;cursor:pointer;display:flex;align-items:center;gap:4px;background:none;border:none;font-family:inherit;padding:0;}
    .cc-nav-dropdown-toggle:hover{color:#2C4A2E;}
    .cc-nav-dropdown-toggle::after{content:"▾";font-size:10px;letter-spacing:0;}
    .cc-nav-dropdown-menu{display:none;position:absolute;top:100%;left:50%;transform:translateX(-50%);background:#fff;border:1px solid #e0ddd8;border-radius:4px;padding:14px 0 6px;min-width:140px;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,0.08);}
    .cc-nav-dropdown:hover .cc-nav-dropdown-menu,.cc-nav-dropdown:focus-within .cc-nav-dropdown-menu{display:block;}
    .cc-nav-dropdown-menu a{display:block;padding:7px 18px;font-size:12px;font-weight:600;letter-spacing:0.08em;text-transform:uppercase;color:#888;text-decoration:none;white-space:nowrap;}
    .cc-nav-dropdown-menu a:hover{color:#2C4A2E;background:#f7f5f2;}
    .cc-nav-dropdown-menu a.active{color:#1a1a1a;}"""

HEADER_HTML = """  <header class="cc-header">
    <div class="cc-top-bar">
      <a href="/" style="font-size:12px;color:#2C4A2E;text-decoration:none;font-weight:600;">← Home</a>
      <a class="cc-subscribe-btn" href="/#cc-email-box">Get the Daily Digest</a>
    </div>
    <div class="cc-masthead">
      <a href="/" class="cc-site-name">Christian Curator</a>
      <p class="cc-tagline">Curated perspectives &middot; updated daily</p>
    </div>
{nav}
  </header>"""

FOOTER_HTML = """  <footer class="cc-footer">
    <div class="cc-footer-name">Christian Curator</div>
    <div class="cc-footer-nav">
      <a href="/about/">About</a>
      <a href="/digest/">Daily Digest</a>
      <a href="/voices/">Voices</a>
      <a href="/archive/">Archive</a>
    </div>
    <div>Curated from across the evangelical web.</div>
  </footer>"""

SITE_URL = "https://www.christiancurator.com"
PERSON_MARKER = "CC-PERSON-SCHEMA"
FAQ_MARKER = "AEO-FAQPAGE-SCHEMA"

# CSS for the Quick Facts box + FAQ section. Kept in sync with
# scripts/apply_voice_enrichment.py so newly generated pages match enriched ones.
ENRICH_CSS = """
    .cc-qf{background:#fff;border:1px solid #e0ddd8;border-radius:5px;padding:1.1rem 1.4rem;margin:0 0 2rem;}
    .cc-qf-label{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;margin-bottom:0.7rem;}
    .cc-qf-item{display:flex;gap:1rem;padding:0.5rem 0;border-bottom:1px solid #f0ede8;align-items:baseline;}
    .cc-qf-item:last-child{border-bottom:none;padding-bottom:0;}
    .cc-qf-item:first-of-type{padding-top:0;}
    .cc-qf-key{font-size:10px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#aaa;min-width:96px;flex-shrink:0;}
    .cc-qf-val{font-size:14px;color:#333;line-height:1.55;}
    .cc-faq{margin-top:2.5rem;padding-top:1.75rem;border-top:2px solid #e0ddd8;}
    .cc-faq-label{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;margin-bottom:0.5rem;}
    .cc-faq-title{font-family:'Lora',Georgia,serif;font-size:22px;font-weight:600;margin-bottom:1.25rem;color:#1a1a1a;}
    .cc-faq-item{margin-bottom:1.4rem;}
    .cc-faq-item:last-child{margin-bottom:0;}
    .cc-faq-q{font-family:'Lora',Georgia,serif;font-size:16px;font-weight:600;line-height:1.35;margin-bottom:0.35rem;color:#1a1a1a;}
    .cc-faq-a{font-size:15px;color:#333;line-height:1.7;}""".rstrip()

# Quick-facts rows: (data key, visible label). current_role is dropped for deceased voices.
_QF_ROWS = [
    ("denomination", "Denomination"),
    ("tradition", "Tradition"),
    ("current_role", "Current role"),
    ("known_for", "Known for"),
]


def _esc(text: str) -> str:
    """Minimal HTML escaping for text nodes."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_quick_facts(author: dict) -> str:
    """Render the Quick Facts box, or '' when no quick-facts data exists."""
    deceased = bool(author.get("deceased"))
    rows = []
    for key, label in _QF_ROWS:
        if key == "current_role" and deceased:
            continue
        val = author.get(key)
        if val:
            rows.append((label, str(val).strip()))
    if not rows:
        return ""
    items = "".join(
        f'\n      <div class="cc-qf-item"><span class="cc-qf-key">{_esc(label)}</span>'
        f'<span class="cc-qf-val">{_esc(val)}</span></div>'
        for label, val in rows
    )
    return (
        '\n    <div class="cc-qf">'
        '\n      <div class="cc-qf-label">Quick Facts</div>'
        f'{items}'
        '\n    </div>'
    )


def render_faq_section(author: dict) -> str:
    """Render the visible FAQ section, or '' when no faqs exist."""
    faqs = author.get("faqs") or []
    if not faqs:
        return ""
    name = author.get("name", "")
    items = ""
    for qa in faqs:
        items += (
            '\n      <div class="cc-faq-item">'
            f'\n        <h3 class="cc-faq-q">{_esc(qa["q"])}</h3>'
            f'\n        <p class="cc-faq-a">{_esc(qa["a"])}</p>'
            '\n      </div>'
        )
    return (
        '\n    <section class="cc-faq">'
        '\n      <div class="cc-faq-label">Frequently Asked Questions</div>'
        f'\n      <h2 class="cc-faq-title">Frequently Asked Questions about {_esc(name)}</h2>'
        f'{items}'
        '\n    </section>'
    )


def render_jsonld(author: dict) -> str:
    """Render Person (+ FAQPage when faqs exist) JSON-LD script tags."""
    slug = author["slug"]
    person = {
        "@context": "https://schema.org",
        "@type": "Person",
        "name": author["name"],
        "url": f"{SITE_URL}/voices/{slug}/",
    }
    if author.get("bio"):
        person["description"] = author["bio"]
    if author.get("role"):
        person["jobTitle"] = author["role"]
    if author.get("affiliation"):
        person["affiliation"] = {"@type": "Organization", "name": author["affiliation"]}
    same_as = [u for u in [author.get("website")] if u]
    if same_as:
        person["sameAs"] = same_as

    blocks = [
        f'  <script type="application/ld+json" data-cc-marker="{PERSON_MARKER}">\n'
        + json.dumps(person, ensure_ascii=False, indent=2)
        + "\n  </script>"
    ]

    faqs = author.get("faqs") or []
    if faqs:
        faq_data = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": qa["q"],
                    "acceptedAnswer": {"@type": "Answer", "text": qa["a"]},
                }
                for qa in faqs
            ],
        }
        blocks.append(
            f'  <script type="application/ld+json" data-cc-marker="{FAQ_MARKER}">\n'
            + json.dumps(faq_data, ensure_ascii=False, indent=2)
            + "\n  </script>"
        )
    return "\n" + "\n".join(blocks)


# ── Utilities ──────────────────────────────────────────────────────────────────

def name_to_slug(name: str) -> str:
    """Convert an author name to a URL-safe slug."""
    # Remove emoji, degree suffixes, and trailing punctuation
    name = re.sub(r'[^\x00-\x7F]', '', name)          # strip non-ASCII (emoji etc.)
    name = re.sub(r'\b(Jr\.?|Sr\.?|PhD\.?|Ph\.D\.?|MD\.?|M\.D\.?|Esq\.?)\b', '', name, flags=re.IGNORECASE)
    name = name.lower()
    name = re.sub(r'[^a-z0-9\s]', '', name)            # remove remaining punctuation
    name = re.sub(r'\s+', '-', name.strip())
    name = re.sub(r'-+', '-', name).strip('-')
    return name


def load_voices_data() -> list:
    if VOICES_DATA_PATH.exists():
        try:
            return json.loads(VOICES_DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def save_voices_data(data: list):
    VOICES_DATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def get_existing_slugs() -> set:
    """Return slugs of authors who already have pages."""
    existing = set()
    if VOICES_DIR.exists():
        for d in VOICES_DIR.iterdir():
            if d.is_dir() and (d / "index.html").exists():
                existing.add(d.name)
    return existing


_EMAIL_RE = r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'

# Production-credit bylines ("executive producer ...", "produced by ...") are
# credits, not authors — they generate junk description-as-slug voice pages.
_CREDIT_RE = re.compile(
    r'\b(executive producer|produced by|presented by|narrated by|photographs? by|'
    r'sound design|series editor)\b', re.IGNORECASE)


def normalize_author_name(raw: str) -> str:
    """Normalize a byline fragment before slugging.

    RSS 2.0 <author> fields arrive as "email@example.com (Real Name)" — extract
    "Real Name". Bare emails return "" (skip), so slugs like
    "jpanyardchristianitytodaycom" never regenerate.
    """
    raw = (raw or "").strip()
    m = re.fullmatch(_EMAIL_RE + r'\s*\((.+?)\)', raw)
    if m:
        return m.group(1).strip()
    if re.fullmatch(_EMAIL_RE, raw):
        return ""
    # Strip any embedded email address left in the byline
    raw = re.sub(_EMAIL_RE, '', raw)
    return re.sub(r'\s{2,}', ' ', raw).strip(' \t,;:()-')


def extract_new_authors(articles: list, existing_slugs: set) -> list:
    """Return list of (name, slug) tuples for authors not yet in the voices section."""
    seen_names = set()
    new_authors = []
    for article in articles:
        raw = (article.get("author") or "").strip()
        if not raw:
            continue
        # Drop production-credit bylines entirely (not real author names)
        if _CREDIT_RE.search(raw):
            continue
        # Split comma/semicolon-separated multi-author bylines into individual names
        candidates = [normalize_author_name(n) for n in re.split(r'[,;]', raw)]
        candidates = [n for n in candidates if n]
        for name in candidates:
            # Skip blanks, short strings, known junk
            if len(name) < 4:
                continue
            if '@' in name:
                continue
            if name.lower() in SKIP_AUTHORS:
                continue
            # Skip obvious news bylines like "Name in City"
            if re.search(r'\b(in |at )\b', name):
                continue
            if name in seen_names:
                continue
            seen_names.add(name)
            slug = name_to_slug(name)
            if slug and slug not in existing_slugs:
                new_authors.append({"name": name, "slug": slug})
    return new_authors


def avatar_color(index: int) -> str:
    return AVATAR_COLORS[index % len(AVATAR_COLORS)]


# ── Bio generation via Claude API ─────────────────────────────────────────────

def generate_bio_data(name: str) -> dict:
    """
    Use the Claude API to generate structured bio data for an evangelical author.
    Returns a dict matching the voices_data schema, or a minimal stub on failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(f"    ⚠️  ANTHROPIC_API_KEY not set — using stub bio for {name}")
        return _stub_bio(name)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""You are helping build author bio pages for a Christian content curation website.
Generate structured bio data for the following person: {name}

Return ONLY a valid JSON object (no markdown, no commentary) with these exact fields:
{{
  "name": "{name}",
  "slug": "<url-safe lowercase slug>",
  "bio": "<2-3 sentence biography for a Christian audience>",
  "affiliation": "<primary publication(s) or institution they write for>",
  "role": "<concise role, e.g. Author & Pastor, Professor & Writer>",
  "education": "<highest degree and institution if publicly known, else empty string>",
  "website": "<personal website or blog URL if publicly known, else empty string>",
  "books": [
    {{"title": "<book title>", "amazon_url": "https://www.amazon.com/s?k=<title+author url-encoded>"}}
  ],
  "initials": "<2-3 initials>"
}}

Rules:
- Include up to 6 books maximum. If no books are known, use an empty array [].
- If this person is not well-known or you are uncertain about details, keep the bio brief and accurate, and omit uncertain fields by using empty strings or [].
- Do not invent facts. If education is unknown, use "".
- The bio should be warm and informative, written for a curious evangelical Christian reader.
"""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )
        text = message.content[0].text.strip()
        # Strip markdown code fences if present
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        data = json.loads(text)
        # Ensure required fields exist
        data.setdefault("name", name)
        data.setdefault("slug", name_to_slug(name))
        data.setdefault("bio", "")
        data.setdefault("affiliation", "")
        data.setdefault("role", "Author & Writer")
        data.setdefault("education", "")
        data.setdefault("website", "")
        data.setdefault("books", [])
        data.setdefault("initials", "".join(p[0].upper() for p in name.split()[:3] if p))
        data["books"] = data["books"][:6]
        return data
    except Exception as e:
        print(f"    ⚠️  Bio generation failed for {name}: {e}")
        return _stub_bio(name)


def _stub_bio(name: str) -> dict:
    """Minimal fallback bio when API is unavailable."""
    initials = "".join(p[0].upper() for p in name.split()[:3] if p and p[0].isalpha())
    return {
        "name": name,
        "slug": name_to_slug(name),
        "bio": f"{name} is a writer whose work appears in evangelical publications curated by Christian Curator.",
        "affiliation": "",
        "role": "Author & Writer",
        "education": "",
        "website": "",
        "books": [],
        "initials": initials or name[:2].upper(),
    }


# ── HTML rendering ─────────────────────────────────────────────────────────────

def render_bio_page(author: dict, index: int) -> str:
    name = author["name"]
    slug = author["slug"]
    role = author.get("role", "")
    bio = author.get("bio", "")
    affiliation = author.get("affiliation", "")
    education = author.get("education", "")
    website = author.get("website", "")
    books = (author.get("books") or [])[:6]
    initials = author.get("initials") or "".join(p[0].upper() for p in name.split()[:3] if p and p[0].isalpha()) or name[:2].upper()
    color = avatar_color(index)

    # Split bio on blank lines to support multi-paragraph bios. Single-paragraph
    # bios continue to render as one <p>; two-paragraph bios render as two <p>s.
    bio_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", bio.strip()) if p.strip()]
    bio_html = "\n    ".join(f'<p class="cc-voice-bio">{p}</p>' for p in bio_paragraphs) if bio_paragraphs else f'<p class="cc-voice-bio">{bio}</p>'

    books_html = ""
    if books:
        books_html = '\n    <div class="cc-voice-section">\n      <div class="cc-section-label">Notable Books</div>\n      <div class="cc-books-list">'
        for book in books:
            books_html += f'\n        <a href="{book["amazon_url"]}" target="_blank" rel="noopener noreferrer" class="cc-book-item"><span class="cc-book-title">{book["title"]}</span><span class="cc-book-link">Amazon &rarr;</span></a>'
        books_html += '\n      </div>\n    </div>'

    meta_items = []
    if affiliation:
        meta_items.append(f'<div class="cc-meta-item"><span class="cc-meta-label">Writes for</span><span class="cc-meta-value">{affiliation}</span></div>')
    if education:
        meta_items.append(f'<div class="cc-meta-item"><span class="cc-meta-label">Education</span><span class="cc-meta-value">{education}</span></div>')
    if website:
        display = website.replace("https://", "").replace("http://", "").rstrip("/")
        meta_items.append(f'<div class="cc-meta-item"><span class="cc-meta-label">Website</span><a href="{website}" target="_blank" rel="noopener noreferrer" class="cc-meta-link">{display}</a></div>')
    meta_html = '\n      '.join(meta_items)
    meta_block = f'    <div class="cc-voice-meta">\n      {meta_html}\n    </div>' if meta_items else ''

    quickfacts_block = render_quick_facts(author)
    faq_block = render_faq_section(author)
    jsonld_block = render_jsonld(author)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{name} — Voices — Christian Curator</title>
  <meta name="description" content="{bio[:160]}" />
  <link rel="canonical" href="https://www.christiancurator.com/voices/{slug}/" />
  <meta property="og:type" content="profile" />
  <meta property="og:site_name" content="Christian Curator" />
  <meta property="og:title" content="{name} — Voices — Christian Curator" />
  <meta property="og:description" content="{bio[:200]}" />
  <meta property="og:url" content="https://www.christiancurator.com/voices/{slug}/" />
  <meta property="og:image" content="https://www.christiancurator.com/og-image.png" />
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-3NJ5DSPFXL"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","G-3NJ5DSPFXL");</script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet" />
{jsonld_block}
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:"Source Sans 3",sans-serif;background:#faf9f7;color:#1a1a1a;font-size:16px;line-height:1.5;}}
    .cc-root{{max-width:980px;margin:0 auto;padding:0 20px 3rem;}}
    main.cc-prose{{max-width:740px;margin:0 auto;padding-top:1.5rem;}}
    .cc-header{{border-bottom:1px solid #e0ddd8;padding:0.75rem 0 0;margin-bottom:2.5rem;}}
    .cc-top-bar{{display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;font-size:12px;color:#888;}}
    .cc-subscribe-btn{{background:#2C4A2E;color:#fff;padding:5px 14px;font-size:12px;border-radius:3px;text-decoration:none;font-family:inherit;}}
    .cc-subscribe-btn:hover{{background:#3a5f3c;}}
    .cc-masthead{{text-align:center;padding:0.5rem 0 1rem;border-bottom:2.5px solid #1a1a1a;}}
    .cc-site-name{{font-family:"Lora",Georgia,serif;font-size:46px;font-weight:600;letter-spacing:-0.02em;color:#1a1a1a;text-decoration:none;display:block;}}
    .cc-site-name:hover{{color:#2C4A2E;}}
    .cc-tagline{{font-size:12px;letter-spacing:0.18em;text-transform:uppercase;color:#888;margin:8px 0 0;font-weight:300;}}
    @media(max-width:600px){{.cc-site-name{{font-size:32px;}}}}
    {NAV_CSS}
    {ENRICH_CSS}
    .cc-breadcrumb{{font-size:11px;color:#aaa;margin-bottom:1.5rem;}}
    .cc-breadcrumb a{{color:#2C4A2E;text-decoration:none;}}
    .cc-breadcrumb a:hover{{text-decoration:underline;}}
    .cc-breadcrumb span{{margin:0 6px;}}
    .cc-voice-hero{{display:flex;align-items:flex-start;gap:1.25rem;margin-bottom:2rem;padding-bottom:2rem;border-bottom:2px solid #1a1a1a;}}
    .cc-voice-avatar{{width:64px;height:64px;border-radius:50%;background:{color};display:flex;align-items:center;justify-content:center;font-family:"Lora",Georgia,serif;font-size:18px;font-weight:600;color:#fff;flex-shrink:0;letter-spacing:0.02em;}}
    .cc-voice-name{{font-family:"Lora",Georgia,serif;font-size:28px;font-weight:600;line-height:1.2;color:#1a1a1a;margin-bottom:4px;}}
    .cc-voice-role{{font-size:12px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:#2C4A2E;}}
    .cc-voice-bio{{font-family:"Lora",Georgia,serif;font-size:17px;line-height:1.75;color:#1a1a1a;margin-bottom:2rem;}}
    .cc-voice-meta{{background:#fff;border:1px solid #e0ddd8;border-radius:5px;padding:1.25rem 1.5rem;margin-bottom:2rem;}}
    .cc-meta-item{{display:flex;gap:1rem;padding:0.6rem 0;border-bottom:1px solid #f0ede8;align-items:baseline;}}
    .cc-meta-item:last-child{{border-bottom:none;padding-bottom:0;}}
    .cc-meta-item:first-child{{padding-top:0;}}
    .cc-meta-label{{font-size:10px;font-weight:700;letter-spacing:0.14em;text-transform:uppercase;color:#aaa;min-width:80px;flex-shrink:0;}}
    .cc-meta-value{{font-size:14px;color:#444;line-height:1.5;}}
    .cc-meta-link{{font-size:14px;color:#2C4A2E;text-decoration:none;}}
    .cc-meta-link:hover{{text-decoration:underline;}}
    .cc-section-label{{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;margin-bottom:0.9rem;}}
    .cc-books-list{{display:flex;flex-direction:column;gap:0;}}
    .cc-book-item{{display:flex;align-items:center;justify-content:space-between;padding:0.75rem 0;border-bottom:1px solid #f0ede8;text-decoration:none;color:#1a1a1a;}}
    .cc-book-item:last-child{{border-bottom:none;}}
    .cc-book-item:hover .cc-book-title{{color:#2C4A2E;}}
    .cc-book-title{{font-family:"Lora",Georgia,serif;font-size:15px;font-weight:500;line-height:1.35;}}
    .cc-book-link{{font-size:12px;font-weight:600;color:#2C4A2E;white-space:nowrap;margin-left:1rem;flex-shrink:0;}}
    .cc-back-link{{display:inline-block;margin-top:2rem;font-size:13px;color:#2C4A2E;text-decoration:none;font-weight:600;border-bottom:1px solid #2C4A2E;}}
    .cc-back-link:hover{{color:#1a1a1a;border-color:#1a1a1a;}}
    .cc-footer{{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #e0ddd8;font-size:12px;color:#aaa;text-align:center;line-height:1.8;}}
    .cc-footer-name{{font-family:"Lora",serif;font-size:14px;color:#888;margin-bottom:4px;}}
    .cc-footer-nav{{display:flex;justify-content:center;gap:1.5rem;margin-bottom:6px;}}
    .cc-footer-nav a{{color:#aaa;text-decoration:none;font-size:12px;}}
    .cc-footer-nav a:hover{{color:#2C4A2E;}}
  </style>
</head>
<body>
<div class="cc-root">

{HEADER_HTML.format(nav=NAV_HTML)}

  <main class="cc-prose">
    <div class="cc-breadcrumb">
      <a href="/">Home</a><span>›</span>
      <a href="/voices/">Voices</a><span>›</span>
      {name}
    </div>
    <div class="cc-voice-hero">
      <div class="cc-voice-avatar">{initials}</div>
      <div>
        <h1 class="cc-voice-name">{name}</h1>
        <div class="cc-voice-role">{role}</div>
      </div>
    </div>
    {quickfacts_block}
    {bio_html}
    {meta_block}
    {books_html}
    {faq_block}
    <a href="/voices/" class="cc-back-link">&larr; All Voices</a>
  </main>

{FOOTER_HTML}

</div>
</body>
</html>"""


def render_voices_index(authors: list) -> str:
    """Re-render the /voices/ index page with the full sorted author list."""
    def sort_key(a):
        parts = re.sub(r'\b(Jr\.?|Sr\.?|PhD\.?)\b', '', a["name"], flags=re.IGNORECASE).strip().split()
        return parts[-1].lower() if parts else a["name"].lower()

    authors_sorted = sorted(authors, key=sort_key)

    cards = ""
    for i, author in enumerate(authors_sorted):
        name = author["name"]
        slug = author["slug"]
        role = author.get("role", "")
        bio = author.get("bio", "")
        initials = author.get("initials") or "".join(p[0].upper() for p in name.split()[:3] if p and p[0].isalpha()) or name[:2].upper()
        color = avatar_color(i)
        teaser = bio[:120].rsplit(" ", 1)[0] + "…" if len(bio) > 120 else bio

        cards += f"""
      <a href="/voices/{slug}/" class="cc-voice-card">
        <div class="cc-voice-card-avatar" style="background:{color};">{initials}</div>
        <div class="cc-voice-card-body">
          <div class="cc-voice-card-name">{name}</div>
          <div class="cc-voice-card-role">{role}</div>
          <div class="cc-voice-card-teaser">{teaser}</div>
        </div>
      </a>"""

    # Read the current index and replace just the grid + count, preserving any manual edits
    # to CSS/structure by regenerating from scratch with the full template
    index_path = VOICES_DIR / "index.html"
    if index_path.exists():
        current = index_path.read_text(encoding="utf-8")
        # Update the count line
        current = re.sub(
            r'— \d+ voices worth following\.',
            f'— {len(authors_sorted)} voices worth following.',
            current
        )
        # Replace the grid contents
        current = re.sub(
            r'(<div class="cc-voices-grid">)(.*?)(</div>\s*</main>)',
            lambda m: m.group(1) + cards + '\n    ' + m.group(3),
            current,
            flags=re.DOTALL
        )
        return current

    # Fallback: build from scratch
    return _build_index_from_scratch(authors_sorted, cards)


def _build_index_from_scratch(authors_sorted: list, cards: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Voices — Christian Curator</title>
  <meta name="description" content="Meet the writers, pastors, and thinkers whose work we curate most often — the voices shaping evangelical Christianity." />
  <link rel="canonical" href="https://www.christiancurator.com/voices/" />
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-3NJ5DSPFXL"></script>
  <script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag("js",new Date());gtag("config","G-3NJ5DSPFXL");</script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,500;0,600;1,400&family=Source+Sans+3:wght@300;400;600&display=swap" rel="stylesheet" />
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
    body{{font-family:"Source Sans 3",sans-serif;background:#faf9f7;color:#1a1a1a;font-size:16px;line-height:1.5;}}
    .cc-root{{max-width:760px;margin:0 auto;padding:0 20px 4rem;}}
    .cc-header{{border-bottom:1px solid #e0ddd8;padding:0.75rem 0 0;margin-bottom:2.5rem;}}
    .cc-top-bar{{display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;font-size:12px;color:#888;}}
    .cc-subscribe-btn{{background:#2C4A2E;color:#fff;padding:5px 14px;font-size:12px;border-radius:3px;text-decoration:none;font-family:inherit;}}
    .cc-masthead{{text-align:center;padding:0.5rem 0 1rem;border-bottom:2.5px solid #1a1a1a;}}
    .cc-site-name{{font-family:"Lora",Georgia,serif;font-size:46px;font-weight:600;letter-spacing:-0.02em;color:#1a1a1a;text-decoration:none;display:block;}}
    .cc-site-name:hover{{color:#2C4A2E;}}
    .cc-tagline{{font-size:12px;letter-spacing:0.18em;text-transform:uppercase;color:#888;margin:8px 0 0;font-weight:300;}}
    {NAV_CSS}
    .cc-page-header{{border-bottom:2px solid #1a1a1a;padding-bottom:0.75rem;margin-bottom:0.5rem;}}
    .cc-page-label{{font-size:10px;font-weight:700;letter-spacing:0.16em;text-transform:uppercase;color:#2C4A2E;margin-bottom:0.4rem;}}
    .cc-page-title{{font-family:"Lora",Georgia,serif;font-size:30px;font-weight:600;color:#1a1a1a;}}
    .cc-page-desc{{font-size:14px;color:#666;line-height:1.65;margin:0.75rem 0 2rem;}}
    .cc-voices-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem;}}
    @media(max-width:580px){{.cc-voices-grid{{grid-template-columns:1fr;}}}}
    .cc-voice-card{{display:flex;gap:0.9rem;align-items:flex-start;padding:1rem 1.1rem;background:#fff;border:1px solid #e0ddd8;border-radius:5px;text-decoration:none;color:#1a1a1a;transition:border-color 0.15s,box-shadow 0.15s;}}
    .cc-voice-card:hover{{border-color:#2C4A2E;box-shadow:0 2px 8px rgba(44,74,46,0.08);}}
    .cc-voice-card-avatar{{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:"Lora",Georgia,serif;font-size:13px;font-weight:600;color:#fff;flex-shrink:0;letter-spacing:0.02em;}}
    .cc-voice-card-name{{font-family:"Lora",Georgia,serif;font-size:15px;font-weight:600;line-height:1.25;margin-bottom:2px;color:#1a1a1a;}}
    .cc-voice-card-role{{font-size:10px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:#2C4A2E;margin-bottom:5px;}}
    .cc-voice-card-teaser{{font-size:12.5px;color:#666;line-height:1.5;}}
    .cc-footer{{margin-top:3rem;padding-top:1.5rem;border-top:1px solid #e0ddd8;font-size:12px;color:#aaa;text-align:center;line-height:1.8;}}
    .cc-footer-name{{font-family:"Lora",serif;font-size:14px;color:#888;margin-bottom:4px;}}
    .cc-footer-nav{{display:flex;justify-content:center;gap:1.5rem;margin-bottom:6px;}}
    .cc-footer-nav a{{color:#aaa;text-decoration:none;font-size:12px;}}
  </style>
</head>
<body>
<div class="cc-root">
{HEADER_HTML.format(nav=NAV_HTML)}
  <main>
    <div class="cc-page-header">
      <div class="cc-page-label">Resources</div>
      <h1 class="cc-page-title">Voices</h1>
    </div>
    <p class="cc-page-desc">The writers, pastors, scholars, and thinkers whose work we curate most often — {len(authors_sorted)} voices worth following.</p>
    <div class="cc-voices-grid">
      {cards}
    </div>
  </main>
{FOOTER_HTML}
</div>
</body>
</html>"""


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_new_voice_pages(articles: list) -> int:
    """
    Detect authors in today's articles that don't yet have voice pages.
    Generate their bio pages and update the voices index.
    Returns the number of new pages created.
    """
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    existing_slugs = get_existing_slugs()
    new_authors = extract_new_authors(articles, existing_slugs)

    if not new_authors:
        print("  Voices: no new authors found.")
        return 0

    print(f"  Voices: {len(new_authors)} new author(s) detected — generating pages...")

    voices_data = load_voices_data()
    existing_data_slugs = {a["slug"] for a in voices_data}
    total_existing = len(voices_data)

    for entry in new_authors:
        name, slug = entry["name"], entry["slug"]
        print(f"    → {name}")
        bio_data = generate_bio_data(name)
        bio_data["slug"] = slug  # use our computed slug for consistency

        # Write individual page
        author_dir = VOICES_DIR / slug
        author_dir.mkdir(parents=True, exist_ok=True)
        page_html = render_bio_page(bio_data, total_existing + len(voices_data))
        (author_dir / "index.html").write_text(page_html, encoding="utf-8")

        # Add to data store
        if slug not in existing_data_slugs:
            voices_data.append(bio_data)
            existing_data_slugs.add(slug)

    # Re-render the index
    index_html = render_voices_index(voices_data)
    (VOICES_DIR / "index.html").write_text(index_html, encoding="utf-8")

    # Persist updated data
    save_voices_data(voices_data)

    print(f"  Voices: {len(new_authors)} new page(s) created. Index updated.")
    return len(new_authors)
