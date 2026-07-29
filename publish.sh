#!/usr/bin/env bash
# Rebuild and publish. Safe to run repeatedly; a no-op build produces no commit.
#
#   ./publish.sh "dashboard: Aug 1 hike"
#
# Expects the remote to already carry credentials — either a git credential helper
# or an origin URL containing a token. The token is never written into this file.
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-dashboard rebuild}"

# Generated files are never a real conflict: they are rebuilt from data/ a few lines
# below. .gitattributes routes them to this driver, which keeps our copy and reports
# success, so a rebase never stops on 130 KB of generated HTML. Configured here because
# a fresh clone has no .git/config of ours.
git config merge.generated.driver 'true'
git config merge.generated.name 'keep ours, then regenerate'

# Two writers can run on the same evening: the nightly scheduled task and whatever
# session is running now. Nightly check-ins go to data/daily/<date>.json — one file per
# date, so they cannot collide by construction. This rebase covers the rest. The one
# thing never to do here is --force: it would silently delete the other side's work.
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  FETCH="https://x-access-token:${GITHUB_TOKEN}@github.com/udhaydurai/whitney-hike-plan-oct2.git"
else
  FETCH="origin"
fi
echo "── checking for changes pushed by another session"
if git fetch -q "$FETCH" main 2>/dev/null; then
  if ! git merge-base --is-ancestor FETCH_HEAD HEAD 2>/dev/null; then
    echo "   remote has commits this checkout does not — rebasing onto them"
    if ! git -c user.email=udhaydurai@users.noreply.github.com \
           -c user.name="Udhay Durai" rebase FETCH_HEAD; then
      git rebase --abort 2>/dev/null || true
      echo "   STOP: the rebase conflicts. Both sides edited the same records."
      echo "   Resolve by hand — do not force-push, it would delete the other side's work."
      exit 1
    fi
  fi
fi

echo "── rebuilding data from the Garmin digest"
python3 build/rebuild_data.py

echo "── building the dashboard"
python3 build/dashboard.py

echo "── assembling docs/ (the published folder)"
python3 build/site.py

echo "── verifying on a 390px viewport, offline included"
python3 tools/verify_site.py

if [[ -z "$(git status --porcelain)" ]]; then
  echo "── nothing changed, nothing to publish"
  exit 0
fi

git add -A
git -c user.email=udhaydurai@users.noreply.github.com -c user.name="Udhay Durai" commit -q -m "$MSG"

# A scheduled session gets the credential as GITHUB_TOKEN and pushes over a one-shot
# URL, so the token is never written into .git/config. Interactively, fall back to
# whatever credential helper is already configured.
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  REMOTE="https://x-access-token:${GITHUB_TOKEN}@github.com/udhaydurai/whitney-hike-plan-oct2.git"
  git push -q "$REMOTE" HEAD:main 2>&1 | sed 's/github_pat_[A-Za-z0-9_]*/[token]/g'
else
  git push -q origin HEAD:main
fi
echo "── published: $MSG"
echo "   the live site updates within about a minute"
