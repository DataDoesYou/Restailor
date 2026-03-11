"""
Quick test script for the test checkbox API endpoints
Run this after logging in to verify the endpoints work correctly
"""

import requests
import sys

# Configuration
API_BASE = "http://localhost:8000"
# You'll need to provide a valid session cookie after logging in
SESSION_COOKIE: str | None = None  # Set this to your session cookie value

def test_checkbox_endpoints():
    """Test the checkbox GET and PUT endpoints"""
    
    if not SESSION_COOKIE:
        print("❌ ERROR: Please set SESSION_COOKIE in the script after logging in")
        print("   You can get this from browser DevTools > Application > Cookies")
        return False
    
    cookies = {"session": SESSION_COOKIE}
    
    print("🧪 Testing checkbox endpoints...\n")
    
    # Test GET endpoint
    print("1️⃣  Testing GET /test-checkbox")
    try:
        resp = requests.get(f"{API_BASE}/test-checkbox", cookies=cookies)
        resp.raise_for_status()
        data = resp.json()
        print(f"   ✅ GET successful: {data}")
        initial_state = data.get("is_checked", False)
    except requests.exceptions.RequestException as e:
        print(f"   ❌ GET failed: {e}")
        return False
    
    # Test PUT endpoint - toggle to opposite state
    new_state = not initial_state
    print(f"\n2️⃣  Testing PUT /test-checkbox (setting to {new_state})")
    try:
        resp = requests.put(
            f"{API_BASE}/test-checkbox",
            json={"is_checked": new_state},
            cookies=cookies
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"   ✅ PUT successful: {data}")
        
        if data.get("is_checked") != new_state:
            print(f"   ⚠️  Warning: Expected is_checked={new_state}, got {data.get('is_checked')}")
    except requests.exceptions.RequestException as e:
        print(f"   ❌ PUT failed: {e}")
        return False
    
    # Verify with another GET
    print(f"\n3️⃣  Verifying with GET /test-checkbox")
    try:
        resp = requests.get(f"{API_BASE}/test-checkbox", cookies=cookies)
        resp.raise_for_status()
        data = resp.json()
        print(f"   ✅ GET successful: {data}")
        
        if data.get("is_checked") != new_state:
            print(f"   ⚠️  Warning: State mismatch! Expected {new_state}, got {data.get('is_checked')}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"   ❌ GET failed: {e}")
        return False
    
    # Toggle back to original state
    print(f"\n4️⃣  Toggling back to original state ({initial_state})")
    try:
        resp = requests.put(
            f"{API_BASE}/test-checkbox",
            json={"is_checked": initial_state},
            cookies=cookies
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"   ✅ PUT successful: {data}")
    except requests.exceptions.RequestException as e:
        print(f"   ❌ PUT failed: {e}")
        return False
    
    print("\n" + "="*50)
    print("✨ All tests passed! The checkbox endpoints work correctly.")
    print("="*50)
    return True

if __name__ == "__main__":
    success = test_checkbox_endpoints()
    sys.exit(0 if success else 1)
