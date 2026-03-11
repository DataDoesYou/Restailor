from __future__ import annotations

"""Network risk classification helpers (pure, header-based).

Exposes:
- NetTier: RESIDENTIAL | UNIVERSITY | DATACENTER | UNKNOWN
- classify_ip_asn(ip, asn, org, settings) -> NetTier
- get_asn_from_headers(request, header_name) -> str | None
- get_org_from_headers(request, header_name) -> str | None

No external lookups are performed. Caller is responsible for providing
IP/ASN/Org values, typically via proxy-populated headers.
"""

from enum import Enum
from typing import Any, Mapping
import ipaddress

try:
    # Prefer Starlette/FastAPI Request for type hints if available
    from starlette.requests import Request  # type: ignore
except Exception:  # pragma: no cover
    Request = Any  # type: ignore

from restailor.app_config import AbuseIpAsnSettings


class NetTier(str, Enum):
    RESIDENTIAL = "RESIDENTIAL"
    UNIVERSITY = "UNIVERSITY"
    DATACENTER = "DATACENTER"
    UNKNOWN = "UNKNOWN"


def _contains_keyword(hay: str | None, keywords: list[str]) -> bool:
    if not hay:
        return False
    text = hay.casefold()
    for kw in keywords:
        try:
            if kw and kw.casefold() in text:
                return True
        except (AttributeError, TypeError):
            # Non-string keyword; ignore
            pass
    return False


def _is_rfc1918_or_cgnat(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address((ip or "").strip())
        # ipaddress.is_private covers RFC1918 IPv4, CGNAT 100.64/10, and IPv6 ULA
        return bool(ip_obj.is_private)
    except (ValueError, ipaddress.AddressValueError):
        return False


def classify_ip_asn(
    ip: str,
    asn: str | None,
    org: str | None,
    settings: AbuseIpAsnSettings,
) -> NetTier:
    """Classify a client into a network tier using only local signals.

    Evaluation order:
    1) Explicit ASN allowlists (university/datacenter)
    2) Organization keyword heuristics (university/datacenter)
    3) Private/RFC1918/CGNAT IPs -> Residential (likely)
    4) Otherwise -> Unknown
    """
    asn_norm = (asn or "").strip()
    if asn_norm:
        if asn_norm in (settings.university_asns or []):
            return NetTier.UNIVERSITY
        if asn_norm in (settings.datacenter_asns or []):
            return NetTier.DATACENTER

    if _contains_keyword(org, settings.university_org_keywords or []):
        return NetTier.UNIVERSITY
    if _contains_keyword(org, settings.datacenter_org_keywords or []):
        return NetTier.DATACENTER

    if _is_rfc1918_or_cgnat(ip):
        return NetTier.RESIDENTIAL

    return NetTier.UNKNOWN


def _get_header_from_request(request: Any, header_name: str) -> str | None:
    try:
        headers: Mapping[str, Any] = getattr(request, "headers", {})  # type: ignore
        if not headers:
            return None
        val = headers.get(header_name)
        if val is None and hasattr(headers, "get"):  # case-insensitive dict in Starlette
            val = headers.get(header_name)
        if val is None:
            return None
        s = str(val).strip()
        return s if s else None
    except Exception:
        return None


def get_asn_from_headers(request: Any, header_name: str) -> str | None:
    """Extract ASN from request headers using the configured header name."""
    return _get_header_from_request(request, header_name)


def get_org_from_headers(request: Any, header_name: str) -> str | None:
    """Extract organization name from request headers using the configured header name."""
    return _get_header_from_request(request, header_name)


__all__ = [
    "NetTier",
    "classify_ip_asn",
    "get_asn_from_headers",
    "get_org_from_headers",
]
