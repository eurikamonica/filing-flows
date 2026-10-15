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
cp ../"$media"/x/*.png ../"$media"/x/*.gif x/ 2>/dev/null || true
cp ../"$media"/x/*-state.json x/ 2>/dev/null || true
git add -A
git -c user.name=filing-flows -c user.email=actions@users.noreply.github.com commit -qm "post images $(date -u +%Y-%m-%dT%H:%MZ)" || true
# Post to X, the engagement posts and the movers all write here: replay this commit on top if another run pushed first
for attempt in 1 2 3 4; do
  if git push -q origin HEAD:media; then break; fi
  [ "$attempt" = 4 ] && { echo "::error::media branch push failed"; exit 1; }
  sleep $((attempt * 5))
  git fetch -q --depth 20 origin media
  git -c user.name=filing-flows -c user.email=actions@users.noreply.github.com rebase -q -X theirs FETCH_HEAD || { git rebase --abort; exit 1; }
done
cd ..
python -m pipeline.buffer --site "$media" --site-url "https://raw.githubusercontent.com/${GITHUB_REPOSITORY}/media"
