"""Pytest config — make the shared layer importable as ``careervault`` during unit tests.

In Lambda the layer mounts at ``/opt/python/``; locally we add ``backend/shared/python`` to
``sys.path`` so ``import careervault...`` resolves the same way.

Environment defaults stand in for what the SAM template sets per-function. They are applied
before any test module imports ``careervault``, and no test ever reaches AWS: Bedrock and
DynamoDB are always faked, so the suite costs nothing to run (Section 4.6.2 cost note).
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_LAYER_SRC = _ROOT / "backend" / "shared" / "python"
if str(_LAYER_SRC) not in sys.path:
    sys.path.insert(0, str(_LAYER_SRC))

_ENV_DEFAULTS = {
    "CAREERVAULT_TABLE_NAME": "CareerVaultTable-test",
    "BEDROCK_HAIKU_MODEL_ID": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "BEDROCK_TITAN_EMBED_MODEL_ID": "amazon.titan-embed-text-v2:0",
    "ENVIRONMENT": "test",
    "POWERTOOLS_SERVICE_NAME": "test",
    "POWERTOOLS_METRICS_NAMESPACE": "CareerVault",
    # No X-Ray daemon under pytest; without this the Tracer tries to emit segments.
    "POWERTOOLS_TRACE_DISABLED": "1",
    "CORS_ALLOW_ORIGIN": "http://localhost:5173",
}
for _key, _value in _ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _value)
