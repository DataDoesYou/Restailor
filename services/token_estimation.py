from __future__ import annotations

"""Improved token estimation for LLM requests.

Uses tiktoken for OpenAI models when available, falls back to character-based heuristics.
"""
import logging
from typing import Optional

_LOG = logging.getLogger(__name__)


def estimate_tokens(text: str, model: Optional[str] = None) -> int:
    """Estimate token count for given text and model.
    
    Args:
        text: The text to estimate tokens for
        model: Optional model identifier (e.g., "gpt-4", "claude-3-opus")
        
    Returns:
        Estimated token count (minimum 1)
    """
    if not text:
        return 1
    
    # Try tiktoken for OpenAI models
    if model and _is_openai_model(model):
        try:
            import tiktoken
            encoding = _get_encoding_for_model(model)
            if encoding:
                try:
                    tokens = encoding.encode(text)
                    count = len(tokens)
                    return max(1, count)
                except Exception as ex:
                    _LOG.debug(f"tiktoken encoding failed for {model}: {ex}")
        except ImportError:
            _LOG.debug("tiktoken not available, falling back to heuristic")
        except Exception as ex:
            _LOG.debug(f"tiktoken estimation failed: {ex}")
    
    # Fallback to character-based heuristic (~4 chars per token)
    return max(1, len(text) // 4)


def _is_openai_model(model: str) -> bool:
    """Check if model is from OpenAI."""
    model_lower = model.lower()
    openai_prefixes = ("gpt-", "o1-", "o3-", "text-", "davinci", "curie", "babbage", "ada")
    return any(model_lower.startswith(prefix) for prefix in openai_prefixes)


def _get_encoding_for_model(model: str) -> Optional[object]:
    """Get tiktoken encoding for a specific model.
    
    Returns encoding object or None if model not recognized.
    """
    try:
        import tiktoken
        
        # Try direct model lookup first
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            pass
        
        # Fallback to encoding by model family
        model_lower = model.lower()
        
        # GPT-4 and newer models use cl100k_base
        if any(x in model_lower for x in ["gpt-4", "gpt-5", "o1-", "o3-"]):
            return tiktoken.get_encoding("cl100k_base")
        
        # GPT-3.5 and older
        if "gpt-3.5" in model_lower or "gpt-35" in model_lower:
            return tiktoken.get_encoding("cl100k_base")
        
        # Legacy models
        if any(x in model_lower for x in ["davinci", "curie", "babbage", "ada"]):
            return tiktoken.get_encoding("p50k_base")
        
        # Default for unrecognized OpenAI models
        return tiktoken.get_encoding("cl100k_base")
        
    except Exception as ex:
        _LOG.debug(f"Failed to get encoding for {model}: {ex}")
        return None


def estimate_prompt_and_completion(
    prompt: str,
    completion: str,
    model: Optional[str] = None
) -> tuple[int, int]:
    """Estimate tokens for both prompt and completion.
    
    Args:
        prompt: The prompt text
        completion: The completion text
        model: Optional model identifier
        
    Returns:
        Tuple of (prompt_tokens, completion_tokens)
    """
    prompt_tokens = estimate_tokens(prompt, model)
    completion_tokens = estimate_tokens(completion, model)
    return (prompt_tokens, completion_tokens)
