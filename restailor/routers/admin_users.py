from typing import Annotated, List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, desc
from pydantic import BaseModel
from datetime import datetime

from restailor.db import get_db
from restailor.models import User, UserPreferences
from restailor import auth as auth_dep
from restailor.stepup import require_recent_stepup

router = APIRouter(prefix="/admin/users", tags=["admin"])

class UserListItem(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime
    credits: int
    trial_mode_override: Optional[Literal["enabled", "disabled"]] = None
    is_active: bool

class TrialModeReq(BaseModel):
    override: Optional[Literal["enabled", "disabled"]] = None

@router.get("", response_model=List[UserListItem])
async def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(auth_dep.require_admin)],
    _step: Annotated[bool, Depends(require_recent_stepup(admin_only=True))],
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None
):
    query = select(User, UserPreferences).outerjoin(UserPreferences, User.id == UserPreferences.user_id)
    
    if search:
        query = query.where(User.username.ilike(f"%{search}%"))
    
    query = query.order_by(desc(User.created_at)).limit(limit).offset(offset)
    
    results = db.execute(query).all()
    
    users = []
    for row in results:
        user = row[0]
        prefs = row[1]
        
        override = None
        if prefs and prefs.settings:
            override = prefs.settings.get("trial_mode_override")
            
        users.append(UserListItem(
            id=user.id,
            email=user.username,
            role=user.role,
            created_at=user.created_at,
            credits=user.credits,
            trial_mode_override=override,
            is_active=user.is_active
        ))
        
    return users

@router.post("/{user_id}/trial-mode")
async def set_trial_mode(
    user_id: int,
    req: TrialModeReq,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(auth_dep.require_admin)],
    _step: Annotated[bool, Depends(require_recent_stepup(admin_only=True))],
):
    # Check if user exists
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Get or create preferences
    prefs = db.get(UserPreferences, user_id)
    if not prefs:
        prefs = UserPreferences(user_id=user_id, settings={})
        db.add(prefs)
    
    # Update setting
    current_settings = dict(prefs.settings) if prefs.settings else {}
    
    if req.override:
        current_settings["trial_mode_override"] = req.override
    else:
        # Reset to auto
        if "trial_mode_override" in current_settings:
            del current_settings["trial_mode_override"]
        
    prefs.settings = current_settings
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(prefs, "settings")
    
    db.commit()
    
    return {"ok": True, "override": req.override}

