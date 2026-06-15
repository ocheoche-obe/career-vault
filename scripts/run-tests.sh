#!/usr/bin/env bash
# Run backend unit tests in a throwaway venv. boto3 is provided by the Lambda runtime in
# production (not bundled in the layer) but is installed here so ddb_helpers imports locally.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV="${REPO_ROOT}/.venv-test"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r tests/requirements-dev.txt
"$VENV/bin/python" -m pytest tests/unit -q
