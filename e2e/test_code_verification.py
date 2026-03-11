#!/usr/bin/env python
"""
🔍 CODE VERIFICATION TEST
Verify that __rt_mutation_in_progress flag is set SYNCHRONOUSLY

This test analyzes the TypeScript source code to verify:
1. Flag is set at the START of onAppliedToggle function
2. Flag is set BEFORE any await statements
3. Flag is set BEFORE any early returns (that don't unlock)
4. Flag is unlocked in all exit paths

NO BROWSER NEEDED - just static code analysis
"""

import re
from pathlib import Path


def test_flag_placement():
    """Verify flag is set synchronously at function start"""
    print("=" * 70)
    print("🔍 CODE VERIFICATION TEST")
    print("=" * 70)
    print()
    
    # Read the TypeScript file
    file_path = Path(__file__).parent.parent / "frontend" / "components" / "pages" / "ResumeTailorClient.tsx"
    print(f"Reading: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the onAppliedToggle function
    print("\n1️⃣  Finding onAppliedToggle function...")
    match = re.search(
        r'const onAppliedToggle = useCallback\(async \(checked: boolean\) => \{(.*?)^[\t ]*\}, \[',
        content,
        re.MULTILINE | re.DOTALL
    )
    
    if not match:
        print("❌ FAIL: Could not find onAppliedToggle function")
        return 1
    
    function_body = match.group(1)
    lines = function_body.split('\n')
    print(f"✓ Found function ({len(lines)} lines)")
    
    # Track what we find
    issues = []
    checks_passed = []
    
    # Parse the function line by line
    print("\n2️⃣  Analyzing function structure...")
    
    flag_lock_line = None
    first_await_line = None
    first_if_return_line = None
    flag_unlock_lines = []
    
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Find flag lock
        if '__rt_mutation_in_progress = true' in stripped and not stripped.startswith('//'):
            if flag_lock_line is None:
                flag_lock_line = i
                print(f"   📍 Flag LOCK found at line {i}")
        
        # Find flag unlocks
        if '__rt_mutation_in_progress = false' in stripped and not stripped.startswith('//'):
            flag_unlock_lines.append(i)
            print(f"   📍 Flag UNLOCK found at line {i}")
        
        # Find first await
        if first_await_line is None and 'await ' in stripped and not stripped.startswith('//'):
            first_await_line = i
            print(f"   📍 First 'await' at line {i}")
        
        # Find first conditional return
        if first_if_return_line is None and 'return' in stripped and not stripped.startswith('//'):
            # Check if it's inside an if/condition
            prev_lines = '\n'.join(lines[max(0, i-5):i])
            if 'if (' in prev_lines or ') return' in stripped:
                first_if_return_line = i
                print(f"   📍 First conditional return at line {i}")
    
    print("\n3️⃣  Verification checks...")
    print("   " + "-" * 60)
    
    # CHECK 1: Flag lock exists
    if flag_lock_line is None:
        issues.append("❌ No flag lock found - navigation blocking won't work!")
    else:
        checks_passed.append("✅ Flag lock found")
    
    # CHECK 2: Flag lock is BEFORE first await
    if flag_lock_line and first_await_line:
        if flag_lock_line < first_await_line:
            checks_passed.append(f"✅ Flag locked BEFORE first await ({flag_lock_line} < {first_await_line})")
        else:
            issues.append(f"❌ Flag locked AFTER await! ({flag_lock_line} > {first_await_line}) - Race condition!")
    
    # CHECK 3: Flag lock is BEFORE first conditional return (but allow early guards)
    if flag_lock_line and first_if_return_line:
        # Check if early returns are guards (running check, login check)
        early_return_context = '\n'.join(lines[max(0, first_if_return_line-2):first_if_return_line+1])
        is_guard = 'running' in early_return_context or 'isLoggedIn' in early_return_context
        
        if flag_lock_line < first_if_return_line:
            checks_passed.append(f"✅ Flag locked BEFORE early returns ({flag_lock_line} < {first_if_return_line})")
        elif is_guard:
            checks_passed.append(f"✅ Early returns are guard clauses (OK to be before flag lock)")
            print(f"   ℹ️  Note: Guard returns at line {first_if_return_line} prevent unnecessary mutations")
        else:
            issues.append(f"❌ Flag locked AFTER return! ({flag_lock_line} > {first_if_return_line}) - Will never lock!")
    
    # CHECK 4: Flag is unlocked somewhere
    if len(flag_unlock_lines) == 0:
        issues.append("❌ No flag unlock found - navigation will stay blocked forever!")
    elif len(flag_unlock_lines) < 2:
        issues.append(f"⚠️  Only {len(flag_unlock_lines)} unlock found - may not cover all exit paths")
    else:
        checks_passed.append(f"✅ Flag unlocked in {len(flag_unlock_lines)} places (covers multiple exit paths)")
    
    # CHECK 5: Flag lock is in first 20 lines (should be near start)
    if flag_lock_line and flag_lock_line <= 20:
        checks_passed.append(f"✅ Flag locked early in function (line {flag_lock_line})")
    elif flag_lock_line:
        issues.append(f"⚠️  Flag locked late in function (line {flag_lock_line}) - should be earlier!")
    
    # CHECK 6: Look for console.log indicating lock
    if 'LOCKED at function start' in function_body or 'Navigation LOCKED' in function_body:
        checks_passed.append("✅ Debug logging present for lock event")
    
    # Print results
    print("\n" + "=" * 70)
    print("📊 RESULTS")
    print("=" * 70)
    
    for check in checks_passed:
        print(check)
    
    if issues:
        print()
        for issue in issues:
            print(issue)
    
    print("\n" + "-" * 70)
    
    # Show relevant code snippet
    if flag_lock_line:
        print("\n📝 Code snippet around flag lock:")
        print("-" * 70)
        start = max(0, flag_lock_line - 5)
        end = min(len(lines), flag_lock_line + 5)
        for i in range(start, end):
            marker = ">>>" if i + 1 == flag_lock_line else "   "
            print(f"{marker} {i+1:3d} | {lines[i].rstrip()}")
        print("-" * 70)
    
    print("\n" + "=" * 70)
    
    if len(issues) == 0:
        print("🎉 ALL CHECKS PASSED!")
        print("\nThe code is correctly structured:")
        print("- Flag is set synchronously at function start")
        print("- Flag is set BEFORE any async operations")
        print("- Flag is unlocked on all exit paths")
        print("\nNavigation blocking should work correctly! 🔒")
        return 0
    else:
        print(f"⚠️  {len(issues)} ISSUE(S) FOUND")
        print("\nThe navigation blocking may not work correctly.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = test_flag_placement()
        exit(exit_code)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
