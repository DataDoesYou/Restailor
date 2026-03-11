"""One-time migration: Upgrade trial models in system_settings to new model IDs.

This script reads the trial_models list from the system_settings table,
applies the automatic upgrade logic (e.g., gpt-5.1-thinking -> gpt-5.4),
and writes the upgraded list back to the database.

Run this once after deploying the GPT-5.2 model changes.
"""
import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from restailor.db import SessionLocal
from restailor.models import SystemSettings
from restailor.settings_schemas import apply_model_upgrades
from sqlalchemy.dialects.postgresql import insert


def upgrade_trial_models():
    """Upgrade trial models in database to new model IDs."""
    db = SessionLocal()
    try:
        # Load current settings
        settings_rows = db.query(SystemSettings).all()
        settings_dict = {row.key: row.value for row in settings_rows}
        
        # Check if we have credits_signup_grant config
        if "credits_signup_grant" not in settings_dict:
            print("No credits_signup_grant found in system_settings")
            return
        
        grant_config = settings_dict["credits_signup_grant"]
        
        # Check if trial_models exists
        if "trial_models" not in grant_config or not grant_config["trial_models"]:
            print("No trial_models configured")
            return
        
        old_models = grant_config["trial_models"]
        print(f"Current trial models: {json.dumps(old_models, indent=2)}")
        
        # Apply upgrade logic
        new_models = apply_model_upgrades(old_models)
        print(f"Upgraded trial models: {json.dumps(new_models, indent=2)}")
        
        # Check if anything changed
        if old_models == new_models:
            print("No upgrades needed - models are already up to date")
            return
        
        # Update the config
        grant_config["trial_models"] = new_models
        
        # Save back to database using upsert
        stmt = insert(SystemSettings).values(
            key="credits_signup_grant",
            value=grant_config,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={"value": grant_config},
        )
        db.execute(stmt)
        db.commit()
        
        print("✅ Successfully upgraded trial models in database")
        
    except Exception as ex:
        print(f"❌ Error upgrading trial models: {ex}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    upgrade_trial_models()
