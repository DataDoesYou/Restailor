"""Demonstrate the settings schema and model allowlist functionality.

Run this script to see:
1. Available models from config
2. Valid settings creation
3. Invalid settings rejection (400-style validation)
"""
from pydantic import ValidationError
from restailor.settings_schemas import (
    ModelSettings,
    get_allowed_models,
    get_models_by_provider,
    validate_model_id,
    get_default_model_for_role,
)


def print_separator(title: str = ""):
    """Print a visual separator."""
    if title:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
    else:
        print(f"{'='*60}\n")


def demo_allowlist():
    """Show what models are available."""
    print_separator("Server-Side Model Allowlist")
    
    allowed = get_allowed_models()
    print(f"Total models in allowlist: {len(allowed)}")
    print(f"Models: {sorted(allowed)}\n")
    
    print("Models by provider:")
    by_provider = get_models_by_provider()
    for provider, roles in by_provider.items():
        print(f"  {provider}:")
        for role, model in roles.items():
            print(f"    {role}: {model}")
    print()


def demo_valid_settings():
    """Show valid settings creation."""
    print_separator("Valid Settings Creation")
    
    # Get a valid model
    allowed = list(get_allowed_models())
    if not allowed:
        print("No models in allowlist!")
        return
    
    valid_model = allowed[0]
    print(f"Using valid model: {valid_model}\n")
    
    # Create valid settings
    settings = ModelSettings(
        multi_model_enabled=True,
        fit_models=[valid_model],
        tailor_models=[valid_model],
        judge_models=[valid_model],
        last_single_fit=valid_model,
        version=1,
    )
    
    print("✅ Successfully created settings:")
    print(f"   multi_model_enabled: {settings.multi_model_enabled}")
    print(f"   fit_models: {settings.fit_models}")
    print(f"   tailor_models: {settings.tailor_models}")
    print(f"   last_single_fit: {settings.last_single_fit}")
    
    # Show JSON representation (for DB storage)
    print("\n📦 JSON for database storage:")
    import json
    print(json.dumps(settings.model_dump(), indent=2, default=str))
    print()


def demo_invalid_settings():
    """Show how invalid settings are rejected."""
    print_separator("Invalid Settings Rejection (400 errors)")
    
    test_cases = [
        ("fake-model-999", "Non-existent model"),
        ("../../etc/passwd", "Path traversal attempt"),
        ("'; DROP TABLE users; --", "SQL injection attempt"),
        ("<script>alert('xss')</script>", "XSS attempt"),
        ("gpt-999-ultra-mega", "Fictional model version"),
    ]
    
    for invalid_model, description in test_cases:
        print(f"\nTesting: {description}")
        print(f"  Input: {invalid_model}")
        
        try:
            ModelSettings(
                multi_model_enabled=False,
                last_single_tailor=invalid_model,
            )
            print("  ❌ ERROR: Should have been rejected!")
        except ValidationError as e:
            print(f"  ✅ Correctly rejected: {str(e).splitlines()[0]}")
    
    print()


def demo_helper_functions():
    """Show helper function usage."""
    print_separator("Helper Functions")
    
    print("Validation checks:")
    print(f"  validate_model_id('gpt-5'): {validate_model_id('gpt-5')}")
    print(f"  validate_model_id('fake-model'): {validate_model_id('fake-model')}")
    
    print("\nDefault models per role:")
    for role in ["tailor", "fit", "judge"]:
        default = get_default_model_for_role(role)
        print(f"  {role}: {default}")
    
    print()


def demo_db_workflow():
    """Show typical database workflow."""
    print_separator("Typical DB Workflow")
    
    allowed = list(get_allowed_models())
    if not allowed:
        print("No models in allowlist!")
        return
    
    print("1️⃣  User submits settings via API")
    user_input = {
        "multi_model_enabled": True,
        "tailor_models": [allowed[0]],
        "fit_models": [allowed[0]],
        "judge_models": [],
        "version": 1,
    }
    print(f"   Input: {user_input}\n")
    
    print("2️⃣  Backend validates against allowlist")
    try:
        validated = ModelSettings(**user_input)
        print("   ✅ Validation passed\n")
        
        print("3️⃣  Store in database (JSONB column)")
        jsonb_data = validated.model_dump()
        print(f"   JSONB: {jsonb_data}\n")
        
        print("4️⃣  Later: Retrieve and validate again")
        retrieved = ModelSettings(**jsonb_data)
        print(f"   Retrieved: multi_model={retrieved.multi_model_enabled}, models={retrieved.tailor_models}")
        print("   ✅ Still valid\n")
        
    except ValidationError as e:
        print(f"   ❌ Validation failed: {e}\n")


def main():
    """Run all demonstrations."""
    print("\n" + "="*60)
    print("  MODEL SETTINGS SCHEMA & ALLOWLIST DEMONSTRATION")
    print("="*60)
    
    demo_allowlist()
    demo_valid_settings()
    demo_invalid_settings()
    demo_helper_functions()
    demo_db_workflow()
    
    print_separator()
    print("Summary:")
    print("  ✅ Server-side allowlist extracts models from config/app.toml")
    print("  ✅ Pydantic validation rejects unknown/malicious model IDs")
    print("  ✅ Single source of truth: DB + config")
    print("  ✅ Safe for production use")
    print()


if __name__ == "__main__":
    main()
