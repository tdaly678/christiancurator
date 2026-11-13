"""Conflict markers never reach main (Nov 13 2026 homepage incident).

Covers scripts/check_conflict_markers.py and scripts/commit_daily_run.sh, the
daily workflow's commit step, against throwaway git repos.
"""
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
_spec = importlib.util.spec_from_file_location(
    "check_conflict_markers", os.path.join(ROOT, "scripts", "check_conflict_markers.py"))
ccm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ccm)

COMMIT_SCRIPT = os.path.abspath(os.path.join(ROOT, "scripts", "commit_daily_run.sh"))
START, MID, END = "<" * 7, "=" * 7, ">" * 7


def test_finds_stash_conflict():
    text = f"a\n{START} Updated upstream\nold\n{MID}\nnew\n{END} Stashed changes\nb\n"
    assert [n for n, _ in ccm.find_markers(text)] == [2, 4, 6]


def test_bare_rule_line_is_not_a_conflict():
    assert ccm.find_markers(f"Title\n{MID}\nbody\n") == []


def test_indented_or_inline_markers_are_ignored():
    assert ccm.find_markers(f"  {START} x\ncode = '{END} y'\n") == []


def test_repo_has_no_conflict_markers():
    found = ccm.scan(ccm.tracked_files(Path(ROOT).resolve()))
    assert not found, sorted(str(p) for p in found)


def _git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


@pytest.fixture
def repos(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))

    def clone(name):
        path = tmp_path / name
        _git(tmp_path, "clone", "-q", str(origin), str(path))
        _git(path, "config", "user.email", "t@example.com")
        _git(path, "config", "user.name", "t")
        return path

    seed = clone("seed")
    (seed / "docs").mkdir()
    (seed / "docs" / "index.html").write_text("".join(f"line {i}\n" for i in range(20)))
    (seed / "docs" / "other.json").write_text("{}\n")
    (seed / "notes.txt").write_text("keep\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    return origin, clone


def _run_commit(cwd, *paths):
    return subprocess.run(["bash", COMMIT_SCRIPT, "daily run", *paths], cwd=cwd,
                          capture_output=True, text=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


def _main_file(origin, path):
    return _git(origin, "show", f"main:{path}").stdout


def test_conflicting_upstream_edit_does_not_push_markers(repos):
    origin, clone = repos
    runner = clone("runner")
    # Overnight commit lands on main mid-run, editing the same homepage line.
    upstream = clone("upstream")
    page = (upstream / "docs" / "index.html").read_text().replace("line 10\n", "line 10 byline\n")
    (upstream / "docs" / "index.html").write_text(page)
    (upstream / "notes.txt").write_text("keep, edited upstream\n")
    _git(upstream, "commit", "-qam", "byline sweep")
    _git(upstream, "push", "-q", "origin", "HEAD:main")
    # The run regenerated the whole homepage and edits a file outside its list.
    (runner / "docs" / "index.html").write_text("".join(f"today {i}\n" for i in range(20)))
    (runner / "notes.txt").write_text("local scratch\n")

    result = _run_commit(runner, "docs/index.html")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "::warning" in result.stdout
    home = _main_file(origin, "docs/index.html")
    assert not ccm.find_markers(home)
    assert home == "".join(f"today {i}\n" for i in range(20))
    # The upstream commit is kept and the uncommitted scratch edit is not pushed.
    assert _main_file(origin, "notes.txt") == "keep, edited upstream\n"
    assert "byline sweep" in _git(origin, "log", "--format=%s", "main").stdout
    # HEAD~1..HEAD is the run's own change set (IndexNow reads it).
    changed = _git(runner, "diff", "--name-only", "HEAD~1", "HEAD").stdout.split()
    assert changed == ["docs/index.html"]


def test_clean_rebase_keeps_history_linear(repos):
    origin, clone = repos
    runner = clone("runner")
    upstream = clone("upstream")
    (upstream / "notes.txt").write_text("upstream\n")
    _git(upstream, "commit", "-qam", "unrelated")
    _git(upstream, "push", "-q", "origin", "HEAD:main")
    (runner / "docs" / "other.json").write_text('{"a": 1}\n')

    result = _run_commit(runner, "docs/other.json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "::warning" not in result.stdout
    assert _git(origin, "log", "--format=%s", "main").stdout.split("\n")[:2] == ["daily run", "unrelated"]
    assert _git(origin, "rev-list", "--merges", "main").stdout == ""


def test_markers_in_output_block_the_push(repos):
    origin, clone = repos
    runner = clone("runner")
    before = _git(origin, "rev-parse", "main").stdout
    (runner / "docs" / "index.html").write_text(f"{START} Updated upstream\na\n{MID}\nb\n{END} Stashed changes\n")

    result = _run_commit(runner, "docs/index.html")
    assert result.returncode == 1
    assert "conflict marker" in result.stdout
    assert _git(origin, "rev-parse", "main").stdout == before


def test_nothing_to_commit(repos):
    _, clone = repos
    runner = clone("runner")
    result = _run_commit(runner, "docs/index.html")
    assert result.returncode == 0
    assert "Nothing to commit" in result.stdout
