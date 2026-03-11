/**
 * Model Selection Adapter - Usage Examples
 * 
 * This file demonstrates how to use the adapter functions in UI components
 * to manage model selection state with optimistic updates.
 */

import { useState } from "react";
import type { ModelSettings } from "../lib/apiClient";
import {
  enterMulti,
  leaveMulti,
  toggleCheckbox,
  selectRadio,
  selectAll,
  clearAll,
  effectiveSelected,
  isModelSelected,
  getSelectedCount,
  hasSelection,
  type ModelRole,
} from "../lib/modelSelectionAdapter";

/**
 * Example 1: Multi-Model Toggle Switch
 * 
 * Shows how to handle the multi-model enable/disable toggle.
 */
export function MultiModelToggleExample({
  settings,
  onSave,
}: {
  settings: ModelSettings;
  onSave: (partial: Partial<ModelSettings>) => Promise<ModelSettings>;
}) {
  const [optimisticSettings, setOptimisticSettings] = useState(settings);

  const handleToggle = async () => {
    // Optimistically update UI
    const newSettings = settings.multi_model_enabled
      ? leaveMulti(optimisticSettings)
      : enterMulti(optimisticSettings);

    setOptimisticSettings(newSettings);

    try {
      // Save to server
      await onSave(newSettings);
    } catch (error) {
      // Revert on error
      setOptimisticSettings(settings);
      console.error("Failed to update multi-model setting:", error);
    }
  };

  return (
    <div>
      <label>
        <input
          type="checkbox"
          checked={optimisticSettings.multi_model_enabled}
          onChange={handleToggle}
        />
        Enable Multi-Model Mode
      </label>
      <p className="text-sm text-gray-600">
        {optimisticSettings.multi_model_enabled
          ? "Select multiple models per role"
          : "Select one model per role"}
      </p>
    </div>
  );
}

/**
 * Example 2: Model Checkboxes (Multi-Model Mode)
 * 
 * Shows how to render checkboxes for model selection when multi-model is enabled.
 */
export function ModelCheckboxesExample({
  role,
  availableModels,
  settings,
  onSave,
}: {
  role: ModelRole;
  availableModels: Array<{ id: string; name: string }>;
  settings: ModelSettings;
  onSave: (partial: Partial<ModelSettings>) => Promise<ModelSettings>;
}) {
  const [optimisticSettings, setOptimisticSettings] = useState(settings);

  const handleToggle = async (modelId: string) => {
    // Optimistically update UI
    const newSettings = toggleCheckbox(role, modelId, optimisticSettings);
    setOptimisticSettings(newSettings);

    try {
      await onSave(newSettings);
    } catch (error) {
      // Revert on error
      setOptimisticSettings(settings);
      console.error("Failed to toggle model:", error);
    }
  };

  if (!settings.multi_model_enabled) {
    return null; // Only show in multi-model mode
  }

  return (
    <div>
      <h3>Select {role} models:</h3>
      <div className="space-y-2">
        {availableModels.map((model) => (
          <label key={model.id} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={isModelSelected(role, model.id, optimisticSettings)}
              onChange={() => handleToggle(model.id)}
            />
            {model.name}
          </label>
        ))}
      </div>
      <p className="text-sm text-gray-600 mt-2">
        {getSelectedCount(role, optimisticSettings)} selected
      </p>
    </div>
  );
}

/**
 * Example 3: Model Radio Buttons (Single-Model Mode)
 * 
 * Shows how to render radio buttons for model selection when multi-model is disabled.
 */
export function ModelRadioButtonsExample({
  role,
  availableModels,
  settings,
  onSave,
}: {
  role: ModelRole;
  availableModels: Array<{ id: string; name: string }>;
  settings: ModelSettings;
  onSave: (partial: Partial<ModelSettings>) => Promise<ModelSettings>;
}) {
  const [optimisticSettings, setOptimisticSettings] = useState(settings);

  const handleSelect = async (modelId: string) => {
    // Optimistically update UI
    const newSettings = selectRadio(role, modelId, optimisticSettings);
    setOptimisticSettings(newSettings);

    try {
      await onSave(newSettings);
    } catch (error) {
      // Revert on error
      setOptimisticSettings(settings);
      console.error("Failed to select model:", error);
    }
  };

  if (settings.multi_model_enabled) {
    return null; // Only show in single-model mode
  }

  const selectedModels = effectiveSelected(role, optimisticSettings);
  const selectedModelId = selectedModels.length > 0 ? selectedModels[0] : null;

  return (
    <div>
      <h3>Select {role} model:</h3>
      <div className="space-y-2">
        {availableModels.map((model) => (
          <label key={model.id} className="flex items-center gap-2">
            <input
              type="radio"
              name={`${role}-model`}
              checked={selectedModelId === model.id}
              onChange={() => handleSelect(model.id)}
            />
            {model.name}
          </label>
        ))}
      </div>
    </div>
  );
}

/**
 * Example 4: Select All / Clear All Buttons
 * 
 * Shows how to implement bulk selection controls.
 */
export function BulkSelectionExample({
  role,
  availableModels,
  settings,
  onSave,
}: {
  role: ModelRole;
  availableModels: Array<{ id: string; name: string }>;
  settings: ModelSettings;
  onSave: (partial: Partial<ModelSettings>) => Promise<ModelSettings>;
}) {
  const [optimisticSettings, setOptimisticSettings] = useState(settings);
  const [isLoading, setIsLoading] = useState(false);

  const handleSelectAll = async () => {
    setIsLoading(true);
    const allModelIds = availableModels.map((m) => m.id);
    const newSettings = selectAll(role, allModelIds, optimisticSettings);
    setOptimisticSettings(newSettings);

    try {
      await onSave(newSettings);
    } catch (error) {
      setOptimisticSettings(settings);
      console.error("Failed to select all:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleClearAll = async () => {
    setIsLoading(true);
    const newSettings = clearAll(role, optimisticSettings);
    setOptimisticSettings(newSettings);

    try {
      await onSave(newSettings);
    } catch (error) {
      setOptimisticSettings(settings);
      console.error("Failed to clear all:", error);
    } finally {
      setIsLoading(false);
    }
  };

  if (!settings.multi_model_enabled) {
    return null; // Only show in multi-model mode
  }

  const count = getSelectedCount(role, optimisticSettings);
  const total = availableModels.length;

  return (
    <div className="flex gap-2">
      <button
        onClick={handleSelectAll}
        disabled={isLoading || count === total}
        className="px-3 py-1 text-sm bg-blue-500 text-white rounded disabled:opacity-50"
      >
        Select All
      </button>
      <button
        onClick={handleClearAll}
        disabled={isLoading || count === 0}
        className="px-3 py-1 text-sm bg-gray-500 text-white rounded disabled:opacity-50"
      >
        Clear All
      </button>
      <span className="text-sm text-gray-600 self-center">
        {count} / {total} selected
      </span>
    </div>
  );
}

/**
 * Example 5: Active Models Display
 * 
 * Shows how to display which models are currently active for a role.
 */
export function ActiveModelsDisplay({
  role,
  settings,
  modelNames,
}: {
  role: ModelRole;
  settings: ModelSettings;
  modelNames: Record<string, string>; // modelId -> display name
}) {
  const activeModels = effectiveSelected(role, settings);

  if (!hasSelection(role, settings)) {
    return <p className="text-gray-500 italic">No {role} model selected</p>;
  }

  return (
    <div>
      <h4 className="font-semibold">Active {role} models:</h4>
      <ul className="list-disc list-inside">
        {activeModels.map((modelId) => (
          <li key={modelId}>{modelNames[modelId] || modelId}</li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Example 6: Conditional Feature Gate
 * 
 * Shows how to conditionally enable UI features based on model selection.
 */
export function ConditionalFeatureExample({
  settings,
}: {
  settings: ModelSettings;
}) {
  const hasFitModels = hasSelection("fit", settings);
  const hasTailorModels = hasSelection("tailor", settings);
  const hasJudgeModels = hasSelection("judge", settings);

  const canRunPipeline = hasFitModels && hasTailorModels;

  return (
    <div>
      <button
        disabled={!canRunPipeline}
        className="px-4 py-2 bg-green-500 text-white rounded disabled:opacity-50"
      >
        Run Resume Tailoring Pipeline
      </button>
      {!canRunPipeline && (
        <p className="text-red-500 text-sm mt-2">
          Please select at least one model for both Fit and Tailor roles.
        </p>
      )}
      {hasJudgeModels && (
        <p className="text-blue-500 text-sm mt-2">
          ✓ Judge models selected - quality scoring enabled
        </p>
      )}
    </div>
  );
}

/**
 * Example 7: Complete Settings Form
 * 
 * Shows how to combine all adapter functions in a full settings UI.
 */
export function CompleteSettingsFormExample({
  availableModels,
  settings,
  onSave,
}: {
  availableModels: Array<{ id: string; name: string }>;
  settings: ModelSettings;
  onSave: (partial: Partial<ModelSettings>) => Promise<ModelSettings>;
}) {
  const [optimisticSettings, setOptimisticSettings] = useState(settings);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleModeToggle = async () => {
    const newSettings = optimisticSettings.multi_model_enabled
      ? leaveMulti(optimisticSettings)
      : enterMulti(optimisticSettings);

    setOptimisticSettings(newSettings);
    await saveSettings(newSettings);
  };

  const handleCheckboxToggle = async (role: ModelRole, modelId: string) => {
    const newSettings = toggleCheckbox(role, modelId, optimisticSettings);
    setOptimisticSettings(newSettings);
    await saveSettings(newSettings);
  };

  const handleRadioSelect = async (role: ModelRole, modelId: string) => {
    const newSettings = selectRadio(role, modelId, optimisticSettings);
    setOptimisticSettings(newSettings);
    await saveSettings(newSettings);
  };

  const saveSettings = async (newSettings: ModelSettings) => {
    setIsSaving(true);
    setError(null);

    try {
      const saved = await onSave(newSettings);
      setOptimisticSettings(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
      // Revert to server state
      setOptimisticSettings(settings);
    } finally {
      setIsSaving(false);
    }
  };

  const roles: ModelRole[] = ["fit", "tailor", "judge"];

  return (
    <div className="space-y-6">
      <div>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={optimisticSettings.multi_model_enabled}
            onChange={handleModeToggle}
            disabled={isSaving}
          />
          <span className="font-semibold">Enable Multi-Model Mode</span>
        </label>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-2 rounded">
          {error}
        </div>
      )}

      {roles.map((role) => (
        <div key={role} className="border rounded p-4">
          <h3 className="font-bold capitalize mb-3">{role} Models</h3>

          {optimisticSettings.multi_model_enabled ? (
            // Multi-model mode: checkboxes
            <div className="space-y-2">
              {availableModels.map((model) => (
                <label key={model.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={isModelSelected(role, model.id, optimisticSettings)}
                    onChange={() => handleCheckboxToggle(role, model.id)}
                    disabled={isSaving}
                  />
                  {model.name}
                </label>
              ))}
              <p className="text-sm text-gray-600 mt-2">
                {getSelectedCount(role, optimisticSettings)} selected
              </p>
            </div>
          ) : (
            // Single-model mode: radio buttons
            <div className="space-y-2">
              {availableModels.map((model) => (
                <label key={model.id} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name={`${role}-model`}
                    checked={isModelSelected(role, model.id, optimisticSettings)}
                    onChange={() => handleRadioSelect(role, model.id)}
                    disabled={isSaving}
                  />
                  {model.name}
                </label>
              ))}
            </div>
          )}
        </div>
      ))}

      {isSaving && (
        <div className="text-blue-600 text-sm">Saving changes...</div>
      )}
    </div>
  );
}

/**
 * Example 8: Using effectiveSelected for Backend Submission
 * 
 * Shows how to prepare data for API calls based on current selection.
 */
export function PrepareForSubmission({
  settings,
}: {
  settings: ModelSettings;
}) {
  // Get the active models for each role
  const activeFitModels = effectiveSelected("fit", settings);
  const activeTailorModels = effectiveSelected("tailor", settings);
  const activeJudgeModels = effectiveSelected("judge", settings);

  // Example: prepare API payload
  const pipelinePayload = {
    fit_models: activeFitModels, // Array of 1+ models
    tailor_models: activeTailorModels,
    judge_models: activeJudgeModels.length > 0 ? activeJudgeModels : null, // Optional
    enable_quality_scoring: activeJudgeModels.length > 0,
  };

  return (
    <pre className="bg-gray-100 p-4 rounded text-xs overflow-auto">
      {JSON.stringify(pipelinePayload, null, 2)}
    </pre>
  );
}
