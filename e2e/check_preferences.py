"""
Simple script to check user_preferences table state.
Run with: doppler run -- poetry run python e2e/check_preferences.py [user_id]
"""

import json
import os
import sys
import psycopg2
from datetime import datetime


def get_db_connection():
    """Get database connection."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL not set - run with doppler")
    return psycopg2.connect(db_url)


def show_all_preferences():
    """Show all user preferences."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, settings, version, updated_at 
                FROM user_preferences 
                ORDER BY user_id
            """)
            rows = cur.fetchall()
            
            if not rows:
                print("📭 No user preferences found in database")
                return
            
            print(f"\n📊 Found {len(rows)} user(s) with preferences:\n")
            print("="*80)
            
            for row in rows:
                user_id, settings, version, updated_at = row
                print(f"\n👤 User ID: {user_id}")
                print(f"   Version: {version}")
                print(f"   Updated: {updated_at}")
                print(f"   Settings:")
                print(json.dumps(settings, indent=6))
                print("-"*80)
                
    finally:
        conn.close()


def show_user_preferences(user_id: int):
    """Show preferences for specific user."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT settings, version, updated_at 
                FROM user_preferences 
                WHERE user_id = %s
            """, (user_id,))
            row = cur.fetchone()
            
            if not row:
                print(f"📭 No preferences found for user {user_id}")
                return
            
            settings, version, updated_at = row
            print(f"\n👤 User {user_id} Preferences:")
            print("="*80)
            print(f"Version: {version}")
            print(f"Updated: {updated_at}")
            print(f"\nSettings:")
            print(json.dumps(settings, indent=2))
            print("="*80)
            
    finally:
        conn.close()


def clear_user_preferences(user_id: int):
    """Clear preferences for specific user."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_preferences WHERE user_id = %s", (user_id,))
            conn.commit()
            print(f"✅ Cleared preferences for user {user_id}")
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "clear" and len(sys.argv) > 2:
            user_id = int(sys.argv[2])
            clear_user_preferences(user_id)
        else:
            user_id = int(sys.argv[1])
            show_user_preferences(user_id)
    else:
        show_all_preferences()
