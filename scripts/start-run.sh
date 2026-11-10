#!/usr/bin/env bash
# Start a workflow run and see that it gets going. GitHub now and then fails a run as it starts (no job at all): on
# Nov 9, 2026 the intraday move odds relay (intraday.yml) and the X-post watch relay both broke on such a start and
# stayed down for hours, their schedules firing late. A run that fails as it starts is started again (four tries, the
# answer looked at for two minutes each time); one waiting for its concurrency group counts as started.
#
#   scripts/start-run.sh WORKFLOW [-f key=value …]        env: GH_TOKEN, GITHUB_REPOSITORY, GITHUB_REF_NAME
set -u
wf=$1
shift
for attempt in 1 2 3 4; do
  t0=$(date -u -d '-30 seconds' +%Y-%m-%dT%H:%M:%SZ)
  if gh workflow run "$wf" -R "$GITHUB_REPOSITORY" --ref "${GITHUB_REF_NAME:-main}" "$@"; then
    s=none
    for _ in $(seq 1 12); do
      sleep 10
      s=$(gh run list -R "$GITHUB_REPOSITORY" --workflow "$wf" --event workflow_dispatch --limit 10 --json status,conclusion,createdAt \
            --jq "[.[] | select(.createdAt >= \"$t0\")] | sort_by(.createdAt) | last | if . == null then \"none\" else .status + \" \" + (.conclusion // \"\") end" \
            2>/dev/null || echo none)
      case "$s" in
        "in_progress "*|"completed success"|"completed skipped"|"completed cancelled") echo "$wf: started ($s)"; exit 0 ;;
        "completed "*) echo "::warning::$wf failed as it started ($s), attempt $attempt"; break ;;
      esac
    done
    case "$s" in
      "queued "*|"pending "*|"waiting "*|"requested "*) echo "$wf: waiting to start ($s)"; exit 0 ;;
    esac
  else
    echo "::warning::starting $wf failed (attempt $attempt)"
  fi
  sleep $((attempt * 15))
done
echo "::error::$wf could not be started"
exit 1
