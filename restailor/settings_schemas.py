"""User preference settings schemas with server-side validation.

Defines Pydantic models for user settings stored in the user_preferences table,
along with server-side allowlists for valid model IDs derived from config.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator, model_validator

from restailor.app_config import CONFIG


class ModelSettings(BaseModel):
    """User model preferences for multi-model feature.
    
    Controls which models are enabled for each role (fit, tailor, judge) when
    multi-model mode is active. Falls back to single-model selections when disabled.
    
    All model IDs must be validated against the server-side allowlist before storage.
    """
    
    multi_model_enabled: bool = Field(
        default=False,
        description="Whether multi-model mode is enabled for this user"
    )
    
    # Multi-model selections (lists of model IDs)
    fit_models: list[str] = Field(
        default_factory=list,
        description="List of models enabled for fit scoring (multi-model mode)"
    )
    tailor_models: list[str] = Field(
        default_factory=list,
        description="List of models enabled for resume tailoring (multi-model mode)"
    )
    judge_models: list[str] = Field(
        default_factory=list,
        description="List of models enabled for judging (multi-model mode)"
    )
    
    # Single-model selections (fallback when multi_model_enabled=False)
    last_single_fit: str | None = Field(
        default=None,
        description="Last selected single model for fit scoring"
    )
    last_single_tailor: str | None = Field(
        default=None,
        description="Last selected single model for resume tailoring"
    )
    last_single_judge: str | None = Field(
        default=None,
        description="Last selected single model for judging"
    )
    
    # Analytics preferences
    analytics_period: str = Field(
        default="90d",
        description="Default time period for analytics dashboard (7d, 30d, 90d, ytd, custom)"
    )
    
    # Admin analytics preferences (only used for admin users)
    admin_analytics_period: str = Field(
        default="90d",
        description="Default time period for admin analytics dashboard (7d, 30d, 90d, ytd, all, custom)"
    )
    admin_analytics_tab: str = Field(
        default="overview",
        description="Last selected tab in admin analytics (overview, users, usage, revenue)"
    )
    
    # Metadata
    updated_at: datetime | None = Field(
        default=None,
        description="Last update timestamp for these settings"
    )
    version: int = Field(
        default=1,
        description="Schema version for migration compatibility"
    )
    
    @field_validator('fit_models', 'tailor_models', 'judge_models', mode='before')
    @classmethod
    def validate_model_lists(cls, v: Any) -> list[str]:
        """Ensure model lists are valid lists of strings."""
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("Model lists must be arrays")
        return [str(item) for item in v if item]
    
    @field_validator('last_single_fit', 'last_single_tailor', 'last_single_judge', mode='before')
    @classmethod
    def validate_single_models(cls, v: Any) -> str | None:
        """Ensure single model selections are strings or None."""
        if v is None or v == "":
            return None
        return str(v)
    
    @field_validator('analytics_period', mode='before')
    @classmethod
    def validate_analytics_period(cls, v: Any) -> str:
        """Ensure analytics period is valid."""
        if v is None or v == "":
            return "90d"
        valid_periods = {"7d", "30d", "90d", "ytd", "custom"}
        if v not in valid_periods:
            raise ValueError(f"Invalid analytics period: {v}. Must be one of {valid_periods}")
        return str(v)
    
    @field_validator('admin_analytics_period', mode='before')
    @classmethod
    def validate_admin_analytics_period(cls, v: Any) -> str:
        """Ensure admin analytics period is valid."""
        if v is None or v == "":
            return "90d"
        valid_periods = {"7d", "30d", "90d", "ytd", "all", "custom"}
        if v not in valid_periods:
            raise ValueError(f"Invalid admin analytics period: {v}. Must be one of {valid_periods}")
        return str(v)
    
    @field_validator('admin_analytics_tab', mode='before')
    @classmethod
    def validate_admin_analytics_tab(cls, v: Any) -> str:
        """Ensure admin analytics tab is valid."""
        if v is None or v == "":
            return "overview"
        valid_tabs = {"overview", "users", "usage", "revenue"}
        if v not in valid_tabs:
            raise ValueError(f"Invalid admin analytics tab: {v}. Must be one of {valid_tabs}")
        return str(v)
    
    @model_validator(mode='after')
    def validate_against_allowlist(self) -> ModelSettings:
        """Validate all model IDs against the server-side allowlist.
        
        Instead of rejecting invalid models, automatically upgrade them to valid replacements.
        This ensures backwards compatibility when models are deprecated.
        """
        import logging
        
        logger = logging.getLogger(__name__)
        allowlist = get_allowed_models()
        
        # Log allowlist for debugging
        logger.info(f"Model allowlist: {sorted(allowlist)}")
        
        # Helper to validate and auto-upgrade if needed
        def validate_and_upgrade_model(model_id: str, field_name: str) -> str:
            """Validate model_id and auto-upgrade if deprecated."""
            logger.info(f"Validating {field_name}: model_id={model_id}")
            
            if model_id and model_id not in allowlist:
                # Known deprecated models are upgraded. Unknown model IDs remain invalid.
                logger.warning(f"Invalid or deprecated model for {field_name}: {model_id}, checking upgrade map")
                upgraded = apply_model_upgrades(model_id)
                if upgraded not in allowlist:
                    raise ValueError(f"Invalid model for {field_name}: {model_id}")
                logger.info(f"Auto-upgraded {field_name}: {model_id} -> {upgraded}")
                return upgraded
            
            return model_id
        
        # Validate and auto-upgrade multi-model lists
        self.fit_models = [validate_and_upgrade_model(m, "fit") for m in self.fit_models]
        self.tailor_models = [validate_and_upgrade_model(m, "tailor") for m in self.tailor_models]
        self.judge_models = [validate_and_upgrade_model(m, "judge") for m in self.judge_models]
        
        # Validate and auto-upgrade single-model selections
        if self.last_single_fit is not None:
            self.last_single_fit = validate_and_upgrade_model(self.last_single_fit, "last_single_fit")
        
        if self.last_single_tailor is not None:
            self.last_single_tailor = validate_and_upgrade_model(self.last_single_tailor, "last_single_tailor")
        
        if self.last_single_judge is not None:
            self.last_single_judge = validate_and_upgrade_model(self.last_single_judge, "last_single_judge")
        
        return self


# --- Server-side model allowlist ---

def get_allowed_models() -> set[str]:
    """Get the allowlist of valid model IDs from server configuration.
    
    This is the single source of truth for which models users can select.
    Extracts model IDs from all enabled providers in config/app.toml.
    
    Returns:
        Set of valid model ID strings (e.g., {"gpt-5.5", "claude-opus-4-7", "gemini-3.1-pro-preview", "grok-4.3"})
    """
    models: set[str] = set()
    
    providers_cfg = CONFIG.get("providers", {}) or {}
    
    # Extract models from each provider if enabled
    for provider_name, provider_config in providers_cfg.items():
        if provider_name == "default":
            # Skip default section (contains temps, stop sequences, etc.)
            continue
        
        if not isinstance(provider_config, dict):
            continue
        
        # Only include models from enabled providers
        if not provider_config.get("enabled", False):
            continue
        
        # Extract ALL model_* keys (not just the three roles)
        # This supports model_tailor, model_fit, model_judge, model_tailor_alt, etc.
        for key, value in provider_config.items():
            if key.startswith("model_") and isinstance(value, str):
                models.add(value.strip())
    
    return models


def get_models_by_provider() -> dict[str, dict[str, str]]:
    """Get models organized by provider and role.
    
    Returns:
        Dict mapping provider -> role -> model_id
        Example: {"openai": {"tailor": "gpt-5", "fit": "gpt-5", "judge": "gpt-5"}, ...}
    """
    result: dict[str, dict[str, str]] = {}
    
    providers_cfg = CONFIG.get("providers", {}) or {}
    
    for provider_name, provider_config in providers_cfg.items():
        if provider_name == "default":
            continue
        
        if not isinstance(provider_config, dict):
            continue
        
        if not provider_config.get("enabled", False):
            continue
        
        provider_models: dict[str, str] = {}
        for role in ["tailor", "fit", "judge"]:
            model_key = f"model_{role}"
            model_id = provider_config.get(model_key)
            if model_id and isinstance(model_id, str):
                provider_models[role] = model_id.strip()
        
        if provider_models:
            result[provider_name] = provider_models
    
    return result


def validate_model_id(model_id: str) -> bool:
    """Check if a model ID is in the allowlist.
    
    Args:
        model_id: The model ID to validate
        
    Returns:
        True if the model ID is allowed, False otherwise
    """
    return model_id in get_allowed_models()


def get_default_model_for_role(role: str) -> str | None:
    """Get the default model for a given role from the first enabled provider.
    
    Args:
        role: One of "tailor", "fit", or "judge"
        
    Returns:
        The default model ID for that role, or None if not found
    """
    if role not in ("tailor", "fit", "judge"):
        return None
    
    providers_cfg = CONFIG.get("providers", {}) or {}
    
    # Try to find the first enabled provider with this role
    for provider_name in ["openai", "anthropic", "google", "xai"]:  # Order of preference
        provider_config = providers_cfg.get(provider_name, {})
        if not isinstance(provider_config, dict):
            continue
        
        if not provider_config.get("enabled", False):
            continue
        
        model_key = f"model_{role}"
        model_id = provider_config.get(model_key)
        if model_id and isinstance(model_id, str):
            return model_id.strip()
    
    return None


# --- Model upgrade/migration mappings ---

def get_model_upgrade_map() -> dict[str, str]:
    """Automatically generate model upgrade mappings by comparing config vs current models.
    
    Strategy: If a user has a model that's no longer in the config allowlist,
    automatically upgrade them to the first available model from the same provider.
    This ensures users always have a valid model selected.
    
    Returns:
        Dict mapping old/deprecated model_id -> new model_id
    """
    import logging
    logger = logging.getLogger(__name__)
    
    upgrade_map: dict[str, str] = {}
    
    # Get current allowed models from config
    allowed = get_allowed_models()
    
    # Get models organized by provider
    by_provider = get_models_by_provider()
    
    # Define explicit upgrade mappings for known deprecations
    # This section can be used for custom upgrade paths (e.g., GPT-4 -> GPT-5 Instant instead of Thinking)
    explicit_upgrades = {
        "gpt-5.1-instant": "gpt-5.4-mini",
        "gpt-5.1-thinking": "gpt-5.5",
        "gpt-5.2-chat-latest": "gpt-5.4-mini",
        "gpt-5.2": "gpt-5.5",
        "gpt-5.3-chat-latest": "gpt-5.4-mini",
        "gpt-5.4": "gpt-5.5",
        "claude-sonnet-4-5-20250929": "claude-sonnet-4-6",
        "claude-opus-4-5-20251101": "claude-opus-4-7",
        "claude-opus-4-6": "claude-opus-4-7",
        "gemini-3-pro-preview": "gemini-3.1-pro-preview",
        "gemini-2.5-flash": "gemini-3-flash-preview",
        "grok-4-1-fast-reasoning": "grok-4.3",
        "grok-4-fast": "grok-4.3",
        "grok-4-0709": "grok-4.3",
        "grok-4": "grok-4.3",
    }
    
    upgrade_map.update(explicit_upgrades)
    
    # For models not explicitly mapped, auto-upgrade deprecated models
    # to the default model for their provider (if available)
    # This handles the case where a provider removes old models
    
    logger.debug(f"Model upgrade map generated: {upgrade_map}")
    
    return upgrade_map


def apply_model_upgrades(model_id: str) -> str:
    """Apply automatic model upgrade/fallback if needed.
    
    Checks if the given model is still in the allowlist. If not, only explicit
    known-deprecated mappings are upgraded. Unknown values are returned
    unchanged so validation can reject them.
    
    This ensures saved preferences survive known model retirements without
    accepting arbitrary model IDs.
    
    Args:
        model_id: Model identifier (e.g., "gpt-5.1-instant", "claude-sonnet-4-6")
        
    Returns:
        Valid model_id (upgraded if needed, or original if still valid)
    """
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Check if model is still valid
    allowed = get_allowed_models()
    if model_id and model_id in allowed:
        # Model is still valid, return as-is
        return model_id
    
    # Model is deprecated/invalid. Upgrade only if this is a known mapping.
    logger.info(f"Model {model_id} not in allowlist, finding replacement")
    
    # 1. Check explicit upgrade mapping
    upgrade_map = get_model_upgrade_map()
    if model_id in upgrade_map:
        replacement = upgrade_map[model_id]
        logger.info(f"Using explicit upgrade mapping: {model_id} -> {replacement}")
        return replacement
    
    # Unknown values must be rejected by the caller's validation path.
    logger.error(f"Could not find explicit replacement for invalid model: {model_id}")
    return model_id


def resolve_effective_settings(
    user_settings: ModelSettings,
    org_defaults: ModelSettings | None = None
) -> ModelSettings:
    """Resolve effective settings by merging user preferences with org/tenant defaults.
    
    Model upgrades are now handled automatically in the ModelSettings validator,
    so this function focuses on future org/tenant policy merging.
    
    Args:
        user_settings: User's personal model preferences (already validated and upgraded)
        org_defaults: Organization/tenant default settings (optional, for future use)
    
    Returns:
        ModelSettings: Effective settings to use
        
    Note:
        Model auto-upgrades happen in ModelSettings.validate_against_allowlist(),
        so settings passed here are already upgraded if needed.
    """
    # The validator already handles model upgrades, so we just return the settings
    # TODO: Implement org/tenant policy merge logic when multi-tenancy is added
    return user_settings
