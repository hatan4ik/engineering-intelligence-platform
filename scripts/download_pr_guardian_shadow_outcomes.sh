#!/usr/bin/env bash
# Download every retained PR Guardian shadow closure artifact.
#
# Reads only: it lists completed pull_request_target runs of the closure
# workflow and downloads each run's still-retained export. An export past its
# retention window is skipped; any other gh failure (a token without
# actions:read, a rate limit, a network fault) fails the step rather than
# reporting an empty pilot as a result.
#
# Usage: bash scripts/download_pr_guardian_shadow_outcomes.sh [OUTPUT_DIR]
# Writes count=<n> to $GITHUB_OUTPUT when set, and — only when the count is
# zero — an explicit "nothing retained" note to $GITHUB_STEP_SUMMARY.
set -euo pipefail

OUTPUT_DIR="${1:-shadow-outcomes}"
WORKFLOW="${EIP_SHADOW_OUTCOME_WORKFLOW:-pr-guardian-shadow-outcome.yml}"
RUN_LIMIT="${EIP_SHADOW_OUTCOME_RUN_LIMIT:-100}"
ARTIFACT_PATTERN='pr-guardian-shadow-outcome*'

mkdir -p "$OUTPUT_DIR"

# The closure workflow only ever runs on pull_request_target, so that event is
# the filter. Do not filter on branch: a pull_request_target run's head_branch
# is the pull request's branch, not the default branch.
runs="$(gh run list \
  --workflow "$WORKFLOW" \
  --event pull_request_target \
  --status completed \
  --limit "$RUN_LIMIT" \
  --json databaseId \
  --jq '.[].databaseId')"

for run_id in $runs; do
  stderr_file="$(mktemp)"
  if gh run download "$run_id" \
    --pattern "$ARTIFACT_PATTERN" \
    --dir "$OUTPUT_DIR/$run_id" 2>"$stderr_file"; then
    rm -f "$stderr_file"
    continue
  fi
  detail="$(cat "$stderr_file")"
  rm -f "$stderr_file"
  if printf '%s' "$detail" | grep -qiE 'no artifact|no valid artifacts'; then
    # Expected: this run's export has passed its 14-day retention window.
    rmdir "$OUTPUT_DIR/$run_id" 2>/dev/null || true
    continue
  fi
  echo "gh run download failed for run $run_id: $detail" >&2
  exit 1
done

count="$(find "$OUTPUT_DIR" -type f -name '*.json' | wc -l | tr -d ' ')"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  echo "count=$count" >> "$GITHUB_OUTPUT"
fi

if [ "$count" -eq 0 ] && [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "## PR Guardian shadow report"
    echo
    echo "No retained \`pr-guardian-shadow-outcome\` artifacts were found, so no report was"
    echo "produced. This is not a result: the shadow pilot has either not run, or every closure"
    echo "export has passed its retention window."
  } >> "$GITHUB_STEP_SUMMARY"
fi

echo "retained pr-guardian-shadow-outcome artifacts: $count"
