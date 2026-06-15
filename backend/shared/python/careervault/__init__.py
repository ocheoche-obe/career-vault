"""CareerVault shared Lambda layer (``careervault-shared``).

Mounts at ``/opt/python/careervault/`` inside the Lambda runtime (ADR-023 / Section 5.2), so
handlers import via ``from careervault import ddb_helpers``, ``from careervault.observability
import logger``, etc. — the same paths whether running locally or deployed.
"""

from . import bedrock_client, ddb_helpers, observability

__all__ = ["bedrock_client", "ddb_helpers", "observability"]
