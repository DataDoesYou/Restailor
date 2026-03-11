"""Centralized runtime configuration for model temperatures and provider timeouts.

Primary source is config/app.toml ([providers.default.temperature_*]).
Environment variables WRITER_TEMP, JUDGE_TEMP, FIT_TEMP, and PROVIDER_TIMEOUT_S,
if set, override the TOML values at runtime.
"""
from __future__ import annotations
import os
from typing import Any

try:
    # Read from app.toml through the shared loader
    from restailor.app_config import CONFIG as _CFG  # type: ignore
except Exception:  # pragma: no cover
    _CFG = {}  # type: ignore

def _to_float(val: str, default: float) -> float:
    try:
        return float(val)
    except Exception:
        return default

def _get_toml_temp(role: str, default: float) -> float:
    try:
        d: dict[str, Any] = (_CFG.get("providers", {}) or {}).get("default", {}) or {}
        v = d.get(f"temperature_{role}")
        if v is None:
            return default
        return float(v)
    except Exception:
        return default

# Base values from app.toml, then allow env override
WRITER_TEMP: float = _to_float(os.getenv("WRITER_TEMP", str(_get_toml_temp("tailor", 0.4))), 0.4)
JUDGE_TEMP: float = _to_float(os.getenv("JUDGE_TEMP", str(_get_toml_temp("judge", 0.2))), 0.2)
FIT_TEMP: float = _to_float(os.getenv("FIT_TEMP", str(_get_toml_temp("fit", 0.2))), 0.2)

# Global HTTP timeout for provider SDKs (seconds)
def _to_int(val: str, default: int) -> int:
    try:
        return int(val)
    except Exception:
        return default

PROVIDER_TIMEOUT_S: int = _to_int(os.getenv("PROVIDER_TIMEOUT_S", "600"), 600)

# --- Feature flags ---
def env_bool(name: str, default: bool) -> bool:
    """Parse a boolean from environment variables.

    Truthy: '1', 'true', 'yes', 'on' (case-insensitive)
    Falsy: '0', 'false', 'no', 'off'
    Missing -> default
    """
    val = os.getenv(name)
    if val is None:
        return bool(default)
    v = val.strip().lower()
    if v in {"1", "true", "yes", "on"}:
        return True
    if v in {"0", "false", "no", "off"}:
        return False
    return bool(default)

# Toggle for the new cancel flow (V2)
FEATURE_CANCEL_V2: bool = env_bool("FEATURE_CANCEL_V2", True)
