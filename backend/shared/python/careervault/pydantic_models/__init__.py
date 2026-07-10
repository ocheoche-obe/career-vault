"""Pydantic entity + tool-input schemas for CareerVault (Section 2.7, 3.1, 3.2).

``profile`` landed with the auth slice; ``entry``, ``tools``, and ``conversation`` with the
chat + entry-ingestion slice. ``goals`` and the resume-agent tool schemas follow with their
respective Lambdas.
"""

from .conversation import ConversationMessage, build_message
from .entry import (
    ENTRY_TYPES,
    AwardEntry,
    CertEntry,
    EducationEntry,
    Entry,
    HobbyEntry,
    JobEntry,
    MilestoneEntry,
    ProjectEntry,
    VolunteerEntry,
    embedding_input_text,
    resolve_event_date,
    to_entry_item,
    utcnow_iso,
    validate_entry,
)
from .profile import Profile, Settings, default_profile
from .tools import CLARIFICATION_REASONS, build_tool_config

__all__ = [
    # profile
    "Profile",
    "Settings",
    "default_profile",
    # entry
    "ENTRY_TYPES",
    "Entry",
    "JobEntry",
    "ProjectEntry",
    "MilestoneEntry",
    "CertEntry",
    "AwardEntry",
    "EducationEntry",
    "VolunteerEntry",
    "HobbyEntry",
    "validate_entry",
    "resolve_event_date",
    "embedding_input_text",
    "to_entry_item",
    "utcnow_iso",
    # conversation
    "ConversationMessage",
    "build_message",
    # tools
    "build_tool_config",
    "CLARIFICATION_REASONS",
]
