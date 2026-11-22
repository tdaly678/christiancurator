#!/usr/bin/env python3
"""Seed data/sitemap_lastmod.json from git history.

For every page the sitemap dates by content (About, the /topics/ and /voices/
hubs, topic pages, voice pages), find the date of the oldest commit in the
newest run of commits whose visible content fingerprint matches the working
tree (frontend/sitemap_lastmod.content_fingerprint). Markup-only sweeps (CSS,
nav, favicon) leave the fingerprint alone, so they do not move the date. A
page whose content differs from HEAD gets today.

Needs full git history (the daily run's shallow checkout cannot do this; it
only carries the dates forward). Rerun after a history rewrite or to reset.

    python scripts/seed_sitemap_lastmod.py            # print a summary
    python scripts/seed_sitemap_lastmod.py --write    # write the state file
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from frontend.sitemap_lastmod import content_fingerprint  # noqa: E402

BASE = "https://www.christiancurator.com"
STATE = ROOT / "data" / "sitemap_lastmod.json"


def pages() -> list[Path]:
    docs = ROOT / "docs"
    out = [docs / "about" / "index.html", docs / "topics" / "index.html", docs / "voices" / "index.html"]
    out += sorted((docs / "topics").glob("*/index.html"))
    out += sorted((docs / "voices").glob("*/index.html"))
    return [p for p in out if p.exists()]


def url_for(path: Path) -> str:
    rel = path.relative_to(ROOT / "docs").parent.as_posix()
    return f"{BASE}/{rel}/"


class Blobs:
    def __init__(self):
        self.proc = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT,
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, spec: str) -> str | None:
        self.proc.stdin.write(spec.encode() + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().decode().split()
        if len(header) < 3 or header[1] != "blob":
            return None
        data = self.proc.stdout.read(int(header[2]))
        self.proc.stdout.read(1)
        return data.decode("utf-8", errors="replace")


def seed_one(path: Path, blobs: Blobs, today: str) -> str:
    rel = path.relative_to(ROOT).as_posix()
    current = content_fingerprint(path.read_text(encoding="utf-8", errors="replace"))
    log = subprocess.run(["git", "log", "--format=%H %cs", "--", rel], cwd=ROOT,
                         capture_output=True, text=True).stdout.split("\n")
    when = None
    for line in log:
        if not line.strip():
            continue
        sha, day = line.split()
        html = blobs.read(f"{sha}:{rel}")
        if html is None or content_fingerprint(html) != current:
            break
        when = day
    return when or today


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    shallow = subprocess.run(["git", "rev-parse", "--is-shallow-repository"], cwd=ROOT,
                             capture_output=True, text=True).stdout.strip()
    if shallow == "true":
        print("Shallow clone: run this with full history.")
        return 1
    today = date.today().isoformat()
    blobs = Blobs()
    state = {}
    for path in pages():
        html = path.read_text(encoding="utf-8", errors="replace")
        state[url_for(path)] = [content_fingerprint(html), seed_one(path, blobs, today)]
    by_month = Counter(v[1][:7] for v in state.values())
    print(f"{len(state)} pages; by month: " + ", ".join(f"{m}={n}" for m, n in sorted(by_month.items())))
    print(f"dated today: {sum(1 for v in state.values() if v[1] == today)}")
    if args.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(dict(sorted(state.items())), indent=0, sort_keys=True) + "\n",
                         encoding="utf-8")
        print(f"wrote {STATE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
