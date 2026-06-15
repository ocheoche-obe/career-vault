"""Pytest config — make the shared layer importable as ``careervault`` during unit tests.

In Lambda the layer mounts at ``/opt/python/``; locally we add ``backend/shared/python`` to
``sys.path`` so ``import careervault...`` resolves the same way.
"""

import sys
from pathlib import Path

_LAYER_SRC = Path(__file__).resolve().parents[1] / "backend" / "shared" / "python"
if str(_LAYER_SRC) not in sys.path:
    sys.path.insert(0, str(_LAYER_SRC))
