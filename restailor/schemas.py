from __future__ import annotations

from pydantic import BaseModel, EmailStr
from pydantic import StrictBool, StrictStr
try:
    # Pydantic v2
    from pydantic import ConfigDict  # type: ignore
except Exception:  # pragma: no cover
    ConfigDict = None  # type: ignore
from typing import Optional


class UserCreate(BaseModel):
    username: EmailStr
    password: str
    visitorId: Optional[str] = None


class User(BaseModel):
    id: int
    username: EmailStr
    is_active: bool = True
    is_verified: bool = False
    role: str = "user"
    credits: int = 0
    # Pydantic v2 style config
    if 'ConfigDict' in globals() and ConfigDict is not None:  # type: ignore[name-defined]
        model_config = ConfigDict(from_attributes=True)  # type: ignore[assignment]
    else:  # Fallback for v1 if ever needed
        class Config:  # type: ignore[no-redef]
            from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


class CurrentUser(BaseModel):
    id: int
    username: EmailStr
    is_active: bool = True
    is_verified: bool = False
    role: str = "user"
    credits: int = 0
    if 'ConfigDict' in globals() and ConfigDict is not None:  # type: ignore[name-defined]
        model_config = ConfigDict(from_attributes=True)  # type: ignore[assignment]
    else:
        class Config:  # type: ignore[no-redef]
            from_attributes = True


class UserInputs(BaseModel):
    resume_text: str | None = None
    jd_text: str | None = None


class UserSettings(BaseModel):
    public_profile: StrictBool
    dont_save_future_data: StrictBool
    byok_sync_modes: dict[str, StrictBool] | None = None

    if 'ConfigDict' in globals() and ConfigDict is not None:  # type: ignore[name-defined]
        model_config = ConfigDict(extra='forbid')  # type: ignore[assignment]
    else:
        class Config:  # type: ignore[no-redef]
            extra = 'forbid'


class Confirm(BaseModel):
    confirm: StrictBool

    if 'ConfigDict' in globals() and ConfigDict is not None:  # type: ignore[name-defined]
        model_config = ConfigDict(extra='forbid')  # type: ignore[assignment]
    else:
        class Config:  # type: ignore[no-redef]
            extra = 'forbid'


class ConfirmText(BaseModel):
    confirm_text: StrictStr

# Backward- and forward-compatible confirm model for sensitive actions
class ConfirmSensitive(BaseModel):
    # Accept either a password (preferred) or legacy confirm phrase
    password: StrictStr | None = None
    confirm_text: StrictStr | None = None

    if 'ConfigDict' in globals() and ConfigDict is not None:  # type: ignore[name-defined]
        model_config = ConfigDict(extra='forbid')  # type: ignore[assignment]
    else:
        class Config:  # type: ignore[no-redef]
            extra = 'forbid'
