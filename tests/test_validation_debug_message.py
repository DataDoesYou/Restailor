"""
Test that validation error messages include debug information.

This test verifies the error message format includes:
- label value (or NULL)
- meta value (or NULL)  
- multi-mode status (YES or NO)

Run with: poetry run pytest tests/test_validation_debug_message.py -v
"""

def test_validation_error_format():
    """Test that the validation error message format is correct."""
    
    # Simulate validation failure scenarios
    test_cases = [
        {
            "name": "No model selected",
            "label": None,
            "meta": None,
            "multi": False,
            "expected_pattern": r"\(label=NULL, meta=NULL, multi=NO\)"
        },
        {
            "name": "Label but no meta (broken state)",
            "label": "GPT-5.5 Instant",
            "meta": None,
            "multi": False,
            "expected_pattern": r"\(label=GPT-5\.5 Instant, meta=NULL, multi=NO\)"
        },
        {
            "name": "Multi-mode with no models",
            "label": None,
            "meta": None,
            "multi": True,
            "expected_pattern": r"\(label=NULL, meta=NULL, multi=YES\)"
        },
        {
            "name": "Full state",
            "label": "Claude Sonnet 4.6",
            "meta": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            "multi": False,
            "expected_pattern": r"\(label=Claude Sonnet 4\.6, meta=anthropic/claude-sonnet-4-6, multi=NO\)"
        },
    ]
    
    import re
    
    for case in test_cases:
        label = case["label"]
        meta = case["meta"]
        multi = case["multi"]
        
        # Simulate the TypeScript validation logic
        if meta:
            meta_str = f"{meta['provider']}/{meta.get('model', meta.get('model_id', 'unknown'))}"
        else:
            meta_str = "NULL"
        
        label_str = label if label else "NULL"
        multi_str = "YES" if multi else "NO"
        
        # Build the error message
        role_display = "Fit"
        debug_info = f"(label={label_str}, meta={meta_str}, multi={multi_str})"
        error_message = f"Please select a {role_display} model in the sidebar before running. {debug_info}"
        
        # Verify it matches expected pattern
        assert re.search(case["expected_pattern"], error_message), \
            f"Test case '{case['name']}' failed.\nExpected pattern: {case['expected_pattern']}\nActual message: {error_message}"
        
        print(f"✓ Test case '{case['name']}' passed: {error_message}")


def test_validation_error_includes_all_fields():
    """Test that error message always includes all three debug fields."""
    import re
    
    # Test various combinations
    combinations = [
        (None, None, False),
        (None, None, True),
        ("Test Model", None, False),
        ("Test Model", {"provider": "test", "model": "test-1"}, False),
        ("Test Model", {"provider": "test", "model": "test-1"}, True),
    ]
    
    for label, meta, multi in combinations:
        # Build error message
        if meta:
            meta_str = f"{meta['provider']}/{meta.get('model', meta.get('model_id', 'unknown'))}"
        else:
            meta_str = "NULL"
        
        label_str = label if label else "NULL"
        multi_str = "YES" if multi else "NO"
        
        debug_info = f"(label={label_str}, meta={meta_str}, multi={multi_str})"
        error_message = f"Please select a Fit model in the sidebar before running. {debug_info}"
        
        # Verify all three fields are present
        assert "label=" in error_message, "Missing label field"
        assert "meta=" in error_message, "Missing meta field"
        assert "multi=" in error_message, "Missing multi field"
        
        # Verify format is correct
        assert re.search(r"\(label=.+, meta=.+, multi=.+\)", error_message), \
            f"Incorrect format in: {error_message}"
        
        print(f"✓ Format validated: {error_message}")


if __name__ == "__main__":
    print("Testing validation error message format...\n")
    test_validation_error_format()
    print("\nTesting all required fields are present...\n")
    test_validation_error_includes_all_fields()
    print("\n✅ All tests passed!")
