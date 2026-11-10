#!/usr/bin/env bash
# The Close forecast's two branches (app/closecast.py):
#   forecast-live    forecast.json and closes.json, one commit force-pushed each run (the hub reads them from
#                    raw.githubusercontent.com: docs/closecast.js)
#   forecast-ledger  the official freezes (9:45, 12:00, 15:00 New York), filed once per slot and scored once their dates
#                    have closed. Never force-pushed: a push that loses a race reads the branch again and tries anew.
#
#   scripts/forecast-publish.sh [DIR]     DIR (default fcout): what app/closecast.py wrote — forecast.json, closes.json,
#                                         and when the ledger is due, ledger_due (the slot) and freeze.json
#   env: PUSH_URL (https://x-access-token:…@github.com/owner/repo.git), CACHE (closecast's cache, default fc)
set -u
dir=${1:-fcout}
cache=${CACHE:-fc}
here=$(cd "$(dirname "$0")/.." && pwd)
who=(-c user.name="filing-flows" -c user.email="actions@users.noreply.github.com")
[ -f "$dir/forecast.json" ] || { echo "no forecast to publish"; exit 1; }
pub=$(mktemp -d)
cp "$dir/forecast.json" "$pub/"
[ -f "$dir/closes.json" ] && cp "$dir/closes.json" "$pub/"
printf '%s\n' '# forecast-live (data only)' '' "forecast.json and closes.json of the hub's Close forecast, force-pushed as one commit each run by" \
  '.github/workflows/intraday.yml and moves-close.yml (app/closecast.py, scripts/forecast-publish.sh).' > "$pub/README.md"
ok=0
if ( cd "$pub" && git init -q -b forecast-live && git remote add origin "$PUSH_URL" && git add -A && git "${who[@]}" commit -q -m "forecast $(date -u +%Y-%m-%dT%H:%MZ)" ); then
  for i in 1 2 3; do if git -C "$pub" push -q --force origin forecast-live; then ok=1; break; fi; sleep $((i * 5)); done
fi
rm -rf "$pub"
[ "$ok" = 1 ] || echo "::warning::forecast-live could not be pushed"
[ -f "$dir/ledger_due" ] || exit 0
slot=$(cat "$dir/ledger_due")
for i in 1 2 3; do
  lg=$(mktemp -d)
  if git ls-remote --exit-code --heads "$PUSH_URL" forecast-ledger >/dev/null 2>&1; then
    git clone -q --depth 1 --branch forecast-ledger "$PUSH_URL" "$lg/r" || { rm -rf "$lg"; sleep $((i * 5)); continue; }
  else
    mkdir -p "$lg/r" && git -C "$lg/r" init -q -b forecast-ledger && git -C "$lg/r" remote add origin "$PUSH_URL"
  fi
  args=(ledger --root "$lg/r" --closes "$dir/closes.json")
  [ -f "$dir/freeze.json" ] && args+=(--freeze "$dir/freeze.json")
  python "$here/disclosures/app/closecast.py" "${args[@]}" || { rm -rf "$lg"; echo "::warning::the ledger could not be built ($slot)"; exit 1; }
  if ( cd "$lg/r" && git add -A && { git diff --cached --quiet || git "${who[@]}" commit -q -m "ledger: $slot"; } && git push -q origin HEAD:forecast-ledger ); then
    python "$here/disclosures/app/closecast.py" frozen --cache "$cache" --slot "$slot"
    rm -rf "$lg"
    echo "ledger: $slot filed"
    exit 0
  fi
  rm -rf "$lg"
  sleep $((i * 5))
done
echo "::warning::forecast-ledger could not be updated ($slot)"
exit 1
