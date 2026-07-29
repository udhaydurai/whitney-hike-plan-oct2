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

echo "── rebuilding data from the Garmin digest"
python3 build/rebuild_data.py

echo "── building the dashboard"
python3 build/dashboard.py

echo "── assembling site/"
python3 build/site.py

echo "── verifying on a 390px viewport, offline included"
python3 tools/verify_site.py

if [[ -z "$(git status --porcelain)" ]]; then
  echo "── nothing changed, nothing to publish"
  exit 0
fi

git add -A
git commit -q -m "$MSG"
git push -q origin HEAD
echo "── published: $MSG"
echo "   the live site updates within about a minute"
