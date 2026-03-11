from __future__ import annotations

from sqlalchemy.orm import Session
import os
from sqlalchemy import select
from .test_flags import is_automated_test_run

from . import schemas
from .models import User
from .security import get_password_hash


def get_user_by_username(db: Session, username: str) -> User | None:
    # Normalize to lowercase for email lookup
    return db.execute(select(User).where(User.username == (username or "").lower())).scalar_one_or_none()


def create_user(db: Session, user: schemas.UserCreate) -> User:
    hashed_pw = get_password_hash(user.password)
    # Store emails lowercased for uniqueness/consistency
    extra = {}
    try:
        if getattr(user, "visitorId", None):
            extra["browser_fingerprint"] = str(user.visitorId)
    except Exception as ex:
        import logging as _log
        _log.getLogger(__name__).debug("crud.create_user: visitorId extraction failed: %s", ex)
    # Mark test data only when running under an automated test harness; never based on email heuristics.
    _is_test = is_automated_test_run()
    db_user = User(
        username=str(user.username).lower(),
        hashed_password=hashed_pw,
        public_profile=False,
        dont_save_future_data=False,
        is_test=_is_test,
        **extra,
    )  # is_verified defaults False
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user
