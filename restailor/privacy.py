from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from . import models


def should_persist_user_content(user: "models.User") -> bool:
    """Return True if it's permissible to persist user content in DB.

    When the user opts out via dont_save_future_data, we must avoid storing
    resume/JD/generation outputs and last-inputs fields. Streaming to the
    client is still allowed.
    """
    try:
        return not bool(getattr(user, "dont_save_future_data", False))
    except Exception:
        # Default to safest behavior if field missing
        return False
