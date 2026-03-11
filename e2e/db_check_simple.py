"""
Direct database check - no imports that might trigger server reloads.
"""
import sys
import json


def main():
    # Import psycopg2 here to avoid triggering server reloads on module scan
    import psycopg2
    import os
    
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set")
        return 1
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Count total preferences
        cur.execute("SELECT COUNT(*) FROM user_preferences")
        count = cur.fetchone()[0]
        
        print(f"\n{'='*80}")
        print(f"USER PREFERENCES TABLE: {count} row(s)")
        print(f"{'='*80}\n")
        
        if count == 0:
            print("📭 Table is empty - no users have saved preferences yet\n")
            cur.close()
            conn.close()
            return 0
        
        # Show all rows
        cur.execute("""
            SELECT user_id, settings, version, updated_at 
            FROM user_preferences 
            ORDER BY updated_at DESC
        """)
        rows = cur.fetchall()
        
        for user_id, settings, version, updated_at in rows:
            print(f"👤 USER {user_id}")
            print(f"   Version: {version}")
            print(f"   Updated: {updated_at}")
            print(f"   Settings: {json.dumps(settings, indent=6)}")
            print(f"{'-'*80}\n")
        
        cur.close()
        conn.close()
        return 0
        
    except Exception as e:
        print(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
