"""Every workflow job that runs repo Python installs requirements.txt.

Nov 14 2026: the Topic Quality Gate installed only what it thought it needed,
check_topic_quality.py imported frontend (jinja2), and six runs crashed with
ModuleNotFoundError. Installing the whole requirements file in every job that
runs repo code keeps a new import from breaking a workflow that was not touched.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
# Jobs that run only these scripts may skip pip: they use the standard library.
STDLIB_ONLY = {"scripts/morning_guard.py"}
RUNS_REPO_PYTHON = re.compile(r"python3? (?:-c |- <<|main\.py|scripts/[\w/]+\.py)")


def jobs(text):
    """{job name: job text} for a workflow file, split on two-space job keys."""
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([\w-]+):\s*$", body)
    return dict(zip(parts[1::2], parts[2::2]))


def test_every_python_job_installs_requirements():
    missing = []
    for wf in WORKFLOWS:
        for name, job in jobs(wf.read_text()).items():
            scripts = set(re.findall(r"scripts/[\w/]+\.py", job))
            if not RUNS_REPO_PYTHON.search(job):
                continue
            if scripts and scripts <= STDLIB_ONLY and "main.py" not in job:
                continue
            if "pip install -r requirements.txt" not in job:
                missing.append(f"{wf.name}:{name}")
    assert not missing, f"jobs run repo Python without pip install -r requirements.txt: {missing}"


def test_stdlib_only_scripts_import_only_the_standard_library():
    for rel in STDLIB_ONLY:
        tree = ast.parse((ROOT / rel).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                assert top in sys.stdlib_module_names, f"{rel} imports {name}"


def test_third_party_imports_are_in_requirements():
    """Every third-party module the daily scripts import is listed (by its pip name)."""
    pip_names = {"bs4": "beautifulsoup4", "dotenv": "python-dotenv", "google": "google-auth",
                 "yaml": "pyyaml", "PIL": "pillow"}
    reqs = {re.split(r"[<>=\s]", line)[0].lower()
            for line in (ROOT / "requirements.txt").read_text().splitlines() if line.strip()}
    daily = (ROOT / ".github" / "workflows" / "daily_run.yml").read_text()
    files = [ROOT / "main.py"] + [ROOT / p for p in set(re.findall(r"scripts/[\w/]+\.py", daily))]
    files += [p for d in ("curator", "fetcher", "frontend", "output") for p in (ROOT / d).glob("*.py")]
    local = {"curator", "fetcher", "frontend", "output", "scripts", "main", "config"}
    local |= {p.stem for p in (ROOT / "scripts").glob("*.py")}
    missing = set()
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top in sys.stdlib_module_names or top in local:
                    continue
                if pip_names.get(top, top).lower() not in reqs:
                    missing.add(f"{path.relative_to(ROOT)}: {top}")
    assert not missing, sorted(missing)
