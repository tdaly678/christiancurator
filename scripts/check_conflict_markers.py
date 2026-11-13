#!/usr/bin/env python3
"""Fail when any tracked file contains git conflict markers.

On Nov 13 2026 the daily run's `git pull --rebase --autostash` hit a conflict
when it popped the stash, and the workflow committed and pushed docs/index.html
with "<<<<<<< Updated upstream" / "=======" / ">>>>>>> Stashed changes" in the
News column of the live homepage. This check runs in the daily workflow's commit
step (scripts/commit_daily_run.sh) before every push, and by hand before any push.

A file is flagged when a line starts with "<<<<<<< " or ">>>>>>> " (or is exactly
"<<<<<<<" / ">>>>>>>"). A bare "=======" line is reported only in a file that
also has one of those, since it is legal on its own (a Markdown heading rule).
Binary files are skipped.

    python scripts/check_conflict_markers.py            # every tracked file in the current repo
    python scripts/check_conflict_markers.py PATH ...   # only these files

Exit 1 when markers are found, else 0.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

EDGE_RE = re.compile(r"^(<{7}|>{7})(?: |$)")
MIDDLE_RE = re.compile(r"^={7}$")


def find_markers(text: str) -> list[tuple[int, str]]:
    """[(line number, line)] for conflict marker lines; [] when there is no start/end marker."""
    hits = []
    has_edge = False
    for n, line in enumerate(text.splitlines(), 1):
        line = line.rstrip("\r")
        if EDGE_RE.match(line):
            has_edge = True
            hits.append((n, line))
        elif MIDDLE_RE.match(line):
            hits.append((n, line))
    return hits if has_edge else []


def repo_root() -> Path:
    """Top of the git work tree containing the current directory."""
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True,
                         capture_output=True, text=True).stdout.strip()
    return Path(out)


def tracked_files(root: Path | None = None) -> list[Path]:
    root = root or repo_root()
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True,
                         capture_output=True).stdout
    return [root / p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def scan(paths: list[Path]) -> dict[Path, list[tuple[int, str]]]:
    found = {}
    for path in paths:
        try:
            data = path.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            continue
        if b"\0" in data[:8192]:
            continue
        hits = find_markers(data.decode("utf-8", "replace"))
        if hits:
            found[path] = hits
    return found


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    paths = [Path(a).resolve() for a in args] if args else tracked_files()
    root = repo_root()
    found = scan(paths)
    if not found:
        print(f"No conflict markers in {len(paths)} files.")
        return 0
    for path, hits in found.items():
        rel = path.relative_to(root) if path.is_relative_to(root) else path
        for n, line in hits:
            print(f"::error file={rel},line={n}::conflict marker: {line[:60]}")
    print(f"Conflict markers in {len(found)} file(s); do not commit or push.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
