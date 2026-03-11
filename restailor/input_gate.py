from __future__ import annotations

import asyncio
import base64
import binascii
import html
import json
import logging
import math
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal, Optional

from fastapi import Depends, HTTPException, Request
from restailor.constants import SECONDS_PER_DAY

from restailor.app_config import CONFIG

logger = logging.getLogger(__name__)


_APP = CONFIG.get("app", {})
_ABUSE = CONFIG.get("abuse", {})
_LIMITS = CONFIG.get("limits", {})
_TEXT = _LIMITS.get("text", {})
_TOK = _LIMITS.get("tokens", {})

CLIENT_ID_HEADER = _APP.get("client_id_header", "X-Client-Id")

URL_ALLOWLIST = {
    "linkedin.com",
    "www.linkedin.com",
    "github.com",
    "www.github.com",
    "gitlab.com",
    "www.gitlab.com",
    "bitbucket.org",
    "www.bitbucket.org",
}


@dataclass
class GateResult:
    replay: bool
    response: dict | None
    resume_text: str | None
    jd_text: str | None
    idem_cache_key: str | None


def _strip_html(text: str) -> str:
    try:
        # Remove script/style blocks
        text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
        # Remove all tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Unescape entities
        text = html.unescape(text)
        return text
    except Exception:
        return text


def _normalize(text: str) -> str:
    # Normalize newlines, trim, collapse excessive whitespace inside lines
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    t = _strip_html(t)
    if _ABUSE.get("ban_control_chars", True):
        # Remove control chars except \n and \t
        t = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", t)
    # Collapse runs of spaces/tabs
    t = re.sub(r"[ \t]{2,}", " ", t)
    # Trim lines and strip overall
    t = "\n".join(ln.strip() for ln in t.split("\n"))
    return t.strip()


def _detect_urls(text: str) -> list[str]:
    urls: list[str] = []
    # http(s):// and www.
    for m in re.finditer(r"\b(?:(?:https?://)|www\.)[^\s<>]+", text, flags=re.I):
        urls.append(m.group(0))
    # bare domains like example.com
    for m in re.finditer(r"\b[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s<>]*)?", text, flags=re.I):
        urls.append(m.group(0))
    return urls


def _host(u: str) -> str:
    try:
        h = re.sub(r"^https?://", "", u, flags=re.I)
        h = h.split("/", 1)[0]
        return h.lower()
    except Exception:
        return ""


async def _redis_get(request: Request, key: str) -> Optional[str]:
    try:
        r = getattr(request.app.state, "redis", None)
        if not r:
            return None
        val = await r.get(key)  # type: ignore[attr-defined]
        if val is None:
            return None
        if isinstance(val, bytes):
            return val.decode("utf-8", errors="ignore")
        return str(val)
    except Exception as ex:
        logger.info("input_gate: redis get error: %s", ex)
        return None


async def _redis_setex(request: Request, key: str, ttl: int, value: str) -> None:
    try:
        r = getattr(request.app.state, "redis", None)
        if not r:
            return
        await r.setex(key, ttl, value)  # type: ignore[attr-defined]
    except Exception as ex:
        logger.info("input_gate: redis setex error: %s", ex)


def _estimate_tokens(s: str) -> int:
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(s))
    except Exception:
        return int(math.ceil(len(s) / 4.0))


def input_gate_dep(
    endpoint: str,
    enforce_idempotency: bool = False,
    *,
    resume_field: str = "resume_text",
    jd_field: str = "jd_text",
    require_texts: bool = True,
) -> Callable[[Request], Any]:
    """Factory returning a FastAPI dependency that enforces input gates per spec.

    Parameters:
      - endpoint: logical endpoint name used for idempotency cache scoping
      - enforce_idempotency: if True, require Idempotency-Key header
      - resume_field/jd_field: JSON field names to read texts from
      - require_texts: if True, both fields must be present as strings; if False,
        texts are optional and validation/sanitization is skipped when absent.
    """

    async def _dep(request: Request) -> GateResult:
        def _log_reject(reason: str, detail: str):
            try:
                logger.warning(
                    "input_gate.reject endpoint=%s reason=%s detail=%s client_id_present=%s ip=%s",
                    endpoint,
                    reason,
                    detail,
                    bool(request.headers.get(CLIENT_ID_HEADER)),
                    request.client.host if request.client else None,
                )
            except Exception:
                pass
        # 1. Headers
        client_id = (request.headers.get(CLIENT_ID_HEADER) or "").strip()
        if not client_id and bool(_APP.get("auth_required", True)):
            _log_reject("missing_client_id", "Missing client id header")
            raise HTTPException(status_code=400, detail="Missing client id header")
        idem_key = (request.headers.get("Idempotency-Key") or "").strip()
        if enforce_idempotency and not idem_key:
            _log_reject("missing_idempotency_key", "Missing Idempotency-Key header")
            raise HTTPException(status_code=400, detail="Missing Idempotency-Key header")

        # 2. Schema (basic JSON check and flexible fields)
        try:
            body = await request.json()
        except Exception:
            _log_reject("invalid_json", "Invalid JSON body")
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        if not isinstance(body, dict):
            _log_reject("invalid_json_type", "Invalid JSON body")
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        resume_text = body.get(resume_field)
        jd_text = body.get(jd_field)
        if require_texts:
            if not isinstance(resume_text, str) or not isinstance(jd_text, str):
                _log_reject("missing_text_fields", f"{resume_field} and {jd_field} must be strings")
                raise HTTPException(status_code=400, detail=f"{resume_field} and {jd_field} must be strings")
        else:
            if resume_text is not None and not isinstance(resume_text, str):
                _log_reject("bad_resume_type", f"{resume_field} must be a string if provided")
                raise HTTPException(status_code=400, detail=f"{resume_field} must be a string if provided")
            if jd_text is not None and not isinstance(jd_text, str):
                _log_reject("bad_jd_type", f"{jd_field} must be a string if provided")
                raise HTTPException(status_code=400, detail=f"{jd_field} must be a string if provided")

        # 3. Normalize/sanitize if present
        if isinstance(resume_text, str):
            resume_text = _normalize(resume_text)
        if isinstance(jd_text, str):
            jd_text = _normalize(jd_text)

        # 4. Idempotency replay (24h)
        idem_cache_key: Optional[str] = None
        if idem_key and client_id:
            idem_cache_key = f"idem:{client_id}:{endpoint}:{idem_key}"
            cached = await _redis_get(request, idem_cache_key)
            if cached:
                try:
                    cached_obj = json.loads(cached)
                    return GateResult(replay=True, response=cached_obj, resume_text=None, jd_text=None, idem_cache_key=idem_cache_key)
                except json.JSONDecodeError as ex:
                    logger.debug("input_gate: bad cache json for %s: %s", idem_cache_key, ex)

        # 5. URL policy (only when both texts present)
        if isinstance(resume_text, str) and isinstance(jd_text, str):
            urls = _detect_urls(resume_text + "\n" + jd_text)
            # Unique non-allowlisted hosts (dedupe so repeated same domain not penalized)
            non_allow_hosts: set[str] = set()
            for u in urls:
                h = _host(u)
                if h and h not in URL_ALLOWLIST:
                    non_allow_hosts.add(h)
            max_urls = int(_TEXT.get("max_urls_per_request", 0) or 0)
            unique_count = len(non_allow_hosts)
            if max_urls >= 0 and unique_count > max_urls:
                action = (_TEXT.get("url_over_cap_action") or "neutralize").lower()
                sample_hosts = sorted(list(non_allow_hosts))[:5]
                # Internal diagnostic (kept verbose for logs only)
                internal_detail = f"Too many external URL hosts (unique={unique_count}, cap={max_urls}, sample={sample_hosts})"
                if action == "reject":
                    # Craft an end‑user, enterprise friendly message (no raw debug counters)
                    sample_clause = ""
                    if sample_hosts:
                        shown = ", ".join(sample_hosts)
                        sample_clause = f" Examples detected: {shown}."
                    user_msg = (
                        f"Your request includes links to more than {max_urls} different external websites. "
                        f"For security and privacy, we can process up to {max_urls} unique domains per submission. "
                        "Please remove or consolidate extra links (keep only essentials like your company site, LinkedIn, GitHub, or portfolio) and try again." + sample_clause
                    )
                    _log_reject("too_many_urls", internal_detail)
                    raise HTTPException(status_code=400, detail=user_msg)
                # neutralize path: replace only non-allowlisted occurrences with <URL>
                def _neutralize(txt: str) -> str:
                    def repl(m: re.Match) -> str:
                        u = m.group(0)
                        return "<URL>" if _host(u) not in URL_ALLOWLIST else u
                    txt = re.sub(r"\b(?:(?:https?://)|www\.)[^\s<>]+", repl, txt, flags=re.I)
                    txt = re.sub(r"\b[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s<>]*)?", repl, txt, flags=re.I)
                    return txt
                resume_text = _neutralize(resume_text)
                jd_text = _neutralize(jd_text)
                logger.info(
                    "input_gate: neutralized external URLs endpoint=%s unique_hosts=%s cap=%s sample=%s", 
                    endpoint, unique_count, max_urls, sample_hosts
                )

        # 6. Abuse heuristics (log-only by default)
        try:
            if isinstance(resume_text, str) and isinstance(jd_text, str):
                dup_lines_cap = int(_TEXT.get("max_duplicate_lines", 100) or 100)
                def _count_dups(s: str) -> int:
                    seen = {}
                    for ln in s.split("\n"):
                        if not ln:
                            continue
                        seen[ln] = seen.get(ln, 0) + 1
                    return sum(1 for k, v in seen.items() if v > 1)
                dups = _count_dups(resume_text + "\n" + jd_text)
                if dups > dup_lines_cap:
                    logger.info("input_gate: duplicated lines over cap: %s", dups)
                # long char runs
                if re.search(r"(.)\1{100,}", resume_text + jd_text):
                    logger.info("input_gate: long char run detected")
                # code block size
                max_code_lines = int(_ABUSE.get("max_codeblock_lines", 120) or 120)
                for block in re.findall(r"```[\s\S]*?```", resume_text + "\n" + jd_text):
                    if block.count("\n") > max_code_lines:
                        logger.info("input_gate: large code block: %s lines", block.count("\n"))
                # base64 blob size (rough)
                max_b64 = int(_ABUSE.get("max_base64_bytes", 800000) or 800000)
                b64_reject = bool(_ABUSE.get("reject_large_base64", True))
                # First, strict whole-field check
                def _check_field_for_b64(s: str) -> Optional[int]:
                    if not s or len(s) < 8:
                        return None
                    s2 = re.sub(r"\s+", "", s)
                    if not re.fullmatch(r"[A-Za-z0-9+/=]+", s2 or ""):
                        return None
                    if len(s2) % 4 != 0:
                        return None
                    try:
                        raw = base64.b64decode(s2, validate=True)
                        return len(raw)
                    except Exception:
                        return None

                for fld_name, fld_val in ((resume_field, resume_text), (jd_field, jd_text)):
                    dec_len = _check_field_for_b64(fld_val) if isinstance(fld_val, str) else None
                    if dec_len is not None and dec_len > max_b64:
                        logger.info("input_gate: %s appears to be base64 payload: %s bytes > cap %s", fld_name, dec_len, max_b64)
                        if b64_reject:
                            _log_reject("base64_payload_field", "Base64 payload too large")
                            raise HTTPException(status_code=400, detail="Base64 payload too large")
                        break

                # Fallback: scan long base64-like substrings
                min_chars = max(64, int((max_b64 * 4) / 3))
                _b64_pat = rf"[A-Za-z0-9+/=]{{{min_chars},}}"
                for candidate in re.findall(_b64_pat, resume_text + "\n" + jd_text):
                    cut = len(candidate) - (len(candidate) % 4)
                    if cut < 4:
                        continue
                    cand2 = candidate[:cut]
                    if len(set(cand2)) < 4:
                        continue
                    try:
                        raw = base64.b64decode(cand2, validate=True)
                    except (binascii.Error, ValueError) as ex:
                        logger.debug("input_gate: skip non-b64-like segment: %s", ex)
                        continue
                    if len(raw) > max_b64:
                        logger.info("input_gate: large base64 blob substring: %s bytes", len(raw))
                        if b64_reject:
                            _log_reject("base64_payload_substring", "Base64 payload too large")
                            raise HTTPException(status_code=400, detail="Base64 payload too large")
                        break
                # injection lexicon (advisory)
                if bool(_ABUSE.get("ban_injection_phrases", False)):
                    if re.search(r"ignore previous|you are now|disregard instructions", (resume_text + jd_text), re.I):
                        logger.info("input_gate: injection phrase detected")
        except Exception as ex:
            from fastapi import HTTPException as _HTTPException
            if isinstance(ex, _HTTPException):
                raise
            logger.debug("input_gate: abuse heuristics non-fatal error: %s", ex)

        # 7. Size and cost (only when both present)
        if isinstance(resume_text, str) and isinstance(jd_text, str):
            rcap = int(_TEXT.get("char_cap_resume", 120000) or 120000)
            jcap = int(_TEXT.get("char_cap_jd", 80000) or 80000)
            if len(resume_text) > rcap:
                _log_reject("resume_char_cap", f"Resume exceeds character cap ({rcap})")
                raise HTTPException(status_code=413, detail=f"Resume exceeds character cap ({rcap})")
            if len(jd_text) > jcap:
                _log_reject("jd_char_cap", f"Job description exceeds character cap ({jcap})")
                raise HTTPException(status_code=413, detail=f"Job description exceeds character cap ({jcap})")
            input_cap = int(_TOK.get("input_token_cap", 50000) or 50000)
            projected = _estimate_tokens(resume_text + "\n" + jd_text)
            if projected > input_cap:
                _log_reject("token_cap", "Input too large for model token budget")
                raise HTTPException(status_code=413, detail="Input too large for model token budget")

        # 8. Pass-through
        request.state.resume_text = resume_text if isinstance(resume_text, str) else None
        request.state.jd_text = jd_text if isinstance(jd_text, str) else None
        request.state.idem_cache_key = idem_cache_key
        return GateResult(replay=False, response=None, resume_text=resume_text, jd_text=jd_text, idem_cache_key=idem_cache_key)

    return _dep


async def cache_write_success(request: Request, response_json: dict, idem_cache_key: str | None) -> None:
    """Write success response to idempotency cache if key present (24h TTL)."""
    if not idem_cache_key:
        return
    try:
        await _redis_setex(request, idem_cache_key, SECONDS_PER_DAY, json.dumps(response_json, ensure_ascii=False))
    except Exception as ex:  # pragma: no cover
        logger.info("input_gate: cache write failed: %s", ex)
