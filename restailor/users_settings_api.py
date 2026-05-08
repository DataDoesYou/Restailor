"""User settings API endpoints.

Provides authenticated endpoints for managing user preferences stored in the
user_preferences table with server-side validation against model allowlists.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session
from sqlalchemy import select, text

from restailor import auth as auth_dep
from restailor.models import User, UserPreferences
from restailor.settings_schemas import ModelSettings, resolve_effective_settings

logger = logging.getLogger(__name__)

users_settings_router = APIRouter(prefix="/users/me/model-settings", tags=["user-model-settings"])


# --- Request/Response Models ---

class GetSettingsResponse(BaseModel):
    """Response for GET /users/me/settings."""
    settings: ModelSettings
    
    model_config = ConfigDict(
        # Allow datetime serialization
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )


class PutSettingsRequest(BaseModel):
    """Request body for PUT /users/me/settings."""
    settings: ModelSettings
    expected_updated_at: str | None = Field(
        None,
        alias="expectedUpdatedAt",
        description="ISO timestamp for optimistic concurrency control (409 if mismatch)"
    )
    
    model_config = ConfigDict(
        populate_by_name=True,  # Accept both snake_case and camelCase
    )


class PutSettingsResponse(BaseModel):
    """Response for PUT /users/me/settings."""
    settings: ModelSettings
    message: str = "Settings updated successfully"
    
    model_config = ConfigDict(
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )


# --- Endpoints ---

@users_settings_router.get("", response_model=GetSettingsResponse)
async def get_user_model_settings(
    current_user: User = Depends(auth_dep.get_current_user),
    db: Session = Depends(auth_dep.get_db),
) -> GetSettingsResponse:
    """Get current user's model preferences.
    
    Returns the user's settings from the user_preferences table.
    If no settings exist yet, returns default ModelSettings.
    
    **Authentication**: Requires valid bearer token.
    
    **Returns**:
    - `settings`: ModelSettings object with user preferences
    """
    user_id = int(getattr(current_user, "id", 0))
    
    try:
        # Query user_preferences table
        stmt = select(UserPreferences).where(UserPreferences.user_id == user_id)
        result = db.execute(stmt).scalar_one_or_none()
        
        if result is None:
            # No preferences yet - return defaults
            logger.debug(f"No settings found for user {user_id}, returning defaults")
            return GetSettingsResponse(settings=ModelSettings())
        
        # Parse JSONB settings column and validate
        settings_dict = getattr(result, "settings", {}) or {}
        
        # Add metadata from table columns
        settings_dict["updated_at"] = getattr(result, "updated_at", None)
        settings_dict["version"] = getattr(result, "version", 1)
        
        # Validate against current allowlist
        try:
            settings = ModelSettings(**settings_dict)
        except ValidationError as e:
            # Settings in DB have invalid model IDs (config changed?)
            # Log warning and return defaults rather than 500
            logger.warning(
                f"Invalid settings in DB for user {user_id}: {e}. "
                "Returning defaults. User should update their preferences."
            )
            return GetSettingsResponse(settings=ModelSettings())
        
        # Apply model upgrades and future org/tenant policy merge
        # This transparently upgrades users from deprecated models to new ones
        # org_defaults = get_org_defaults(current_user.org_id)  # Future feature
        settings = resolve_effective_settings(settings, org_defaults=None)
        
        return GetSettingsResponse(settings=settings)
        
    except Exception as e:
        logger.error(f"Error fetching settings for user {user_id}: err_type={type(e).__name__} err_msg={str(e)[:200]}")
        # Return defaults on error rather than failing the request
        return GetSettingsResponse(settings=ModelSettings())


@users_settings_router.put("", response_model=PutSettingsResponse)
async def update_user_model_settings(
    body: PutSettingsRequest,
    current_user: User = Depends(auth_dep.get_current_user),
    db: Session = Depends(auth_dep.get_db),
) -> PutSettingsResponse:
    """Update current user's model preferences.
    
    Validates all model IDs against the server-side allowlist before storing.
    Implements optimistic concurrency control via `expectedUpdatedAt`.
    
    **Authentication**: Requires valid bearer token.
    
    **Request Body**:
    - `settings`: ModelSettings object with new preferences
    - `expectedUpdatedAt` (optional): ISO timestamp for conflict detection
    
    **Returns**:
    - `settings`: Updated ModelSettings with new `updated_at` timestamp
    - `message`: Success message
    
    **Errors**:
    - `400`: Invalid model IDs (not in allowlist)
    - `409`: Conflict - settings were modified by another request
    - `422`: Validation error in request body
    """
    user_id = int(getattr(current_user, "id", 0))
    
    try:
        # The body.settings has already been validated by Pydantic against the allowlist
        # (ModelSettings validator runs automatically)
        settings = body.settings
        
        # Check for existing row
        stmt = select(UserPreferences).where(UserPreferences.user_id == user_id)
        existing = db.execute(stmt).scalar_one_or_none()
        
        # Optimistic concurrency check
        if body.expected_updated_at:
            try:
                expected_dt = datetime.fromisoformat(body.expected_updated_at.replace('Z', '+00:00'))
            except (ValueError, AttributeError) as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid expectedUpdatedAt format: {e}"
                )
            
            if existing is None:
                # Client expected a row but we don't have one
                raise HTTPException(
                    status_code=409,
                    detail="Conflict: No existing settings found. Please refresh and try again."
                )
            
            existing_updated_at = getattr(existing, "updated_at", None)
            if existing_updated_at is None:
                # Should not happen but handle gracefully
                raise HTTPException(
                    status_code=409,
                    detail="Conflict: Settings timestamp missing. Please refresh and try again."
                )
            
            # Compare timestamps at millisecond precision to detect concurrent modifications
            # Convert to UTC milliseconds for comparison
            expected_ms = int(expected_dt.timestamp() * 1000)
            existing_ms = int(existing_updated_at.timestamp() * 1000)
            
            if expected_ms != existing_ms:
                logger.warning(
                    f"Concurrency conflict for user {user_id}: "
                    f"expected {expected_dt}, got {existing_updated_at}"
                )
                raise HTTPException(
                    status_code=409,
                    detail="Conflict: Settings were modified by another request. Please refresh and try again."
                )
        
        # Prepare settings for storage
        now = datetime.now(timezone.utc)
        settings_dict = settings.model_dump(exclude={"updated_at"})  # Don't store updated_at in JSONB
        if existing is not None and isinstance(getattr(existing, "settings", None), dict):
            byok_sync_modes = existing.settings.get("byok_sync_modes")
            if isinstance(byok_sync_modes, dict):
                settings_dict["byok_sync_modes"] = {str(k): bool(v) for k, v in byok_sync_modes.items()}
        
        # Ensure version is set (for future schema migrations)
        if "version" not in settings_dict:
            settings_dict["version"] = 1
        
        if existing is None:
            # Insert new row
            new_prefs = UserPreferences(
                user_id=user_id,
                settings=settings_dict,
                version=settings_dict["version"],
                updated_at=now,
            )
            db.add(new_prefs)
            logger.info(f"Creating new settings for user {user_id}")
        else:
            # Update existing row
            existing.settings = settings_dict
            existing.version = settings_dict["version"]
            existing.updated_at = now
            logger.info(f"Updating settings for user {user_id}")
        
        db.commit()
        
        # Return updated settings with new timestamp
        settings.updated_at = now
        
        return PutSettingsResponse(
            settings=settings,
            message="Settings updated successfully"
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions (409, 400, etc.)
        db.rollback()
        raise
    except ValidationError as e:
        # Pydantic validation failed (invalid model IDs)
        db.rollback()
        logger.warning(f"Validation error for user {user_id}: {e}")
        # Extract first error message for cleaner client response
        errors = e.errors()
        if errors:
            first_error = errors[0]
            msg = first_error.get("msg", str(e))
            # Check if it's a model ID validation error
            if "invalid model id" in msg.lower():
                detail = f"Invalid model ID: {msg}"
            else:
                detail = f"Validation error: {msg}"
        else:
            detail = "Validation error: Invalid settings"
        
        raise HTTPException(status_code=400, detail=detail)
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating settings for user {user_id}: err_type={type(e).__name__} err_msg={str(e)[:200]}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while updating settings"
        )
