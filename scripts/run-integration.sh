#!/usr/bin/env bash
# Run the CareerVault integration suite (ADR-042).
#
# Tiers are separated by what a run *costs*, because the suite that costs nothing is the one that
# actually gets run. A uniform suite that exercises the résumé agent costs real money every time —
# which makes it a suite people avoid rather than use.
#
#   ./scripts/run-integration.sh                 local + cloud            $0
#   ./scripts/run-integration.sh --bedrock       + real Haiku calls       ~$0.01
#   ./scripts/run-integration.sh --expensive     + a Sonnet résumé run    ~$0.11
#   ./scripts/run-integration.sh --all           everything               ~$0.12
#
# Anything unavailable (Docker down, no AWS creds) skips with a reason rather than failing.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

WITH_BEDROCK=0
WITH_EXPENSIVE=0
PYTEST_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --bedrock)   WITH_BEDROCK=1 ;;
    --expensive) WITH_EXPENSIVE=1 ;;
    --all)       WITH_BEDROCK=1; WITH_EXPENSIVE=1 ;;
    *)           PYTEST_ARGS+=("$arg") ;;
  esac
done

# Deselect the paid tiers unless explicitly opted in. A marker expression rather than paths, so a
# paid test is still skipped if someone files it in the wrong directory.
MARKER_EXPR=""
if [[ $WITH_BEDROCK -eq 0 ]]; then
  MARKER_EXPR="not bedrock"
fi
if [[ $WITH_EXPENSIVE -eq 0 ]]; then
  MARKER_EXPR="${MARKER_EXPR:+$MARKER_EXPR and }not expensive"
fi

# CareerVault shares an SSO login with a second project in a *different* account, so the profile is
# pinned rather than inherited. Only matters for the cloud tiers; harmless for local.
export AWS_PROFILE="${AWS_PROFILE:-careervault-dev}"

VENV="${REPO_ROOT}/.venv-test"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r tests/requirements-dev.txt

# DynamoDB Local backs the free `local` tier. Started here rather than left to the developer so
# that "one command" is true; left running afterwards so repeat runs stay fast.
DDB_CONTAINER="careervault-ddb-local"
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if ! docker ps --format '{{.Names}}' | grep -qx "$DDB_CONTAINER"; then
    echo "Starting DynamoDB Local ($DDB_CONTAINER)..."
    docker rm -f "$DDB_CONTAINER" >/dev/null 2>&1 || true
    # `|| echo` matters under `set -e`: port 8000 is a common local port, and a bare failing
    # command here would abort before pytest ran at all — taking the cloud tier, which needs no
    # Docker, down with it and contradicting this script's own "skips with a reason" contract.
    docker run -d --name "$DDB_CONTAINER" -p 8000:8000 amazon/dynamodb-local >/dev/null \
      || echo "Could not start DynamoDB Local — the 'local' tier will skip." >&2
    for _ in $(seq 1 30); do
      curl -s -o /dev/null http://localhost:8000 && break
      sleep 0.5
    done
  fi
else
  echo "Docker unavailable — the 'local' tier will skip." >&2
fi

echo "Running integration tests${MARKER_EXPR:+ (-m \"$MARKER_EXPR\")}..."

# Built as an array rather than interpolated: under `set -u`, "${ARR[@]:-}" on an empty array
# expands to one empty-string argument, which pytest reads as a path and quietly widens collection
# to the whole repo — it ran the unit suite too until this was fixed.
CMD=("$VENV/bin/python" -m pytest tests/integration -q)
if [[ -n "$MARKER_EXPR" ]]; then
  CMD+=(-m "$MARKER_EXPR")
fi
if [[ ${#PYTEST_ARGS[@]} -gt 0 ]]; then
  CMD+=("${PYTEST_ARGS[@]}")
fi

exec "${CMD[@]}"
