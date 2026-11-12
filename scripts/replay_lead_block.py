"""
replay_lead_block.py: rerun the homepage lead block offline for past editions.

Builds each day's candidate pool from the article_history.json rows shown that
day (the full scored pool is not committed), adds authors from that day's
homepage in git, rebuilds the Daily Pulse from docs/daily/<date>/index.html,
then prints the Lead and the email's top 8 (lead block, then the first board
rows in email order) under the layout at a git ref ("before") and the working
tree ("after"). Each row is tagged ideas / commentary / news / scandal and
marked * when the Pulse drew on it. Writes nothing.

  .venv/bin/python scripts/replay_lead_block.py 2026-11-12 2026-11-11
  .venv/bin/python scripts/replay_lead_block.py --before-ref b8b55af2b 2026-11-12
"""

import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from curator.dedup import canonical_url  # noqa: E402
from curator.editorial import content_kind, pulse_cited_urls  # noqa: E402
from curator.email_sender import EMAIL_BOARD_PER_COLUMN  # noqa: E402
from frontend import layout as new_layout  # noqa: E402

TOP_N = 8


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def run_commit(day: str) -> str:
    out = _git("log", "--format=%h", "-1", "--grep", f"daily curator run {day}")
    return out.strip()


def authors_from_homepage(commit: str) -> dict:
    """url -> author, from the bylines on that day's rendered homepage."""
    page = _git("show", f"{commit}:docs/index.html")
    out = {}
    for m in re.finditer(r'<a href="(https?://[^"]+)"[^>]*class="cc-(?:lead|sublead|board)-title"'
                         r'.*?<strong>([^<]+)</strong>', page, re.S):
        out.setdefault(canonical_url(m.group(1)), m.group(2).strip())
    return out


def pulse_from_daily_page(day: str) -> dict | None:
    path = ROOT / "docs" / "daily" / day / "index.html"
    if not path.exists():
        return None
    body = path.read_text()
    m = re.search(r'<div class="cc-daily-body">(.*?)</div>', body, re.S)
    if not m:
        return None
    paras = [p.strip() for p in re.findall(r"<p>(.*?)</p>", m.group(1), re.S)]
    plain = [re.sub(r"<[^>]+>", "", p) for p in paras]
    return {"paragraphs_html": paras, "paragraphs_plain": plain, "slug": day}


def load_old_layout(ref: str):
    src = _git("show", f"{ref}:frontend/layout.py")
    tmp = Path(tempfile.mkdtemp()) / "layout_before.py"
    tmp.write_text(src)
    spec = importlib.util.spec_from_file_location("layout_before", tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def email_top(layout: dict, n: int = TOP_N) -> list[dict]:
    eligible = new_layout.email_eligible
    items = [a for a in [layout.get("lead"), *layout.get("subleads", [])] if a and eligible(a)]
    for col in layout.get("board", []):
        items += [a for a in col["articles"] if eligible(a)][:EMAIL_BOARD_PER_COLUMN]
    return items[:n]


def _row(i: int, a: dict, cited: set) -> str:
    mark = "*" if canonical_url(a["url"]) in cited else " "
    return (f"  {i}. [{content_kind(a)}]{mark} {a.get('title')}  "
            f"({a.get('source_name')}, {a.get('final_score')})")


def replay(day: str, old) -> None:
    history = json.loads((ROOT / "docs" / "article_history.json").read_text())
    rows = [dict(r) for r in history if r.get("date_shown") == day and r.get("scored_by") != "media"]
    commit = run_commit(day)
    authors = authors_from_homepage(commit) if commit else {}
    for r in rows:
        r.setdefault("author", authors.get(canonical_url(r["url"]), ""))
    pulse = pulse_from_daily_page(day)
    cited = set(pulse_cited_urls(pulse, rows))
    before = old.build_homepage_layout([dict(r) for r in rows])
    after = new_layout.build_homepage_layout([dict(r) for r in rows], daily_summary=pulse)
    print(f"\n=== {day}  ({len(rows)} candidates, Pulse {'found' if pulse else 'missing'}, "
          f"{len(cited)} Pulse-cited) ===")
    for label, lay in (("BEFORE", before), ("AFTER", after)):
        print(f"{label} email top {TOP_N} (1 = Lead):")
        for i, a in enumerate(email_top(lay), 1):
            print(_row(i, a, cited))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("days", nargs="+")
    ap.add_argument("--before-ref", default="HEAD", help="git ref for the 'before' layout")
    args = ap.parse_args(argv)
    old = load_old_layout(args.before_ref)
    for day in args.days:
        replay(day, old)
    return 0


if __name__ == "__main__":
    sys.exit(main())
