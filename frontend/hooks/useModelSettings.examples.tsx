/**
 * Example usage of useModelSettings hook.
 * 
 * This file demonstrates various patterns for using the hook in React components.
 * Not meant to be imported - just for documentation/reference.
 */

import { useModelSettings } from "./useModelSettings";

// ============================================================================
// Example 1: Basic Toggle
// ============================================================================

export function MultiModelToggle() {
  const { settings, save, isLoading, isSaving } = useModelSettings();

  if (isLoading) return <div>Loading settings...</div>;

  const handleToggle = async () => {
    if (!settings) return;
    
    try {
      await save({
        multi_model_enabled: !settings.multi_model_enabled,
      });
    } catch (error) {
      console.error("Failed to toggle multi-model:", error);
      alert("Failed to save settings. Please try again.");
    }
  };

  return (
    <button 
      onClick={handleToggle} 
      disabled={isSaving}
    >
      {isSaving ? "Saving..." : settings?.multi_model_enabled ? "Disable" : "Enable"} Multi-Model
    </button>
  );
}

// ============================================================================
// Example 2: Model Selection with Optimistic UI
// ============================================================================

export function ModelSelector() {
  const { settings, save, isLoading, isSaving, error } = useModelSettings();

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  const handleModelToggle = async (role: "fit" | "tailor" | "judge", modelId: string) => {
    if (!settings) return;

    const currentModels = settings[`${role}_models`] || [];
    const isSelected = currentModels.includes(modelId);

    const updatedModels = isSelected
      ? currentModels.filter((id) => id !== modelId)
      : [...currentModels, modelId];

    try {
      await save({
        [`${role}_models`]: updatedModels,
      });
    } catch (err) {
      console.error(`Failed to update ${role} models:`, err);
    }
  };

  return (
    <div>
      <h3>Tailor Models</h3>
      {["gpt-5", "claude-4.1-opus", "gemini-3-pro-preview"].map((modelId) => (
        <label key={modelId}>
          <input
            type="checkbox"
            checked={settings?.tailor_models.includes(modelId)}
            onChange={() => handleModelToggle("tailor", modelId)}
            disabled={isSaving}
          />
          {modelId}
        </label>
      ))}
    </div>
  );
}

// ============================================================================
// Example 3: Complete Settings Form with Conflict Handling
// ============================================================================

export function SettingsForm() {
  const { settings, save, isLoading, isSaving, error, refetch } = useModelSettings();

  if (isLoading) return <div>Loading settings...</div>;

  const handleSubmit = async (formData: FormData) => {
    try {
      await save({
        multi_model_enabled: formData.get("multi_model") === "true",
        fit_models: formData.getAll("fit_models") as string[],
        tailor_models: formData.getAll("tailor_models") as string[],
        judge_models: formData.getAll("judge_models") as string[],
      });
      
      alert("Settings saved successfully!");
    } catch (err: any) {
      if (err?.status === 409) {
        // Optimistic lock conflict - settings were modified elsewhere
        const retry = confirm(
          "Settings were modified by another session. Reload and try again?"
        );
        if (retry) {
          await refetch();
        }
      } else if (err?.status === 422) {
        // Validation error - invalid model IDs
        alert("Invalid model configuration. Please check your selections.");
      } else {
        alert("Failed to save settings. Please try again.");
      }
    }
  };

  return (
    <form onSubmit={(e) => { e.preventDefault(); handleSubmit(new FormData(e.currentTarget)); }}>
      {error && (
        <div style={{ color: "red" }}>
          Error: {error.message}
        </div>
      )}

      <label>
        <input
          type="checkbox"
          name="multi_model"
          value="true"
          defaultChecked={settings?.multi_model_enabled}
        />
        Enable Multi-Model Mode
      </label>

      {/* Model selection checkboxes... */}
      
      <button type="submit" disabled={isSaving}>
        {isSaving ? "Saving..." : "Save Settings"}
      </button>
      
      <button type="button" onClick={refetch}>
        Refresh
      </button>
    </form>
  );
}

// ============================================================================
// Example 4: Read-Only Display with Auto-Refresh
// ============================================================================

export function SettingsDisplay() {
  const { settings, isLoading, refetch } = useModelSettings();

  // Auto-refresh every 30 seconds (optional)
  // useEffect(() => {
  //   const interval = setInterval(refetch, 30_000);
  //   return () => clearInterval(interval);
  // }, [refetch]);

  if (isLoading) return <div>Loading...</div>;

  return (
    <div>
      <h2>Current Model Settings</h2>
      <dl>
        <dt>Multi-Model Enabled:</dt>
        <dd>{settings?.multi_model_enabled ? "Yes" : "No"}</dd>

        <dt>Fit Models:</dt>
        <dd>{settings?.fit_models.join(", ") || "None"}</dd>

        <dt>Tailor Models:</dt>
        <dd>{settings?.tailor_models.join(", ") || "None"}</dd>

        <dt>Judge Models:</dt>
        <dd>{settings?.judge_models.join(", ") || "None"}</dd>

        <dt>Last Updated:</dt>
        <dd>{settings?.updated_at ? new Date(settings.updated_at).toLocaleString() : "Never"}</dd>
      </dl>

      <button onClick={refetch}>Refresh</button>
    </div>
  );
}

// ============================================================================
// Example 5: Conditional Rendering Based on Settings
// ============================================================================

export function ConditionalFeature() {
  const { settings, isLoading } = useModelSettings();

  // Don't render until settings are loaded
  if (isLoading || !settings) return null;

  // Only show multi-model UI if enabled
  if (!settings.multi_model_enabled) {
    return <div>Multi-model mode is disabled</div>;
  }

  return (
    <div>
      <h3>Multi-Model Features</h3>
      <p>Using {settings.tailor_models.length} models for tailoring</p>
      {/* Multi-model specific UI... */}
    </div>
  );
}

// ============================================================================
// Example 6: Using with TypeScript for Type Safety
// ============================================================================

export function TypeSafeSettings() {
  const { settings, save } = useModelSettings();

  const updateSingleModel = async (role: "fit" | "tailor" | "judge", modelId: string | null) => {
    if (!settings) return;

    // TypeScript knows the shape of the settings object
    await save({
      [`last_single_${role}`]: modelId,
    });
  };

  return (
    <div>
      <select
        value={settings?.last_single_tailor || ""}
        onChange={(e) => updateSingleModel("tailor", e.target.value || null)}
      >
        <option value="">Select a model...</option>
        <option value="gpt-5">GPT-5</option>
        <option value="claude-4.1-opus">Claude 4.1 Opus</option>
        <option value="gemini-3-pro-preview">Gemini 3 Pro</option>
      </select>
    </div>
  );
}
