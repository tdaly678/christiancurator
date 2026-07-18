#!/usr/bin/env python3
"""Inject a "Featured deep dives" block into docs/index.html and docs/digest/index.html.

Picks 6 deep-dive topic pages at random, seeded by today's date so the
selection rotates daily but is deterministic per day. Refreshes inbound links to
otherwise-static deep-dive URLs from the highest-authority pages on the site,
which (a) signals freshness to crawlers on every daily run and (b) ensures every
deep-dive page eventually gets an inbound link from the homepage over time.

Idempotent: if a previous block exists, replace it.
"""
from __future__ import annotations
import html as html_mod
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
TOPICS_DIR = DOCS_DIR / "topics"
VOICES_DATA = DOCS_DIR / "voices_data.json"

TARGETS = [
    DOCS_DIR / "index.html",
    DOCS_DIR / "digest" / "index.html",
]

BLOCK_START = "<!-- CC-FEATURED-DEEP-DIVES:START -->"
BLOCK_END = "<!-- CC-FEATURED-DEEP-DIVES:END -->"

N_TOPICS = 6
N_VOICES = 0  # voices are surfaced via /voices/ hub pages, not the homepage deep-dives block


def parse_meta(html: str, attr: str, name_value: str) -> str:
    m = re.search(
        rf'<meta[^>]*\s{attr}=["\']{re.escape(name_value)}["\'][^>]*\scontent=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    )
    if m:
        return m.group(1)
    m = re.search(
        rf'<meta[^>]*\scontent=["\']([^"\']*)["\'][^>]*\s{attr}=["\']{re.escape(name_value)}["\']',
        html, re.IGNORECASE,
    )
    return m.group(1) if m else ""


def parse_title(html: str) -> str:
    m = re.search(r"<title>([^<]+)</title>", html)
    if not m:
        return ""
    return html_mod.unescape(m.group(1)).split(" — ")[0].strip()


def collect_topics() -> list[dict]:
    out = []
    if not TOPICS_DIR.exists():
        return out
    for d in sorted(TOPICS_DIR.iterdir()):
        if not d.is_dir():
            continue
        idx = d / "index.html"
        if not idx.exists():
            continue
        h = idx.read_text(encoding="utf-8", errors="replace")
        title = parse_title(h)
        if not title:
            continue
        desc = parse_meta(h, "name", "description")
        out.append({
            "slug": d.name,
            "title": title,
            "desc": desc[:140],
            "url": f"/topics/{d.name}/",
        })
    return out


def collect_voices() -> list[dict]:
    if not VOICES_DATA.exists():
        return []
    data = json.loads(VOICES_DATA.read_text(encoding="utf-8"))
    out = []
    for v in data:
        bio = (v.get("bio") or "").strip()
        if len(bio) < 60:
            continue  # skip thin bios so the block stays high-quality
        role = v.get("role") or ""
        out.append({
            "slug": v["slug"],
            "name": v["name"],
            "role": role,
            "desc": bio[:140],
            "url": f"/voices/{v['slug']}/",
        })
    return out


def pick(items: list, n: int, rng: random.Random) -> list:
    if len(items) <= n:
        return list(items)
    return rng.sample(items, n)


def build_block(topics: list[dict], voices: list[dict]) -> str:
    rows: list[str] = []
    for t in topics:
        rows.append(
            f'      <a href="{t["url"]}" class="cc-fdd-card cc-fdd-topic">'
            f'<div class="cc-fdd-kind">Topic</div>'
            f'<div class="cc-fdd-title">{html_mod.escape(t["title"])}</div>'
            f'<div class="cc-fdd-desc">{html_mod.escape(t["desc"])}</div></a>'
        )
    for v in voices:
        meta = html_mod.escape(v["role"]) if v["role"] else "Voice"
        rows.append(
            f'      <a href="{v["url"]}" class="cc-fdd-card cc-fdd-voice">'
            f'<div class="cc-fdd-kind">Voice · {meta}</div>'
            f'<div class="cc-fdd-title">{html_mod.escape(v["name"])}</div>'
            f'<div class="cc-fdd-desc">{html_mod.escape(v["desc"])}</div></a>'
        )

    style = (
        "<style>"
        ".cc-fdd-section{margin:2.5rem 0 1.5rem;padding:1.5rem 0;"
        "border-top:1px solid #e0ddd8;border-bottom:1px solid #e0ddd8;}"
        ".cc-fdd-heading{font-family:'Lora',Georgia,serif;font-size:18px;font-weight:600;"
        "letter-spacing:-0.01em;margin-bottom:0.25rem;color:#1a1a1a;}"
        ".cc-fdd-sub{font-size:12px;color:#888;margin-bottom:1rem;letter-spacing:0.04em;}"
        ".cc-fdd-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:0.75rem;}"
        "@media(max-width:600px){.cc-fdd-grid{grid-template-columns:1fr;}}"
        ".cc-fdd-card{display:block;padding:0.75rem 0.9rem;background:#fff;"
        "border:1px solid #e0ddd8;border-radius:4px;text-decoration:none;color:#1a1a1a;"
        "transition:border-color 0.15s,box-shadow 0.15s;}"
        ".cc-fdd-card:hover{border-color:#2C4A2E;box-shadow:0 1px 6px rgba(44,74,46,0.08);}"
        ".cc-fdd-kind{font-size:10px;font-weight:700;letter-spacing:0.12em;"
        "text-transform:uppercase;color:#2C4A2E;margin-bottom:4px;}"
        ".cc-fdd-title{font-family:'Lora',Georgia,serif;font-size:15px;font-weight:600;"
        "line-height:1.3;margin-bottom:4px;color:#1a1a1a;}"
        ".cc-fdd-desc{font-size:12.5px;color:#666;line-height:1.5;}"
        "</style>"
    )

    return (
        f'\n  {BLOCK_START}\n'
        f'  <section class="cc-fdd-section" aria-label="Featured deep dives">\n'
        f'    {style}\n'
        f'    <h2 class="cc-fdd-heading">Featured deep dives</h2>\n'
        f'    <div class="cc-fdd-sub">A daily-rotating selection from our topic archives.</div>\n'
        f'    <div class="cc-fdd-grid">\n'
        + "\n".join(rows)
        + f'\n    </div>\n'
        f'  </section>\n'
        f'  {BLOCK_END}\n'
    )


def inject(html: str, block: str) -> str:
    # Remove any existing block (idempotent)
    html = re.sub(
        re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END) + r"\s*",
        "",
        html,
        flags=re.DOTALL,
    )
    # Insert before </main>
    if "</main>" in html:
        return html.replace("</main>", block + "\n  </main>", 1)
    # Fallback: before </body>
    return html.replace("</body>", block + "\n</body>", 1)


def main() -> int:
    topics = collect_topics()
    voices = collect_voices()
    if not topics and not voices:
        print("no topics or voices to feature", file=sys.stderr)
        return 1

    seed = int(date.today().strftime("%Y%m%d"))
    rng = random.Random(seed)
    chosen_topics = pick(topics, N_TOPICS, rng)
    chosen_voices = pick(voices, N_VOICES, rng)

    block = build_block(chosen_topics, chosen_voices)

    for path in TARGETS:
        if not path.exists():
            print(f"skip (missing): {path}")
            continue
        html = path.read_text(encoding="utf-8")
        new_html = inject(html, block)
        path.write_text(new_html, encoding="utf-8")
        print(f"injected featured deep dives into {path.relative_to(REPO_ROOT)}")

    print(
        f"  picked: {len(chosen_topics)} topics, {len(chosen_voices)} voices "
        f"(seed={seed})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
