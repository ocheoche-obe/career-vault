"""Pydantic entity + tool-input schemas for CareerVault (Section 2.7, 3.1, 3.2).

Only ``profile`` exists in the first vertical slice; ``entries``, ``goals``, ``conversation``,
and ``tool_inputs`` modules land as their respective Lambdas are built.
"""

from .profile import Profile, Settings, default_profile

__all__ = ["Profile", "Settings", "default_profile"]
