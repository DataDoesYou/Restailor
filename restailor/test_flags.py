from __future__ import annotations

"""
Lightweight helpers to detect when the server is running under an automated test harness.

Covers:
- Pytest: PYTEST_CURRENT_TEST is present.
- Playwright E2E: E2E_TEST_MODE is truthy (set in our Playwright configs),
  or PW_TEST/PLAYWRIGHT_TEST env vars are truthy when running via Playwright.

Never infer from email/username heuristics here—this is strictly environment-based.
"""

import os


def _truthy(val: str | None) -> bool:
    v = (val or "").strip().lower()
    return v in {"1", "true", "yes", "on"}


def is_automated_test_run() -> bool:
    """Return True when running under an automated test harness.

    Safe to call anywhere; depends only on environment variables.
    """
    try:
        if "PYTEST_CURRENT_TEST" in os.environ:
            return True
        if _truthy(os.getenv("E2E_TEST_MODE")):
            return True
        # Playwright sets PW_TEST=1 in Node test runner; include a couple common flags defensively
        if _truthy(os.getenv("PW_TEST")):
            return True
        if _truthy(os.getenv("PLAYWRIGHT_TEST")):
            return True
    except Exception:
        # On any error, default to False (don't accidentally mark real data as test)
        return False
    return False
