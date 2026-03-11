#!/usr/bin/env python3
"""Test unchecking hired flag via API."""

import asyncio
import sys
from restailor.models import Application, User
from restailor.auth import get_db

async def main():
    async for db in get_db():
        # Get user 4
        user = db.query(User).filter(User.id == 4).first()
        if not user:
            print("User 4 not found")
            return
        
        # Find one application with is_hired=True
        app = db.query(Application).filter(
            Application.user_id == 4,
            Application.is_hired == True
        ).first()
        
        if not app:
            print("No applications with is_hired=True found for user 4")
            return
        
        print(f"Found application: {app.applied_key}")
        print(f"  Before: is_hired={app.is_hired}, is_offer={app.is_offer}, is_interviewing={app.is_interviewing}")
        
        # Simulate what the API does when unchecking H
        from restailor.stage_utils import stage_payload
        
        # Current state
        current_state = stage_payload(
            getattr(app, "stage", None),
            app.is_interviewing,
            app.is_offer,
            app.is_hired,
        )
        _, current_flags, _ = current_state
        
        print(f"  Current flags: {current_flags}")
        
        # Set hired to False (what happens when you uncheck)
        current_flags["hired"] = False
        
        # Normalize
        normalized_state = stage_payload(
            None,
            current_flags.get("interviewing"),
            current_flags.get("offer"),
            current_flags.get("hired"),
        )
        _, normalized_flags, _ = normalized_state
        
        print(f"  Normalized flags after setting hired=False: {normalized_flags}")
        
        # What gets written to DB
        app.is_interviewing = bool(normalized_flags.get("interviewing"))
        app.is_offer = bool(normalized_flags.get("offer"))
        app.is_hired = bool(normalized_flags.get("hired"))
        
        print(f"  After: is_hired={app.is_hired}, is_offer={app.is_offer}, is_interviewing={app.is_interviewing}")
        
        # Don't commit - this is just a test
        db.rollback()
        
        return

if __name__ == "__main__":
    asyncio.run(main())
