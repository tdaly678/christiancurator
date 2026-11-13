#!/usr/bin/env bash
# Commit the daily run's output and push it on top of whatever landed on main
# during the run, without ever pushing git conflict markers.
#
#   scripts/commit_daily_run.sh "commit message" PATH...
#
# Order: stage PATHs and commit FIRST, set aside any other local edits (they
# were never committed, and are left in a stash), then fetch and rebase the run
# commit onto origin/main with no autostash. If the rebase conflicts, it is
# aborted and the run commit is merged onto origin/main instead, with the run's
# side winning the conflicting hunks (every file it commits is generated output
# from today's data); the conflicted paths are printed as a ::warning. If that
# merge also fails, exit 1 and push nothing. Before every push,
# scripts/check_conflict_markers.py must pass.
#
# Replaces `git pull --rebase --autostash` in daily_run.yml, which on
# Nov 13 2026 committed a conflicted stash pop and pushed "<<<<<<< Updated
# upstream" into the live homepage. Tests: tests/test_commit_daily_run.py.
set -euo pipefail

msg="$1"
shift
here="$(cd "$(dirname "$0")" && pwd)"
remote="${CC_REMOTE:-origin}"
branch="${CC_BRANCH:-main}"

python3 "$here/check_conflict_markers.py"

git add -- "$@"
if git diff --staged --quiet; then
  echo "Nothing to commit."
  exit 0
fi
git commit -q -m "$msg"
run_commit="$(git rev-parse HEAD)"

# Uncommitted leftovers would block the rebase; they are not part of the run's output.
if ! git diff --quiet; then
  git stash push -q -m "daily run leftovers (not committed)"
  echo "Set aside uncommitted edits outside the commit list in a stash."
fi

for attempt in 1 2 3; do
  git fetch -q "$remote" "$branch"
  upstream="$(git rev-parse FETCH_HEAD)"
  if git rebase -q "$upstream"; then
    echo "Rebased the run commit onto $remote/$branch."
  else
    conflicted="$(git diff --name-only --diff-filter=U | tr '\n' ' ')"
    git rebase --abort
    echo "::warning title=Daily run commit::rebase onto $remote/$branch conflicted in: ${conflicted}. Merging with today's output winning those hunks."
    git reset -q --hard "$upstream"
    if ! git merge -q --no-edit -X theirs -m "$msg (merge)" "$run_commit"; then
      git merge --abort || true
      git reset -q --hard "$run_commit"
      echo "::error title=Daily run commit::could not merge the run onto $remote/$branch; nothing pushed."
      exit 1
    fi
  fi

  if ! python3 "$here/check_conflict_markers.py"; then
    echo "::error title=Daily run commit::conflict markers after integrating $remote/$branch; nothing pushed."
    exit 1
  fi

  if git push -q "$remote" "HEAD:$branch"; then
    echo "Pushed $(git rev-parse --short HEAD) to $remote/$branch."
    exit 0
  fi
  echo "Push rejected (attempt $attempt); refetching."
  git reset -q --hard "$run_commit"
done

echo "::error title=Daily run commit::push rejected 3 times; nothing pushed."
exit 1
