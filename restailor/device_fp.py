from __future__ import annotations

import re
import hashlib
from typing import Optional, Tuple, Dict


_BROWSER_PATTERNS = [
    (re.compile(r"EdgA?/(\d+)", re.I), "Edge"),  # Edge on Android/iOS also EdgA/
    (re.compile(r"OPR/(\d+)", re.I), "Opera"),
    (re.compile(r"Chrome/(\d+)", re.I), "Chrome"),
    (re.compile(r"Firefox/(\d+)", re.I), "Firefox"),
    (re.compile(r"Version/(\d+).*Safari", re.I), "Safari"),
]

_OS_PATTERNS = [
    (re.compile(r"Windows NT 10\.0", re.I), ("Windows", 10)),
    (re.compile(r"Windows NT 11\.0", re.I), ("Windows", 11)),
    (re.compile(r"Windows NT 12\.0", re.I), ("Windows", 12)),
    (re.compile(r"Mac OS X (\d+)[_\.](\d+)", re.I), "_mac"),
    (re.compile(r"Android (\d+)", re.I), "_android"),
    (re.compile(r"iPhone OS (\d+)_", re.I), ("iOS", None)),
    (re.compile(r"iPad; CPU OS (\d+)_", re.I), ("iOS", None)),
    (re.compile(r"Linux", re.I), ("Linux", None)),
]


def _parse_browser(ua: str) -> Tuple[str, Optional[int]]:
    text = ua or ""
    # Try common UA tokens like 'Chrome/125'
    for pat, fam in _BROWSER_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return fam, int(m.group(1))
            except Exception:
                return fam, None
    # Fallback: our label format like 'Chrome 125 on macOS 14 (arm64)'
    m2 = re.search(r"\b(Edge|Opera|Chrome|Firefox|Safari)\s+(\d+)\b", text, re.I)
    if m2:
        fam = m2.group(1).title()
        try:
            return fam, int(m2.group(2))
        except Exception:
            return fam, None
    return "Other", None


def _parse_os(ua: str) -> Tuple[str, Optional[int]]:
    text = ua or ""
    for pat, marker in _OS_PATTERNS:
        m = pat.search(text)
        if m:
            if marker == "_mac":
                try:
                    major = int(m.group(1))
                except Exception:
                    major = None
                return "macOS", major
            if marker == "_android":
                try:
                    return "Android", int(m.group(1))
                except Exception:
                    return "Android", None
            fam, maj = marker if isinstance(marker, tuple) else (marker, None)
            return fam, maj
    # Fallback for our label format: '... on Windows 10 (...', '... on macOS 14 ...'
    m2 = re.search(r"\b(Windows|macOS|Android|iOS|Linux)\s+(\d+)\b", text, re.I)
    if m2:
        fam = m2.group(1)
        try:
            return fam, int(m2.group(2))
        except Exception:
            return fam, None
    # Also allow bare family names without version present in labels
    m3 = re.search(r"\b(Windows|macOS|Android|iOS|Linux)\b", text, re.I)
    if m3:
        fam = m3.group(1)
        return fam, None
    return "OtherOS", None


def _parse_arch(ua: str) -> str:
    u = ua.lower() if ua else ""
    if any(x in u for x in ("arm64", "aarch64")):
        return "arm64"
    if any(x in u for x in ("x86_64", "win64; x64", "x64")):
        return "x86_64"
    if "i686" in u or "x86" in u:
        return "x86"
    return "unknown"


def normalize_user_agent(ua: Optional[str]) -> Dict[str, Optional[str | int]]:
    fam, maj = _parse_browser(ua or "")
    osf, osmaj = _parse_os(ua or "")
    arch = _parse_arch(ua or "")
    return {
        "browser_family": fam,
        "browser_major": maj,
        "os_family": osf,
        "os_major": osmaj,
        "arch": arch,
    }


def make_device_key(ua: Optional[str], ip_prefix: Optional[str]) -> str:
    n = normalize_user_agent(ua)
    parts = [
        str(n.get("browser_family") or ""),
        str(n.get("browser_major") or ""),
        str(n.get("os_family") or ""),
        str(n.get("os_major") or ""),
        str(n.get("arch") or ""),
        str(ip_prefix or ""),
    ]
    s = ":".join(parts).lower()
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hash_entropy(entropy: Optional[str]) -> Optional[str]:
    if not entropy:
        return None
    try:
        h = hashlib.sha256(str(entropy).encode("utf-8")).hexdigest()
        # Shorten to reduce storage noise
        return h[:16]
    except Exception:
        return None


def label_for_storage(ua: Optional[str], entropy: Optional[str] = None) -> str:
    n = normalize_user_agent(ua)
    label = f"{n['browser_family']} {n['browser_major']} on {n['os_family']} {n['os_major']} ({n['arch']})"
    e = _hash_entropy(entropy)
    return f"{label} | e:{e}" if e else label
