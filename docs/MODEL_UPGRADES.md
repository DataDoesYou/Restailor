# Model Upgrade System

## Overview

The model upgrade system **automatically** migrates users from deprecated models to their replacements. No manual configuration required - it detects when models are removed from config and auto-upgrades users to valid replacements.

## How It Works

1. **Automatic Detection**: When a user's saved model is no longer in the config allowlist, the system automatically finds a replacement
2. **Smart Fallback**: Tries to upgrade to another model from the same provider first, then falls back to system defaults
3. **Database Preserved**: Original model IDs remain in the database; transformation happens during validation
4. **Universal Application**: Works for both trial users and users with purchased credits
5. **Zero Configuration**: Just update your config to add/remove models - upgrades happen automatically

## Upgrade Strategy

When a deprecated model is detected, the system follows this priority:

1. **Explicit Mapping** (optional): Check if you've defined a specific upgrade in `get_model_upgrade_map()`
2. **Same Provider Fallback**: Use the default model for the same provider (e.g., old OpenAI model → new OpenAI model)
3. **System Default**: Fall back to the system's default tailor model

## Optional: Custom Upgrade Paths

If you want to control exactly which model replaces a deprecated one, edit `restailor/settings_schemas.py`:

```python
def get_model_upgrade_map() -> dict[str, str]:
    """Define explicit upgrade mappings."""
    return {
        # Force specific upgrades
        "openai:gpt-4.1": "openai:gpt-5.1-instant",  # Use Instant instead of Thinking
        "gpt-4.1": "gpt-5.1-instant",                # Legacy format
    }
```

**But you don't need to do this!** The system will automatically use the default model from the same provider.


## Example Scenarios

### Scenario 1: Adding GPT-5.1, Removing GPT-4.1

**What You Do:**
1. Update `config/app.toml` to replace GPT-4.1 with GPT-5.1
2. Deploy

**What Happens Automatically:**
- Users with `last_single_tailor = "openai:gpt-4.1"` automatically get upgraded to `"openai:gpt-5.1-instant"` (the new default for OpenAI)
- User sees "GPT-5.1 Instant" selected in the sidebar
- Original database value remains untouched (backward compatible)

### Scenario 2: Multi-Model Mode Upgrade

**Before:**
- User has `tailor_models = ["openai:gpt-4.1", "anthropic:claude-4.1-opus"]`
- Config removes GPT-4.1, adds GPT-5.1

**After (Automatic):**
- User's settings show `tailor_models = ["openai:gpt-5.1-instant", "anthropic:claude-4.1-opus"]`
- Both models work correctly without user intervention

## Benefits

1. **Zero Manual Configuration**: Just update your config - upgrades happen automatically
2. **Works for All Users**: Trial users, paid users, and admins all get upgrades
3. **No Scripts to Run**: Deployment automatically handles everything
4. **Audit Trail**: Original selections remain in database
5. **Safe Fallbacks**: Always provides a valid model, never breaks user experience


## Testing

After updating your model config:

1. **Check API automatically upgrades**:
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
     https://your-api.com/users/me/model-settings
   ```
   Users with deprecated models will see the new model in the response

2. **Test sidebar auto-selection**:
   - Log in as a user who had an old model
   - Sidebar should show the new model automatically selected

3. **Verify job submission works**:
   - Submit a job and confirm it uses the new model
   - Check `charges` table for correct model

## Technical Details

### Where Upgrades Happen

- **Validation Time**: `ModelSettings.validate_against_allowlist()` checks each model and auto-upgrades deprecated ones
- **API Response**: Upgraded values are returned to the frontend
- **Database**: Original values preserved (non-destructive)

### Upgrade Priority

```python
def apply_model_upgrades(model_composite: str) -> str:
    # 1. Check if model is still valid → return as-is
    if model_id in allowed_models:
        return model_composite
    
    # 2. Try explicit upgrade mapping (optional)
    if model_composite in get_model_upgrade_map():
        return upgrade_map[model_composite]
    
    # 3. Try same-provider fallback
    if provider in config:
        return f"{provider}:{default_model_for_provider}"
    
    # 4. Use system default
    return system_default_composite
```

## Migration Notes

### From Manual Mapping to Automatic

If you had manual upgrade mappings, you can now remove them! The system will automatically use provider defaults:

```python
# OLD (manual, required editing this file)
def get_model_upgrade_map():
    return {
        "openai:gpt-4.1": "openai:gpt-5.1-instant",
    }

# NEW (automatic, no editing needed)
def get_model_upgrade_map():
    return {}  # Empty! Uses automatic provider fallback
```

Just update your `config/app.toml` and deploy - users get upgraded automatically.

## Future Enhancements

- UI notification when a user's selected model was auto-upgraded
- Admin dashboard showing model migration statistics
- Opt-in user preference to "lock" to a specific model (prevent auto-upgrades)

## Related Files

- `restailor/settings_schemas.py` - Upgrade mapping and logic
- `restailor/users_settings_api.py` - API endpoint that applies upgrades
- `frontend/components/resume/models.ts` - Frontend model definitions
