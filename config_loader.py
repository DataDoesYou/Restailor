"""Config helpers and config file utilities for Resume Tailor.

- get_backend_base(): Centralized resolver for the backend base URL.
- load_config()/helpers: Read app config and build provider params.
"""
from __future__ import annotations

import os


def get_backend_base() -> str:
    """Return backend base URL.

    Order of precedence:
    - BACKEND_BASE_URL env var
    - NEXT_PUBLIC_API_URL (shared with Next dev) or NEXT_PUBLIC_API_BASE_URL
    - Default http://127.0.0.1:8000 for local dev
    """
    env_val = (os.getenv("BACKEND_BASE_URL") or os.getenv("NEXT_PUBLIC_API_URL") or os.getenv("NEXT_PUBLIC_API_BASE_URL") or "").strip()
    if env_val:
        return env_val
    return "http://127.0.0.1:8000"

from pathlib import Path
from typing import Any, Dict, Literal
import logging

_logger = logging.getLogger(__name__)


def _toml_module():
    try:
        import tomllib as _toml  # type: ignore[attr-defined]
        return _toml
    except Exception:
        try:
            import tomli as _toml  # type: ignore
            return _toml
        except Exception:  # pragma: no cover
            return None


def load_config(path: str | None = None) -> dict:
    """Load the TOML config file.

    Args:
        path: Optional absolute or relative path to the TOML file. Defaults to
              "config/app.toml" relative to the repository root (this file's parent dir).

    Returns:
        Parsed config as a dict; empty dict if file missing or TOML parser unavailable.
    """
    _toml = _toml_module()
    cfg_path = Path(path) if path else (Path(__file__).resolve().parent / "config" / "app.toml")
    try:
        if not cfg_path.exists() or _toml is None:
            return {}
        # tomllib/tomli both accept a bytes file object
        with cfg_path.open("rb") as f:
            return _toml.load(f)  # type: ignore[attr-defined]
    except Exception:
        return {}


def get_limits(cfg: dict) -> dict:
    """Return the limits section."""
    return dict(cfg.get("limits", {}) or {})


def get_role_timeouts(cfg: dict, role: Literal["tailor", "fit", "judge"]) -> dict:
    """Return timeouts for a role, merging [timeouts_role.<role>] over [timeouts]."""
    base = dict((cfg.get("timeouts", {}) or {}))
    role_over = ((cfg.get("timeouts_role", {}) or {}).get(role, {}) or {})
    out = dict(base)
    out.update(role_over)
    return out


def get_abuse(cfg: dict) -> dict:
    """Return the [abuse] section (empty dict if missing)."""
    return dict(cfg.get("abuse", {}) or {})


def get_abuse_role(cfg: dict, role: Literal["tailor", "fit", "judge"]) -> dict:
    """Return abuse settings for a role, layered over base [abuse]."""
    base = get_abuse(cfg)
    role_over = ((cfg.get("abuse_role", {}) or {}).get(role, {}) or {})
    out = dict(base)
    out.update(role_over)
    return out


def provider_enabled(cfg: dict, provider: str) -> bool:
    """Whether the provider is enabled (defaults to True when not specified)."""
    pr = ((cfg.get("providers", {}) or {}).get(provider, {}) or {})
    return bool(pr.get("enabled", True))


def get_provider_models(cfg: dict, provider: str) -> dict:
    """Get provider models mapping.

    Returns a dict with keys: model_tailor, model_fit, model_judge (values may be None).
    """
    pr = ((cfg.get("providers", {}) or {}).get(provider, {}) or {})
    return {
        "model_tailor": pr.get("model_tailor"),
        "model_fit": pr.get("model_fit"),
        "model_judge": pr.get("model_judge"),
    }


def _role_output_cap(cfg: dict, role: Literal["tailor", "fit", "judge"]) -> int | None:
    ro = (((cfg.get("limits", {}) or {}).get("role_outputs", {}) or {}))
    val = ro.get(role)
    try:
        return int(val) if val is not None else None
    except Exception:
        return None


def _role_temperature(cfg: dict, role: Literal["tailor", "fit", "judge"]) -> float | None:
    d = ((cfg.get("providers", {}) or {}).get("default", {}) or {})
    key = f"temperature_{role}"
    val = d.get(key)
    try:
        return float(val) if val is not None else None
    except Exception:
        return None


def _google_role_thinking_budget(cfg: dict, role: Literal["tailor", "fit", "judge"]) -> int | None:
    try:
        g = ((cfg.get("providers", {}) or {}).get("google", {}) or {})
        val = g.get(f"thinking_budget_{role}")
        return int(val) if val is not None else None
    except Exception:
        return None


def _anthropic_role_thinking_budget(cfg: dict, role: Literal["tailor", "fit", "judge"]) -> int | None:
    """Get Anthropic extended thinking budget_tokens for a role.
    
    Returns None if not configured (thinking disabled).
    Valid range: 1024 to 200000.
    """
    try:
        a = ((cfg.get("providers", {}) or {}).get("anthropic", {}) or {})
        val = a.get(f"thinking_budget_{role}")
        if val is not None:
            budget = int(val)
            # Clamp to valid range per Anthropic docs
            return max(1024, min(200000, budget))
        return None
    except Exception:
        return None


def _anthropic_role_effort(cfg: dict, role: Literal["tailor", "fit", "judge"]) -> str | None:
    """Get Anthropic effort parameter for a role (Opus 4.5+ only).
    
    Returns: "high", "medium", "low", or None (uses default/high).
    """
    try:
        a = ((cfg.get("providers", {}) or {}).get("anthropic", {}) or {})
        val = a.get(f"effort_{role}")
        if val is not None:
            effort = str(val).lower()
            if effort in ("high", "medium", "low"):
                return effort
        return None
    except Exception:
        return None


def _google_role_thinking_level(cfg: dict, role: Literal["tailor", "fit", "judge"]) -> str | None:
    try:
        g = ((cfg.get("providers", {}) or {}).get("google", {}) or {})
        val = g.get(f"thinking_level_{role}")
        return str(val) if val is not None else None
    except Exception:
        return None


def _google_role_include_thoughts(cfg: dict, role: Literal["tailor", "fit", "judge"]) -> bool:
    try:
        g = ((cfg.get("providers", {}) or {}).get("google", {}) or {})
        val = g.get(f"include_thoughts_{role}")
        return bool(val) if val is not None else False
    except Exception:
        return False


def _default_stop_sequences(cfg: dict) -> list[str] | None:
    """Return default stop sequences from config.
    Only snake_case key 'stop_sequences' is supported.
    """
    d = ((cfg.get("providers", {}) or {}).get("default", {}) or {})
    seq_snake = d.get("stop_sequences")
    if not isinstance(seq_snake, (list, tuple)):
        return None
    merged: list[str] = []
    for s in seq_snake:
        if not isinstance(s, (str, bytes)):
            continue
        v = s.decode("utf-8", errors="ignore") if isinstance(s, (bytes, bytearray)) else str(s)
        if v and v not in merged:
            merged.append(v)
    return merged or None


def _is_gpt5(model: str) -> bool:
    m = (model or "").lower()
    return m.startswith("gpt-5") or m == "gpt5"


def _normalize_provider_name(provider: str) -> str:
    p = (provider or "").lower()
    return {"google": "gemini"}.get(p, p)


def _prune(d: Dict[str, Any], allowed: set[str], *, provider: str, role: str) -> Dict[str, Any]:
    """Drop None and keys not in allowlist; log one INFO line if any keys are dropped."""
    out: Dict[str, Any] = {}
    dropped: set[str] = set()
    for k, v in d.items():
        if v is None or k not in allowed:
            dropped.add(k)
            continue
        out[k] = v
    if dropped:
        try:
            _logger.info(
                "config_loader.build_gen_params dropped keys for provider=%s role=%s: %s",
                provider,
                role,
                sorted(dropped),
            )
        except Exception as ex:
            _logger.debug("config_loader: logging dropped keys failed: %r", ex)
    return out


def build_gen_params(
    cfg: dict,
    provider: str,
    role: Literal["tailor", "fit", "judge"],
    model: str,
) -> dict:
    """Build provider-specific generation parameters.

    Rules:
    - Always include the per-role output cap mapped to the provider's expected key name.
    - OpenAI GPT-5: include reasoning.effort and max_output_tokens only (no temp/stop).
    - OpenAI (non-gpt-5): allow temperature, max_output_tokens, stop.
    - Anthropic: temperature, max_tokens, stop_sequences; Opus 4.7 uses adaptive thinking.
    - Gemini: temperature, max_output_tokens, stop_sequences.
    - xAI (Grok): temperature, max_tokens; include stop only if model is not grok-4.
    """
    p = _normalize_provider_name(provider)
    cap = _role_output_cap(cfg, role)
    temp = _role_temperature(cfg, role)
    stops = _default_stop_sequences(cfg)
    # Always include a static end-of-output sentinel usable across providers; worker may
    # also pass a per-job dynamic marker via stop_markers at runtime.
    STATIC_END = "\n### END OUTPUT\n"
    if stops is None:
        stops = [STATIC_END]
    elif STATIC_END not in stops:
        stops = [*stops, STATIC_END]

    if p == "openai":
        if _is_gpt5(model):
            # Role-specific reasoning from providers.openai
            openai_cfg = ((cfg.get("providers", {}) or {}).get("openai", {}) or {})
            
            # Map virtual model IDs to real model and reasoning effort
            model_lower = (model or "").lower()
            if model_lower in ("gpt-5.1-instant", "gpt5.1-instant"):
                actual_model = "gpt-5.1"
                effort = "none"  # Instant mode uses no reasoning
            elif model_lower in ("gpt-5.1-thinking", "gpt5.1-thinking"):
                actual_model = "gpt-5.1"
                effort = "medium"  # Thinking mode uses medium reasoning
            elif model_lower in ("gpt-5.1", "gpt5.1"):
                actual_model = "gpt-5.1"
                effort = "none"  # Default to instant
            else:
                # Other GPT-5 models (gpt-5, etc.) use configured reasoning effort
                actual_model = model
                effort = openai_cfg.get(f"reasoning_effort_{role}")
            
            raw = {
                "reasoning": {"effort": effort} if effort else None,
                "max_output_tokens": cap,
            }
            allowed = {"reasoning", "max_output_tokens"}
            # prune nested reasoning if it's None
            if raw.get("reasoning") is None:
                raw.pop("reasoning", None)
            out = _prune(raw, allowed, provider=p, role=role)
            out["_meta_role"] = role  # internal metadata for downstream fallback logic
            out["_actual_model"] = actual_model  # Store actual model for API call
            return out
        # Non-GPT-5
        raw = {
            "temperature": temp,
            "max_output_tokens": cap,
            # OpenAI Responses API does not accept provider-side stop; keep for
            # completeness and possible future use, but worker will also use
            # client-side stop markers.
            "stop": stops,
        }
        allowed = {"temperature", "max_output_tokens", "stop"}
        out = _prune(raw, allowed, provider=p, role=role)
        out["_meta_role"] = role
        return out

    if p == "anthropic":
        mdl_lower = (model or "").lower()

        # Build thinking config. Opus 4.7 removed budget-token extended thinking
        # in favor of adaptive thinking plus output_config.effort.
        thinking_budget = _anthropic_role_thinking_budget(cfg, role)
        thinking_config = None
        if "opus-4-7" in mdl_lower or "opus-4.7" in mdl_lower:
            thinking_config = {"type": "adaptive"}
        elif thinking_budget is not None:
            thinking_config = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }
        
        # Effort parameter for Opus models that support output_config.effort.
        effort = _anthropic_role_effort(cfg, role)
        
        raw = {
            "temperature": temp,
            "max_tokens": cap,
            "stop_sequences": stops,
            "thinking": thinking_config,
            "_effort": effort,  # Internal; handled specially in llm.py
        }
        allowed = {"temperature", "max_tokens", "stop_sequences", "thinking", "_effort"}
        out = _prune(raw, allowed, provider=p, role=role)
        out["_meta_role"] = role
        return out

    if p == "gemini":
        # google-genai (google.genai) expects snake_case keys on GenerateContentConfig
        # - max_output_tokens and stop_sequences are honored as-is
        # - thinking: 
        #   - Gemini 2.5: budget_tokens (0 disables)
        #   - Gemini 3.0: thinking_level (low/high) + include_thoughts (bool)
        
        mdl_lower = (model or "").lower()
        is_gemini_3 = "gemini-3" in mdl_lower
        
        thinking_config = {}
        if is_gemini_3:
            tl = _google_role_thinking_level(cfg, role)
            it = _google_role_include_thoughts(cfg, role)
            thinking_config = {
                "include_thoughts": it,
                "thinking_level": tl if tl else "low"
            }
        else:
            tb = _google_role_thinking_budget(cfg, role)
            thinking_config = {"budget_tokens": (tb if tb is not None else 0)}

        effective_cap = cap
        try:
            if "flash" in mdl_lower:
                # Allow optional per-role overrides via providers.google.flash_min_<role>
                g = ((cfg.get("providers", {}) or {}).get("google", {}) or {})
                flash_key = f"flash_min_{role}"
                flash_min_raw = g.get(flash_key)
                flash_min: int | None = None
                try:
                    if flash_min_raw is not None:
                        flash_min = int(flash_min_raw)
                except Exception:
                    flash_min = None
                if flash_min is None:
                    # Default heuristic: ensure at least 8192 for Flash when base cap < 8192
                    flash_min = 8192
                if effective_cap is None:
                    effective_cap = flash_min
                elif effective_cap < flash_min:
                    _logger.info(
                        "config_loader: escalating gemini flash cap role=%s from %s to %s (model=%s)",
                        role,
                        effective_cap,
                        flash_min,
                        model,
                    )
                    effective_cap = flash_min
        except Exception as ex:  # safe-guard; never break param building
            _logger.debug("config_loader: flash cap escalation skipped due to error: %s", ex)
        raw = {
            "temperature": temp,
            "max_output_tokens": effective_cap,
            "stop_sequences": stops,
            # Keep JSON-serializable shape; services.llm will coerce to SDK type.
            "thinking": thinking_config,
        }
        allowed = {"temperature", "max_output_tokens", "stop_sequences", "thinking"}
        out = _prune(raw, allowed, provider=p, role=role)
        out["_meta_role"] = role
        return out

    if p == "xai":
        # Grok specific: no stop for grok-4
        include_stop = not (model or "").lower().startswith("grok-4")
        raw = {
            "temperature": temp,
            "max_tokens": cap,
            "stop": (stops if include_stop else None),
        }
        allowed = {"temperature", "max_tokens", "stop"}
        out = _prune(raw, allowed, provider=p, role=role)
        out["_meta_role"] = role
        return out

    # Default: just pass temperature and a generic max_tokens if unknown provider
    raw = {"temperature": temp, "max_tokens": cap}
    default_out = {k: v for k, v in raw.items() if v is not None}
    default_out["_meta_role"] = role
    return default_out


def get_testing(cfg: dict) -> dict:
    """Return testing config for mock/live streaming.

    Env override: if E2E_MODE="mock" force mode=mock regardless of file.
    """
    t = dict((cfg.get("testing", {}) or {}))
    import os
    mode = (t.get("mode") or "live").lower()
    if (os.getenv("E2E_MODE") or "").lower() == "mock":
        mode = "mock"
    chunk_text = t.get("mock_chunk_text") or "This is a simulated streamed token "
    try:
        chunk_count = int(t.get("mock_chunk_count") or 60)
    except Exception:
        chunk_count = 60
    try:
        emit_delay_s = float(t.get("mock_emit_delay_ms") or 25) / 1000.0
    except Exception:
        emit_delay_s = 0.025
    return {
        "mode": mode,
        "chunk_text": str(chunk_text),
        "chunk_count": int(chunk_count),
        "emit_delay_s": float(emit_delay_s),
    }
