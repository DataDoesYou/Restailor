from __future__ import annotations

import re
import hashlib
import html

# Zero-width and BOM characters to strip
_ZERO_WIDTH_RE = re.compile(r"[\u200B\u200C\u200D\uFEFF]")
_WHITESPACE_RE = re.compile(r"\s+")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def normalize_text(s: str) -> str:
    """Normalize user-provided text for stable hashing.

    Steps:
    - Remove UTF-8 BOM and zero-width space / joiner characters.
    - Convert CRLF / CR line endings to LF.
    - Strip HTML tags and unescape entities (match input_gate logic).
    - Remove control characters (match input_gate logic).
    - Collapse all consecutive whitespace (incl. newlines, tabs) to a single space.
    - Strip leading & trailing whitespace.
    """
    if s is None:  # type: ignore[unreachable]
        return ""
    # Normalize line endings first (\r\n and \r => \n)
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    
    # Strip HTML (match input_gate logic)
    # Remove script/style blocks
    s = re.sub(r"<script\b[^>]*>.*?</script>", " ", s, flags=re.I | re.S)
    s = re.sub(r"<style\b[^>]*>.*?</style>", " ", s, flags=re.I | re.S)
    # Remove all tags
    s = re.sub(r"<[^>]+>", " ", s)
    # Unescape entities
    s = html.unescape(s)

    # Remove zero-width chars / BOM
    s = _ZERO_WIDTH_RE.sub("", s)
    
    # Remove control chars (match input_gate logic)
    s = _CONTROL_CHARS_RE.sub("", s)

    # Collapse whitespace to single space
    s = _WHITESPACE_RE.sub(" ", s)
    # Strip
    return s.strip()


def sha256_hex(s: str) -> str:
    """Return lowercase hex SHA-256 of the normalized string input (no pre-normalization).

    Caller decides whether to normalize first; keep function pure to raw bytes of input string.
    """
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def compute_applied_key(user_id: str | int, jd_text: str, base_text: str) -> tuple[str, str, str]:
    """Compute (jd_hash, base_hash, applied_key) for an application snapshot.

    Hash inputs after normalization so trivial formatting differences don't break idempotency.
    applied_key format: f"{user_id}:{jd_hash}:{base_hash}".
    """
    norm_jd = normalize_text(jd_text)
    norm_base = normalize_text(base_text)
    jd_hash = sha256_hex(norm_jd)
    base_hash = sha256_hex(norm_base)
    applied_key = f"{user_id}:{jd_hash}:{base_hash}"
    return jd_hash, base_hash, applied_key
