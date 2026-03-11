from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Optional

from restailor.app_config import AbuseIpAsnSettings
from services.network_risk import NetTier


Decision = Literal["allow_trial", "allow_only_with_2fa", "require_payment", "hard_block"]


@dataclass
class IpTrialPolicy:
    """Implements per-IP (and optional per-ASN) trial windows with a simple ladder.

    Redis contract (async): expects methods get(key) -> Optional[str], incr(key) -> int, expire(key, ttl) -> None.
    """

    redis: Any
    settings: AbuseIpAsnSettings

    def _today_str(self) -> str:
        # Use UTC to avoid TZ ambiguity across servers
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _ip_key(self, ip: str) -> str:
        return f"ip_trial_count:{ip}:{self._today_str()}"

    def _asn_key(self, asn: str) -> str:
        return f"asn_trial_count:{asn}:{self._today_str()}"

    def _cap_for_tier(self, tier: NetTier) -> int:
        s = self.settings
        if tier == NetTier.RESIDENTIAL:
            return int(s.cap_residential_per_ip)
        if tier == NetTier.UNIVERSITY:
            return int(s.cap_university_per_ip)
        if tier == NetTier.DATACENTER:
            return int(s.cap_datacenter_per_ip)
        # UNKNOWN fallback
        return int(s.cap_unknown_per_ip)

    def _overcap_action_for_tier(self, tier: NetTier) -> Decision:
        s = self.settings
        if tier == NetTier.RESIDENTIAL:
            return s.over_cap_residential  # type: ignore[return-value]
        if tier == NetTier.UNIVERSITY:
            return s.over_cap_university  # type: ignore[return-value]
        if tier == NetTier.DATACENTER:
            return s.over_cap_datacenter  # type: ignore[return-value]
        return s.over_cap_unknown  # type: ignore[return-value]

    async def _get_count(self, key: str) -> int:
        try:
            val = await self.redis.get(key)
            if val is None:
                return 0
            return int(val)
        except Exception:
            return 0

    async def record_and_decide(
        self,
        ip: str,
        asn: Optional[str],
        org: Optional[str],
        net_tier: NetTier,
    ) -> Decision:
        """Read counters and either increment within window or return over-cap decision.

        - Uses per-tier caps from settings.
        - Only increments counters when allowing a trial.
        - TTL for counters is settings.window_seconds.
        """
        cap = self._cap_for_tier(net_tier)
        ttl = int(self.settings.window_seconds)
        ip_key = self._ip_key(ip)
        current = await self._get_count(ip_key)
        if current < cap:
            # increment IP and (optionally) ASN; set TTL on first creation
            new_val = await self.redis.incr(ip_key)
            if int(new_val) == 1:
                try:
                    await self.redis.expire(ip_key, ttl)
                except Exception as ex:
                    # Best-effort TTL setting; failure shouldn't block trials
                    import logging as _log
                    _log.getLogger(__name__).debug("ip_trial_policy: expire ip_key failed: %s", ex)
            if asn:
                try:
                    asn_key = self._asn_key(asn)
                    asn_new = await self.redis.incr(asn_key)
                    if int(asn_new) == 1:
                        await self.redis.expire(asn_key, ttl)
                except Exception as ex:
                    import logging as _log
                    _log.getLogger(__name__).debug("ip_trial_policy: expire asn_key failed: %s", ex)
            return "allow_trial"
        # over cap: do not increment; return action for this tier
        return self._overcap_action_for_tier(net_tier)


def decision_to_hint(decision: Decision) -> dict:
    """Convert a policy decision into a simple UI/API hint payload.

    Pure function; safe for unit tests without external dependencies.
    """
    if decision == "allow_trial":
        return {
            "eligible": True,
            "reason": "trial available in current window",
            "cta": [],
        }
    if decision == "allow_only_with_2fa":
        return {
            "eligible": True,
            "reason": "trial requires multi-factor authentication",
            "cta": ["Enable 2FA", "Add passkey"],
        }
    if decision == "require_payment":
        return {
            "eligible": False,
            "reason": "trial cap exceeded; payment required",
            "cta": ["Buy credits"],
        }
    # hard_block
    return {
        "eligible": False,
        "reason": "trial blocked due to network risk",
        "cta": [],
    }


__all__ = [
    "IpTrialPolicy",
    "decision_to_hint",
]
