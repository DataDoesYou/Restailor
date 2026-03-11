from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Dict, Tuple
import time

from config_loader import load_config
from services.money import to_cents as money_to_cents, format_usd

# Ensure enough precision for intermediate math; we quantize to 6 or 2 later.
getcontext().prec = 28


_PRICE_CACHE: Dict[str, Tuple[float, dict]] = {}
_PRICE_CACHE_TTL_SEC = 60.0


def _now() -> float:
    return time.time()


def _quantize_6(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _quantize_2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def load_price_map(cfg: dict | None = None) -> dict:
    """Load pricing map from TOML config with TTL caching.

    Pricing keys are the exact provider API model IDs (e.g., "gpt-5", "gemini-3-pro-preview",
    "claude-sonnet-4-5-20250929"). We retain a small alias map for legacy/display names,
    but do not invent our own canonical keys.

    Returns a dict:
    {
        "multiplier": Decimal,
        "currency": str,
        "models": { "<provider-model-id>": {"input": Decimal, "output": Decimal} },
        "version": 1,
        "aliases": { "<legacy or display name>": "<provider-model-id>" }
    }
    """
    cache_key = "default"
    now = _now()
    entry = _PRICE_CACHE.get(cache_key)
    if entry and (now - entry[0]) < _PRICE_CACHE_TTL_SEC:
        return entry[1]

    if cfg is None:
        cfg = load_config()

    pr = dict((cfg.get("pricing", {}) or {}))
    models_flat = dict((pr.get("models", {}) or {}))
    aliases_cfg = dict((pr.get("aliases", {}) or {}))

    # Pricing is sourced from TOML config only.
    multiplier = Decimal(str(pr.get("multiplier", "1.0")))
    currency = str(pr.get("currency") or "USD").strip() or "USD"

    # Flatten "<Model>.input" and "<Model>.output" into nested structure
    models: Dict[str, Dict[str, Decimal]] = {}
    for k, v in models_flat.items():
        s = str(k)
        if s.endswith(".input"):
            name = s[:-len(".input")]
            rate = Decimal(str(v))
            models.setdefault(name, {})["input"] = rate
        elif s.endswith(".output"):
            name = s[:-len(".output")]
            rate = Decimal(str(v))
            models.setdefault(name, {})["output"] = rate
        else:
            raise ValueError(f"pricing.models key must end with .input or .output: {s}")

    # Validate that each model has both input and output
    for name, m in models.items():
        if "input" not in m or "output" not in m:
            raise ValueError(f"pricing for model '{name}' must include both input and output rates")

    # Build normalized alias map -> canonical pricing key
    aliases: Dict[str, str] = {}
    for alias_key, canonical in aliases_cfg.items():
        try:
            aliases[_norm_model(alias_key)] = str(canonical)
        except Exception:
            continue

    result = {
        "multiplier": Decimal(multiplier),
        "currency": str(currency),
        "models": models,
        # integer pricing version for storage; bump as needed when price tables change
        "version": 1,
        # normalized alias -> canonical pricing key
        "aliases": aliases,
    }

    _PRICE_CACHE[cache_key] = (now, result)
    return result


def _norm_model(s: str) -> str:
        """Normalize strings for fuzzy matching of legacy names/variants only.

        Note: Pricing keys themselves are exact provider IDs; normalization is used
        only for tolerant matching (aliases, case/separator drift), never to invent
        new canonical keys.

        - Lowercase
        - Remove separators (space, ., _, -)
        - Strip common trailing provider suffixes like date stamps (e.g., 20250514),
            and markers like 'latest', 'preview', 'beta', or version tags like 'v<number>'
        """
        import re
        s = str(s or "").strip().lower()
        # Drop optional provider prefix like "anthropic:" or "openai:"
        if ":" in s:
                s = s.split(":", 1)[1]
        # Remove separators (including colon just in case) to match flexibly
        s = re.sub(r"[\s._:-]+", "", s)
        # Drop trailing date stamp (e.g., 20250514) or YYYYMM or YYYYMMDDHH etc.
        s = re.sub(r"(?:20\d{6,10})$", "", s)
        # Drop common trailing labels
        s = re.sub(r"(?:latest|preview|beta|stable)$", "", s)
        # Drop trailing v<number> (e.g., v2, v3)
        s = re.sub(r"v\d+$", "", s)
        return s


def quote_cost_usd(price_map: dict, model_name: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Compute true USD cost at provider rates, 6-decimal HALF_UP.

    cost = (prompt_tokens/1e6 * input_rate) + (completion_tokens/1e6 * output_rate)

    Lookup order:
      1) exact provider model ID match in price_map["models"],
      2) explicit alias -> provider ID,
      3) last-resort tolerant match via normalization.
    """
    models = price_map.get("models", {}) or {}
    aliases = price_map.get("aliases", {}) or {}

    # Try exact match first
    mn = (model_name or "").strip()
    key = mn if mn in models else None
    if key is None and aliases:
        # Prefer explicit alias mapping: provider:model_id format recommended by callers
        alias_key = _norm_model(mn)
        canonical = aliases.get(alias_key)
        if canonical and canonical in models:
            key = canonical
    if key is None:
        # Case-insensitive and separator-insensitive match
        nmn = _norm_model(mn)
        for k in models.keys():
            if _norm_model(k) == nmn:
                key = k
                break
    if key is None:
        raise ValueError(f"unknown model in price map: {model_name}")
    model_rates = models[key]
    input_rate: Decimal = Decimal(model_rates["input"])  # per 1M tokens
    output_rate: Decimal = Decimal(model_rates["output"])  # per 1M tokens

    pt = Decimal(int(prompt_tokens))
    ct = Decimal(int(completion_tokens))

    cost = (pt / Decimal(1_000_000)) * input_rate + (ct / Decimal(1_000_000)) * output_rate
    return _quantize_6(cost)


def apply_multiplier(cost_dec: Decimal, multiplier_dec: Decimal) -> Decimal:
    """Apply multiplier and quantize to 6 decimals, HALF_UP."""
    return _quantize_6(cost_dec * multiplier_dec)


def to_cents(dec: Decimal) -> int:
    """Convert a Decimal USD to integer cents using shared money helper (HALF_UP to 2dp)."""
    return money_to_cents(dec)


def estimate_user_price(
    price_map: dict,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> dict:
    """Estimate end-user price from provider token counts.

    Returns dict with:
      - price_cents: int
      - price_usd: str (formatted 2dp)
      - currency: str
    """
    cost = quote_cost_usd(price_map, model_name, int(prompt_tokens or 0), int(completion_tokens or 0))
    price_dec = apply_multiplier(cost, Decimal(price_map.get("multiplier", Decimal("1"))))
    cents = to_cents(price_dec)
    return {
        "price_cents": int(cents),
        "price_usd": format_usd(int(cents)),
        "currency": str(price_map.get("currency", "USD")),
    }


def is_known_model(price_map: dict, model_name: str) -> bool:
    """Return True if the given model name exists in the pricing map using tolerant matching."""
    models = price_map.get("models", {}) or {}
    aliases = price_map.get("aliases", {}) or {}
    if model_name in models:
        return True
    # Alias lookup first
    alias_key = _norm_model(model_name)
    if alias_key in aliases and aliases[alias_key] in models:
        return True
    nmn = _norm_model(model_name)
    for k in models.keys():
        if _norm_model(k) == nmn:
            return True
    return False


def get_model_rates(price_map: dict, model_name: str) -> dict:
    """Return a dict with Decimal rates {input, output} using tolerant matching.

    Raises ValueError if the model cannot be found.
    """
    models = price_map.get("models", {}) or {}
    aliases = price_map.get("aliases", {}) or {}
    if model_name in models:
        return models[model_name]
    # Alias to canonical
    alias_key = _norm_model(model_name)
    if alias_key in aliases and aliases[alias_key] in models:
        return models[aliases[alias_key]]
    nmn = _norm_model(model_name)
    for k, v in models.items():
        if _norm_model(k) == nmn:
            return v
    raise ValueError(f"unknown model in price map: {model_name}")
