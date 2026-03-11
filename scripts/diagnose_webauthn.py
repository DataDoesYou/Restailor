#!/usr/bin/env python3
"""
WebAuthn Production Diagnostic Script

Run this in production to diagnose invalid_pending_token issues.
Usage: python scripts/diagnose_webauthn.py
"""

import os
import sys
from datetime import datetime, timezone, timedelta
import jwt

def check_secret_key():
    """Verify AUTH_SECRET_KEY is properly configured."""
    print("\n=== Checking AUTH_SECRET_KEY ===")
    try:
        # Try keyring first
        try:
            import keyring
            v = keyring.get_password("restailor", "AUTH_SECRET_KEY")
            if v and v.strip():
                print("✓ SECRET_KEY loaded from keyring")
                return v
        except Exception as e:
            print(f"⚠ Keyring read failed: {e}")
        
        # Try environment
        v = os.getenv("AUTH_SECRET_KEY")
        if v and v.strip():
            print("✓ SECRET_KEY loaded from environment")
            return v
        
        print("✗ AUTH_SECRET_KEY not found!")
        return None
    except Exception as e:
        print(f"✗ Error checking SECRET_KEY: {e}")
        return None

def check_clock_skew():
    """Check system clock for potential skew."""
    print("\n=== Checking System Clock ===")
    try:
        now = datetime.now(timezone.utc)
        print(f"System UTC time: {now.isoformat()}")
        
        # Create a test JWT
        secret = check_secret_key()
        if not secret:
            print("Cannot create test JWT without SECRET_KEY")
            return
        
        # Test token with 15 minute expiry
        exp = now + timedelta(minutes=15)
        payload = {"sub": "test@example.com", "scope": "pending_2fa", "exp": exp}
        token = jwt.encode(payload, secret, algorithm="HS256")
        
        print(f"\nTest token created:")
        print(f"  Expires at: {exp.isoformat()}")
        
        # Try to decode immediately
        try:
            decoded = jwt.decode(token, secret, algorithms=["HS256"])
            print("✓ Token validates immediately (no clock skew)")
        except jwt.ExpiredSignatureError:
            print("✗ CLOCK SKEW DETECTED! Token appears expired immediately!")
            print("  This means system clock is ahead of actual time.")
        except Exception as e:
            print(f"✗ Token validation error: {e}")
        
    except Exception as e:
        print(f"✗ Error checking clock: {e}")

def check_redis():
    """Check Redis connectivity."""
    print("\n=== Checking Redis Connection ===")
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("⚠ REDIS_URL not set (will use in-memory fallback)")
        return
    
    print(f"Redis URL: {redis_url[:30]}...")
    
    try:
        import redis.asyncio as redis_async
        import asyncio
        
        async def ping_redis():
            r = redis_async.from_url(redis_url, encoding="utf-8", decode_responses=True)
            try:
                await r.ping()
                print("✓ Redis connection successful")
                await r.close()
                return True
            except Exception as e:
                print(f"✗ Redis connection failed: {e}")
                await r.close()
                return False
        
        result = asyncio.run(ping_redis())
        if not result:
            print("⚠ WebAuthn challenges may not persist across instances!")
            
    except ImportError:
        print("⚠ redis package not installed, skipping Redis check")
    except Exception as e:
        print(f"✗ Error checking Redis: {e}")

def check_token_config():
    """Check token expiry configuration."""
    print("\n=== Checking Token Configuration ===")
    
    # Check environment variables
    access_ttl = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    pending_ttl = os.getenv("PENDING2_TOKEN_EXPIRE_MINUTES", "15")
    reauth_ttl = os.getenv("REAUTH_TOKEN_EXPIRE_MINUTES", "5")
    
    print(f"ACCESS_TOKEN_EXPIRE_MINUTES: {access_ttl}")
    print(f"PENDING2_TOKEN_EXPIRE_MINUTES: {pending_ttl}")
    print(f"REAUTH_TOKEN_EXPIRE_MINUTES: {reauth_ttl}")
    
    try:
        pending_int = int(pending_ttl)
        if pending_int < 5:
            print("⚠ pending_2fa token TTL is very short! User might not complete WebAuthn in time.")
        elif pending_int > 30:
            print("⚠ pending_2fa token TTL is quite long (security consideration).")
        else:
            print("✓ Token TTL looks reasonable")
    except ValueError:
        print("✗ Invalid PENDING2_TOKEN_EXPIRE_MINUTES value!")

def check_instance_info():
    """Display instance information."""
    print("\n=== Instance Information ===")
    print(f"Hostname: {os.getenv('HOSTNAME', 'unknown')}")
    print(f"Render Instance ID: {os.getenv('RENDER_INSTANCE_ID', 'not set')}")
    print(f"Environment: {os.getenv('ENVIRONMENT', 'unknown')}")
    
    # Check if multiple instances might be running
    instance_count = os.getenv("RENDER_INSTANCE_COUNT")
    if instance_count and int(instance_count) > 1:
        print(f"⚠ Multiple instances detected: {instance_count}")
        print("  Ensure Redis is configured for challenge persistence!")

def simulate_webauthn_flow():
    """Simulate the WebAuthn token flow."""
    print("\n=== Simulating WebAuthn Flow ===")
    
    secret = check_secret_key()
    if not secret:
        print("Cannot simulate without SECRET_KEY")
        return
    
    try:
        now = datetime.now(timezone.utc)
        exp = now + timedelta(minutes=15)
        
        # Step 1: Create pending_2fa token (like /token endpoint)
        print("\n1. Creating pending_2fa token...")
        payload = {"sub": "test@example.com", "scope": "pending_2fa", "exp": exp}
        token = jwt.encode(payload, secret, algorithm="HS256")
        print(f"   Token created at: {now.isoformat()}")
        print(f"   Token expires at: {exp.isoformat()}")
        
        # Step 2: Verify immediately (like /webauthn/authenticate/options)
        print("\n2. Verifying token immediately...")
        try:
            decoded = jwt.decode(token, secret, algorithms=["HS256"])
            if decoded.get("scope") != "pending_2fa":
                print("✗ Wrong scope!")
            else:
                print("✓ Token valid")
        except jwt.ExpiredSignatureError:
            print("✗ EXPIRED! Clock skew detected.")
        except Exception as e:
            print(f"✗ Validation error: {e}")
        
        # Step 3: Wait and verify again (simulating user interaction)
        import time
        print("\n3. Waiting 5 seconds (simulating user completing WebAuthn)...")
        time.sleep(5)
        
        print("4. Verifying token again...")
        try:
            decoded = jwt.decode(token, secret, algorithms=["HS256"])
            if decoded.get("scope") != "pending_2fa":
                print("✗ Wrong scope!")
            else:
                print("✓ Token still valid")
        except jwt.ExpiredSignatureError:
            print("✗ Token expired after 5 seconds! TTL too short or clock skew.")
        except Exception as e:
            print(f"✗ Validation error: {e}")
        
    except Exception as e:
        print(f"✗ Error simulating flow: {e}")

def main():
    print("=" * 60)
    print("WebAuthn Production Diagnostic Script")
    print("=" * 60)
    
    check_secret_key()
    check_clock_skew()
    check_redis()
    check_token_config()
    check_instance_info()
    simulate_webauthn_flow()
    
    print("\n" + "=" * 60)
    print("Diagnostic complete!")
    print("=" * 60)
    
    print("\nRecommendations:")
    print("1. If clock skew detected: Verify NTP is running and synced")
    print("2. If Redis fails: Check REDIS_URL and network connectivity")
    print("3. If multiple instances: Ensure Redis is used (not in-memory)")
    print("4. Check production logs for 'pending_2fa token expired' messages")

if __name__ == "__main__":
    main()
