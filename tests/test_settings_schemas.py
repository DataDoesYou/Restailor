"""Test validation of ModelSettings schema and allowlist."""
from datetime import datetime
import pytest
from pydantic import ValidationError

from restailor.settings_schemas import (
    ModelSettings,
    get_allowed_models,
    get_models_by_provider,
    validate_model_id,
    get_default_model_for_role,
    resolve_effective_settings,
    get_model_upgrade_map,
    apply_model_upgrades,
)


def test_get_allowed_models():
    """Test that allowlist returns valid model IDs from config."""
    models = get_allowed_models()
    
    # Should return a set
    assert isinstance(models, set)
    
    # Should contain models from enabled providers (based on default config)
    # Note: Actual models depend on config/app.toml
    assert len(models) > 0
    
    # All entries should be non-empty strings
    for model_id in models:
        assert isinstance(model_id, str)
        assert len(model_id) > 0


def test_get_models_by_provider():
    """Test organized provider/role model mapping."""
    models = get_models_by_provider()
    
    assert isinstance(models, dict)
    
    # Should have at least one enabled provider
    assert len(models) > 0
    
    # Each provider should have role mappings
    for provider, roles in models.items():
        assert isinstance(provider, str)
        assert isinstance(roles, dict)
        # Should have at least one role
        assert len(roles) > 0


def test_validate_model_id():
    """Test model ID validation helper."""
    # Get a valid model from allowlist
    allowed = get_allowed_models()
    if allowed:
        valid_model = next(iter(allowed))
        assert validate_model_id(valid_model) is True
    
    # Invalid models should fail
    assert validate_model_id("fake-model-999") is False
    assert validate_model_id("") is False
    assert validate_model_id("../../etc/passwd") is False


def test_get_default_model_for_role():
    """Test default model retrieval."""
    for role in ["tailor", "fit", "judge"]:
        default = get_default_model_for_role(role)
        # Should return a string or None
        assert default is None or isinstance(default, str)
        
        # If returned, should be in allowlist
        if default:
            assert default in get_allowed_models()
    
    # Invalid role should return None
    assert get_default_model_for_role("invalid_role") is None


def test_model_settings_valid():
    """Test valid ModelSettings creation."""
    # Get valid models from allowlist
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    # Create valid settings
    settings = ModelSettings(
        multi_model_enabled=True,
        fit_models=[allowed[0]],
        tailor_models=[allowed[0]],
        judge_models=[allowed[0]],
        last_single_fit=allowed[0],
        last_single_tailor=allowed[0],
        last_single_judge=allowed[0],
        version=1,
    )
    
    assert settings.multi_model_enabled is True
    assert len(settings.fit_models) == 1
    assert settings.fit_models[0] == allowed[0]


def test_model_settings_invalid_model_in_list():
    """Test that invalid model IDs in lists are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        ModelSettings(
            multi_model_enabled=True,
            fit_models=["invalid-model-xyz"],
        )
    
    # Check that error mentions the invalid model
    assert "invalid-model-xyz" in str(exc_info.value).lower()


def test_model_settings_invalid_single_model():
    """Test that invalid single model selections are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        ModelSettings(
            multi_model_enabled=False,
            last_single_tailor="malicious-model-injection",
        )
    
    assert "malicious-model-injection" in str(exc_info.value).lower()


def test_model_settings_empty_lists():
    """Test that empty model lists are acceptable."""
    settings = ModelSettings(
        multi_model_enabled=True,
        fit_models=[],
        tailor_models=[],
        judge_models=[],
    )
    
    assert settings.fit_models == []
    assert settings.tailor_models == []
    assert settings.judge_models == []


def test_model_settings_none_single_models():
    """Test that None single model selections are acceptable."""
    settings = ModelSettings(
        multi_model_enabled=False,
        last_single_fit=None,
        last_single_tailor=None,
        last_single_judge=None,
    )
    
    assert settings.last_single_fit is None
    assert settings.last_single_tailor is None
    assert settings.last_single_judge is None


def test_model_settings_mixed_valid_invalid():
    """Test that mixing valid and invalid models in a list fails."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    with pytest.raises(ValidationError):
        ModelSettings(
            multi_model_enabled=True,
            tailor_models=[allowed[0], "fake-model-123"],
        )


def test_model_settings_injection_attempts():
    """Test that various injection attempts are blocked."""
    injection_attempts = [
        "../../../etc/passwd",
        "'; DROP TABLE users; --",
        "<script>alert('xss')</script>",
        "$(whoami)",
        "`rm -rf /`",
        "model' OR '1'='1",
    ]
    
    for malicious_input in injection_attempts:
        with pytest.raises(ValidationError):
            ModelSettings(
                multi_model_enabled=False,
                last_single_tailor=malicious_input,
            )


def test_model_settings_defaults():
    """Test default values are set correctly."""
    settings = ModelSettings()
    
    assert settings.multi_model_enabled is False
    assert settings.fit_models == []
    assert settings.tailor_models == []
    assert settings.judge_models == []
    assert settings.last_single_fit is None
    assert settings.last_single_tailor is None
    assert settings.last_single_judge is None
    assert settings.version == 1


def test_model_settings_to_dict():
    """Test serialization to dict for DB storage."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    settings = ModelSettings(
        multi_model_enabled=True,
        fit_models=[allowed[0]],
        version=1,
    )
    
    # Convert to dict (for JSONB storage)
    data = settings.model_dump()
    
    assert isinstance(data, dict)
    assert data["multi_model_enabled"] is True
    assert data["fit_models"] == [allowed[0]]
    assert data["version"] == 1


def test_model_settings_from_dict():
    """Test deserialization from dict (DB retrieval)."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    data = {
        "multi_model_enabled": True,
        "fit_models": [allowed[0]],
        "tailor_models": [],
        "judge_models": [],
        "last_single_fit": None,
        "last_single_tailor": None,
        "last_single_judge": None,
        "updated_at": None,
        "version": 1,
    }
    
    # Validate from dict
    settings = ModelSettings(**data)
    
    assert settings.multi_model_enabled is True
    assert settings.fit_models == [allowed[0]]


def test_resolve_effective_settings_no_org_defaults():
    """Test resolve_effective_settings with no org defaults (current behavior)."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    user_settings = ModelSettings(
        multi_model_enabled=True,
        fit_models=[allowed[0]],
        tailor_models=[],
        judge_models=[],
        version=1,
    )
    
    # With no org defaults, should return user settings unchanged
    effective = resolve_effective_settings(user_settings)
    
    assert effective.multi_model_enabled is True
    assert effective.fit_models == [allowed[0]]
    assert effective.tailor_models == []
    assert effective is user_settings  # Should be same object for now


def test_resolve_effective_settings_with_org_defaults():
    """Test resolve_effective_settings with org defaults (future-proof)."""
    allowed = list(get_allowed_models())
    if not allowed:
        pytest.skip("No models in allowlist")
    
    user_settings = ModelSettings(
        multi_model_enabled=True,
        fit_models=[allowed[0]],
        tailor_models=[],
        judge_models=[],
        version=1,
    )
    
    # Create org defaults (for future use)
    org_defaults = ModelSettings(
        multi_model_enabled=False,
        fit_models=[],
        tailor_models=[allowed[0]],
        judge_models=[],
        version=1,
    )
    
    # Currently, should still return user settings unchanged
    # TODO: In future, this will merge/override with org policy
    effective = resolve_effective_settings(user_settings, org_defaults)
    
    # For now, user settings win
    assert effective.multi_model_enabled is True
    assert effective.fit_models == [allowed[0]]
    assert effective is user_settings  # Should be same object for now
    
    # Future behavior (commented out):
    # assert effective.multi_model_enabled is False  # Org policy wins
    # assert effective.tailor_models == [allowed[0]]  # Org default applied


def test_model_upgrade_map_contains_known_deprecations():
    """Test that the model upgrade map contains known current deprecations."""
    upgrade_map = get_model_upgrade_map()
    
    assert isinstance(upgrade_map, dict)
    assert upgrade_map["gpt-5.4"] == "gpt-5.5"
    assert upgrade_map["claude-opus-4-6"] == "claude-opus-4-7"
    assert upgrade_map["grok-4-fast"] == "grok-4-1-fast-reasoning"
    assert "grok-4-1-fast-reasoning" not in upgrade_map




def test_apply_model_upgrades_no_mapping():
    """Test that models without upgrade mappings are returned unchanged."""
    # Current allowed models are returned unchanged.
    original = "gpt-5.5"
    result = apply_model_upgrades(original)
    
    assert result == original
    
    # Test with another valid model.
    original_model = "claude-opus-4-7"
    result_model = apply_model_upgrades(original_model)
    
    assert result_model == original_model


def test_apply_model_upgrades_with_mapping(monkeypatch):
    """Test that models are upgraded when mapping exists."""
    # Mock the upgrade map to test explicit upgrade logic
    def mock_upgrade_map():
        return {
            "gpt-4.1": "gpt-5.5",
        }
    
    # Mock get_allowed_models to say gpt-4.1 is NOT allowed
    allowed = list(get_allowed_models())
    assert len(allowed) >= 1
    
    def mock_allowed_models():
        # Return all current models EXCEPT gpt-4.1 (simulate deprecation)
        return {m for m in allowed if "gpt-4.1" not in m}
    
    monkeypatch.setattr(
        "restailor.settings_schemas.get_model_upgrade_map",
        mock_upgrade_map
    )
    monkeypatch.setattr(
        "restailor.settings_schemas.get_allowed_models",
        mock_allowed_models
    )
    
    # Test model_id upgrade via explicit mapping
    assert apply_model_upgrades("gpt-4.1") == "gpt-5.5"
    
    # Test valid model is NOT upgraded
    if allowed:
        valid_model = next(m for m in allowed if m != "gpt-4.1")
        assert apply_model_upgrades(valid_model) == valid_model
def test_resolve_effective_settings_applies_upgrades(monkeypatch):
    """Test that ModelSettings validator automatically applies upgrades during construction."""
    # Get valid models from config
    allowed = list(get_allowed_models())
    assert len(allowed) >= 2, "Need at least 2 models in config for testing"
    
    # Create a fake deprecated model ID
    deprecated_model = "deprecated-test-model"
    upgrade_target = allowed[0]
    
    # Mock to make deprecated_model invalid and upgrade to first allowed model
    def mock_allowed():
        return {m for m in allowed if m != deprecated_model}
    
    def mock_upgrade_map():
        return {
            deprecated_model: upgrade_target,
        }
    
    monkeypatch.setattr(
        "restailor.settings_schemas.get_allowed_models",
        mock_allowed
    )
    monkeypatch.setattr(
        "restailor.settings_schemas.get_model_upgrade_map",
        mock_upgrade_map
    )
    
    # Create settings with "deprecated" model
    # The validator should auto-upgrade during construction
    user_settings = ModelSettings(
        multi_model_enabled=False,
        last_single_tailor=deprecated_model,
        tailor_models=[deprecated_model],
    )
    
    # Verify models were auto-upgraded during validation
    assert user_settings.last_single_tailor == upgrade_target
    assert user_settings.tailor_models == [upgrade_target]
    
    # resolve_effective_settings just returns the already-upgraded settings
    effective = resolve_effective_settings(user_settings)
    assert effective.last_single_tailor == upgrade_target
