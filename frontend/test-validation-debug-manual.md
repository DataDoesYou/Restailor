# Manual Test: Validation Error Debug Info

## Purpose
Verify that validation error messages include debug information showing:
- `label=` (the display label selected)
- `meta=` (the provider/model from registry)
- `multi=` (whether multi-mode is active)

## Prerequisites
- Dev server running on `http://localhost:3000`
- Backend running with database access

## Test Steps

### Test 1: No Model Selected
1. Navigate to `http://localhost:3000/resume`
2. Paste any text into the resume textarea
3. Paste any text into the JD textarea
4. **Do NOT select any model in the sidebar**
5. Click the "Check Fit" button

**Expected Result:**
Error message appears containing:
```
Please select a Fit model in the sidebar before running. (label=NULL, meta=NULL, multi=NO)
```

### Test 2: Model Selected (Happy Path)
1. Navigate to `http://localhost:3000/resume`
2. Open the sidebar
3. Select a Fit model (e.g., "GPT-5.4 Mini")
4. Paste text into resume and JD textareas
5. Click the "Check Fit" button

**Expected Result:**
- No validation error (request should proceed)
- OR if error appears, it should show the actual label and meta values:
  ```
  (label=GPT-5.4 Mini, meta=openai/gpt-5.4-mini, multi=NO)
  ```

### Test 3: Multi-Mode Active
1. Navigate to `http://localhost:3000/resume`
2. Open the sidebar
3. Enable multi-mode (select multiple Fit models)
4. Paste text into textareas
5. Click "Check Fit"

**Expected Result:**
- Should work if models are selected
- If validation fails, error should show:
  ```
  (label=NULL, meta=NULL, multi=YES)
  ```
  or similar with actual values

### Test 4: Partial State (Edge Case)
1. Open browser DevTools console
2. Navigate to `http://localhost:3000/resume`
3. In console, run: `window.dispatchEvent(new CustomEvent('rt-sidebar', { detail: { fitModelLabel: 'Invalid Model' } }))`
4. Paste text into textareas
5. Click "Check Fit"

**Expected Result:**
Error message shows:
```
Please select a Fit model in the sidebar before running. (label=Invalid Model, meta=NULL, multi=NO)
```

This proves the debug info correctly identifies when we have a label but no matching meta (broken state).

## Success Criteria
✅ All error messages include the `(label=..., meta=..., multi=...)` format
✅ Values accurately reflect the actual state
✅ "NULL" appears when values are missing
✅ "YES"/"NO" appears for multi-mode status

## Notes
- The debug info helps diagnose why validation fails
- Users can see immediately if their model selection didn't register
- No need to open DevTools to understand the issue
