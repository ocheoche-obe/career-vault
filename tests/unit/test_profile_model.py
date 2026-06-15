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
