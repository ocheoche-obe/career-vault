"""Unit tests for the Profile Pydantic model + default factory."""

from careervault.pydantic_models.profile import Profile, Settings, default_profile


def test_default_profile_shape():
    profile = default_profile("alice-sub-123", "alice@example.com")
    assert isinstance(profile, Profile)
    assert profile.PK == "USER#alice-sub-123"
    assert profile.SK == "PROFILE"
    assert profile.entity_type == "PROFILE"
    assert profile.email == "alice@example.com"
    assert profile.skills == []
    assert profile.portfolio_links == {}
    assert profile.created_at == profile.updated_at


def test_default_profile_settings_defaults():
    settings = default_profile("u", "e@x.com").settings
    assert isinstance(settings, Settings)
    assert settings.checkin_cadence == "weekly"
    assert settings.checkin_paused is False
    assert settings.preferred_template_id is None


def test_profile_model_dump_is_json_serializable():
    import json

    dumped = default_profile("u", "e@x.com").model_dump()
    # Must round-trip through json.dumps (it's what settings_lambda returns in the body).
    assert json.loads(json.dumps(dumped))["settings"]["checkin_cadence"] == "weekly"


# --- B-008: identity fields + the write-side contract ----------------------------------------

from careervault.pydantic_models.profile import ProfileUpdate  # noqa: E402
import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402


def test_profile_carries_the_resume_identity_fields():
    """Absent through slice 6, which is why résumés rendered the literal word "Résumé"."""
    profile = default_profile("u", "e@x.com")
    assert profile.name is None
    assert profile.location is None


def test_profile_update_forbids_server_owned_fields():
    for forbidden in ({"email": "a@b.c"}, {"PK": "USER#x"}, {"SK": "PROFILE"}, {"created_at": "x"}):
        with pytest.raises(ValidationError):
            ProfileUpdate.model_validate(forbidden)


def test_profile_update_exclude_unset_is_what_makes_it_partial():
    update = ProfileUpdate.model_validate({"name": "Ada"})
    assert update.model_dump(exclude_unset=True) == {"name": "Ada"}


def test_profile_update_distinguishes_omitted_from_explicit_null():
    """Omitted means 'leave alone'; explicit null means 'clear'. The API depends on the difference."""
    assert ProfileUpdate.model_validate({}).model_dump(exclude_unset=True) == {}
    assert ProfileUpdate.model_validate({"phone": None}).model_dump(exclude_unset=True) == {"phone": None}


def test_profile_update_enforces_length_caps():
    with pytest.raises(ValidationError):
        ProfileUpdate.model_validate({"name": "x" * 121})
