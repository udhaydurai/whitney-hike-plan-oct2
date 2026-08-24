#!/usr/bin/env bash
# Rebuild and publish. Safe to run repeatedly; a no-op build produces no commit.
#
#   ./publish.sh "dashboard: Aug 1 hike"
#
# Credentials come from GITHUB_TOKEN when set (that is how the scheduled sessions run),
# otherwise from whatever credential helper is already configured. The token is never
# written into this file or into .git/config.
#
# ── Why the order below is what it is
#
# Two writers can run on the same evening: the nightly scheduled task and whatever
# interactive session is open. Three things make that safe, and all three are needed:
#
#   1. Nightly check-ins are written to data/daily/<date>.json — one file per date — so
#      the common case is two writers touching different paths, which git merges without
#      being asked. This is the fix that matters; the rest is belt and braces.
#   2. Generated artefacts (docs/, whitney-dashboard.html) are routed by .gitattributes
#      to a merge driver that keeps our copy and succeeds, because a conflict in 140 KB
#      of generated HTML carries no information — both sides are renderings of their own
#      inputs. They are then rebuilt from the merged data, which is the only version that
#      was ever correct. That is why the rebuild happens AFTER the rebase.
#   3. Commit before rebasing. An earlier version rebased first and failed every time on
#      a dirty tree — git rebase refuses to run with uncommitted changes, so the guard
#      that was supposed to prevent conflicts reported one on every single run.
#
# The one thing never to do here is --force. It resolves the symptom by deleting the
# other writer's work, and on this project the other writer is an unattended 9 pm job
# recording food that cannot be reconstructed afterwards.
set -euo pipefail
cd "$(dirname "$0")"

# -- Make the container able to verify before we rely on it.
#
# The build step below ends in tools/verify_site.py, which drives a real Chromium through
# Playwright, and a fresh session container has neither installed. Sourcing this here
# rather than leaving it to the caller is deliberate: a session that had to work the
# toolchain out for itself stopped before reaching the commit step, which looked from the
# outside like the data had failed to check in when in fact nothing had been written yet.
# Near-instant when the container is already set up. See tools/bootstrap_env.sh.
source tools/bootstrap_env.sh

MSG="${1:-dashboard rebuild}"
REPO="github.com/udhaydurai/whitney-hike-plan-oct2.git"
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  REMOTE="https://x-access-token:${GITHUB_TOKEN}@${REPO}"
else
  REMOTE="origin"
fi
GIT_ID=(-c user.email=udhaydurai@users.noreply.github.com -c user.name="Udhay Durai")

# a fresh clone has none of our config, so the generated-file driver is set every run
git config merge.generated.driver 'true'
git config merge.generated.name 'keep ours, then regenerate from data'

build() {
  echo "── rebuilding data from the Garmin digest"
  python3 build/rebuild_data.py >/dev/null
  echo "── building the dashboard"
  python3 build/dashboard.py | sed 's/^/   /'
  echo "── assembling docs/ (the published folder)"
  python3 build/site.py >/dev/null
  echo "── verifying on a 390px viewport, offline included"
  python3 tools/verify_site.py | tail -3
}

commit_all() {
  if [[ -z "$(git status --porcelain)" ]]; then
    return 1
  fi
  git add -A
  git "${GIT_ID[@]}" commit -q -m "$1"
  return 0
}

# ── 1. commit first, so the tree is clean enough to rebase
build
if ! commit_all "$MSG"; then
  echo "── nothing changed, nothing to publish"
  exit 0
fi

# ── 2. then reconcile with anything the other writer pushed, and push. One retry is
#       enough for a two-writer race; a second failure means something else is wrong and
#       should be looked at rather than looped over.
for attempt in 1 2; do
  git fetch -q "$REMOTE" main 2>/dev/null || true

  if ! git merge-base --is-ancestor FETCH_HEAD HEAD 2>/dev/null; then
    echo "── another session pushed first — rebasing onto it"
    if ! git "${GIT_ID[@]}" rebase FETCH_HEAD >/dev/null 2>&1; then
      # only generated files should ever conflict, and those are safe to take either way
      # because the rebuild below overwrites them from the merged data
      CONFLICTS=$(git diff --name-only --diff-filter=U)
      REAL=$(echo "$CONFLICTS" | grep -v '^docs/' | grep -v '^whitney-dashboard.html$' || true)
      if [[ -n "$REAL" ]]; then
        git rebase --abort 2>/dev/null || true
        echo "   STOP: a real conflict, not a generated one:"
        echo "$REAL" | sed 's/^/     /'
        echo "   Resolve by hand. Do not force-push — it deletes the other writer's work."
        exit 1
      fi
      git checkout --ours -- $CONFLICTS 2>/dev/null || true
      git add -- $CONFLICTS
      GIT_EDITOR=true git "${GIT_ID[@]}" rebase --continue >/dev/null 2>&1 || true
    fi
    # data changed underneath us, so the generated files are now stale by definition
    echo "── rebuilding on top of the merged data"
    build
    commit_all "$MSG (rebuilt after merging another session)" || true
  fi

  if git push -q "$REMOTE" HEAD:main 2>/dev/null; then
    echo "── published: $MSG"
    echo "   the live site updates within about a minute"
    exit 0
  fi
  echo "── push rejected, someone pushed in the meantime — retrying ($attempt of 2)"
done

echo "── STOP: could not push after two attempts. Nothing was lost; the commit is local."
exit 1
