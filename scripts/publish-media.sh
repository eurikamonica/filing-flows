#!/usr/bin/env bash
# Publish media/x/ (chart PNGs + small state files) on the "media" branch, then queue media/x/pending.json in Buffer.
# Used by post-to-x.yml, engage.yml, movers.yml and scan.yml. Needs GITHUB_TOKEN, GITHUB_REPOSITORY, BUFFER_API_KEY.
# Buffer's API allowance is small (free plan: 1,000 requests per channel per 30 days, shared by every workflow), so
# pipeline/buffer.py keeps x/buffer-state.json on the media branch — the X channel, the limits Buffer reported, when
# to try again after a 429 or a full queue, and the threads still waiting — and this script pushes it back after.
set -euo pipefail
media="${MEDIA_DIR:-media}"
[ -f "$media/x/pending.json" ] || { echo "no post was made"; exit 0; }
rm -rf media-branch && mkdir media-branch && cd media-branch
git init -q -b media
git remote add origin "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
git fetch -q --depth 1 origin media 2>/dev/null && git checkout -q media || true
mkdir -p x
cp ../"$media"/x/*.png ../"$media"/x/*.gif x/ 2>/dev/null || true
for f in ../"$media"/x/*-state.json; do       # this run's engagement cooldowns; the Buffer state is the branch's own
  if [ -f "$f" ] && [ "$(basename "$f")" != buffer-state.json ]; then cp "$f" x/; fi
done
push_media() {
  git add -A
  git -c user.name=filing-flows -c user.email=actions@users.noreply.github.com commit -qm "$1" || return 0
  # Post to X, the engagement posts and the movers all write here: replay this commit on top if another run pushed first
  for attempt in 1 2 3 4; do
    if git push -q origin HEAD:media; then return 0; fi
    [ "$attempt" = 4 ] && { echo "::error::media branch push failed"; return 1; }
    sleep $((attempt * 5))
    git fetch -q --depth 20 origin media
    git -c user.name=filing-flows -c user.email=actions@users.noreply.github.com rebase -q -X theirs FETCH_HEAD || { git rebase --abort; return 1; }
  done
}
push_media "post images $(date -u +%Y-%m-%dT%H:%MZ)"
cd ..
rc=0
python -m pipeline.buffer --site "$media" --site-url "https://raw.githubusercontent.com/${GITHUB_REPOSITORY}/media" \
  --state media-branch/x/buffer-state.json || rc=$?
if [ -f media-branch/x/buffer-state.json ]; then
  (cd media-branch && push_media "buffer state $(date -u +%Y-%m-%dT%H:%MZ)") || echo "::warning::the Buffer state was not saved; the next run reads the previous one"
fi
exit $rc
