"""Quick script to verify system_settings table contents."""
from restailor.db import SessionLocal
from restailor.models import SystemSettings
import json

db = SessionLocal()
try:
    settings = db.query(SystemSettings).all()
    print(f"Found {len(settings)} settings in database:\n")
    
    for s in settings:
        print(f"Key: {s.key}")
        print(f"Value: {json.dumps(s.value, indent=2)}")
        print(f"Updated: {s.updated_at}")
        print("-" * 60)
finally:
    db.close()
