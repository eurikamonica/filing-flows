#!/usr/bin/env bash
# Publish media/x/ (chart PNGs + small state files) on the "media" branch, then queue media/x/pending.json in Buffer.
# Used by post-to-x.yml and reddit-trends.yml. Needs GITHUB_TOKEN, GITHUB_REPOSITORY, BUFFER_API_KEY.
set -euo pipefail
media="${MEDIA_DIR:-media}"
[ -f "$media/x/pending.json" ] || { echo "no post was made"; exit 0; }
rm -rf media-branch && mkdir media-branch && cd media-branch
git init -q -b media
git remote add origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
git fetch -q --depth 1 origin media 2>/dev/null && git checkout -q media || true
mkdir -p x
cp ../"$media"/x/*.png x/ 2>/dev/null || true
cp ../"$media"/x/*-state.json x/ 2>/dev/null || true
git add -A
git -c user.name=filing-flows -c user.email=actions@users.noreply.github.com commit -qm "post images $(date -u +%Y-%m-%dT%H:%MZ)" || true
git push -q origin HEAD:media
cd ..
python -m pipeline.buffer --site "$media" --site-url "https://raw.githubusercontent.com/${GITHUB_REPOSITORY}/media"
