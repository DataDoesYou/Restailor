"use client";

import { useCallback } from "react";
import { useModelSettings } from "@/hooks/useModelSettings";
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
  type ModelRole,
} from "@/lib/modelSelectionAdapter";
import type { ModelSettings as ModelSettingsType } from "@/lib/apiClient";
import { MODEL_OPTIONS } from "@/components/resume/models";

// Use the actual MODEL_OPTIONS from the canonical source
const AVAILABLE_MODELS = MODEL_OPTIONS.map(m => ({
  id: m.model_id,
  name: m.alias,  // Just the alias, like sidebar
  tooltip: `${m.provider_display} (${m.description})`  // Tooltip with provider and description
}));

const ROLES: { key: ModelRole; label: string; description: string }[] = [
  { key: "fit", label: "Fit Analysis", description: "Models for analyzing resume-to-job fit" },
  { key: "tailor", label: "Resume Tailoring", description: "Models for tailoring resumes to job descriptions" },
  { key: "judge", label: "Quality Scoring", description: "Models for evaluating tailored resume quality" },
];

/**
 * Model Settings Component
 * 
 * Allows users to configure AI model preferences with two modes:
 * - Single-model mode: Select one model per role (radio buttons)
 * - Multi-model mode: Select multiple models per role (checkboxes)
 * 
 * All state changes are optimistically applied and synced to server.
 */
export default function ModelSettings() {
  const { settings, isLoading, isSaving, error, save, refetch } = useModelSettings();

  // Apply a transformation function to settings and save
  const apply = useCallback(
    async (fn: (s: ModelSettingsType) => ModelSettingsType) => {
      if (!settings) return;
      const newSettings = fn(settings);
      console.log('[ModelSettings] apply() - about to save:', newSettings);
      try {
        await save(newSettings);
        console.log('[ModelSettings] apply() - save succeeded');
      } catch (err) {
        // Error handling is done in the hook
        console.error("[ModelSettings] apply() - Failed to save settings:", err);
      }
    },
    [settings, save]
  );

  // Toggle multi-model mode
  const handleMultiModeToggle = useCallback(() => {
    if (!settings) return;
    apply(settings.multi_model_enabled ? leaveMulti : enterMulti);
  }, [settings, apply]);

  // Toggle checkbox (multi-model mode)
  const handleCheckboxToggle = useCallback(
    (role: ModelRole, modelId: string) => {
      apply((s) => toggleCheckbox(role, modelId, s));
    },
    [apply]
  );

  // Select radio (single-model mode)
  const handleRadioSelect = useCallback(
    (role: ModelRole, modelId: string) => {
      apply((s) => selectRadio(role, modelId, s));
    },
    [apply]
  );

  // Select all models for a role
  const handleSelectAll = useCallback(
    (role: ModelRole) => {
      const allModelIds = AVAILABLE_MODELS.map((m) => m.id);
      apply((s) => selectAll(role, allModelIds, s));
    },
    [apply]
  );

  // Clear all models for a role
  const handleClearAll = useCallback(
    (role: ModelRole) => {
      apply((s) => clearAll(role, s));
    },
    [apply]
  );

  if (isLoading) {
    return (
      <div className="rounded border border-slate-700 p-4">
        <div className="text-slate-400">Loading model settings...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded border border-red-700 p-4">
        <div className="text-red-400">Error: {String(error)}</div>
        <button
          onClick={refetch}
          className="mt-2 rounded bg-slate-700 px-3 py-2 text-sm"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!settings) {
    return null;
  }

  const isMultiMode = settings.multi_model_enabled;
  const disabled = isSaving;

  return (
    <div className="rounded border border-slate-700 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Model Selection Mode</h3>
          <p className="text-sm text-slate-400">
            {isMultiMode
              ? "Select multiple models per role for ensemble processing"
              : "Select one model per role"}
          </p>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <span className="text-sm font-medium">Multi-Model</span>
          <input
            type="checkbox"
            checked={isMultiMode}
            onChange={handleMultiModeToggle}
            disabled={disabled}
            className="h-4 w-4 accent-amber-500"
          />
        </label>
      </div>

      {isSaving && (
        <div className="text-sm text-blue-400" role="status" aria-live="polite">
          Saving changes...
        </div>
      )}

      <div className="space-y-6" aria-busy={disabled}>
        {ROLES.map((role) => {
          const selectedModels = effectiveSelected(role.key, settings);
          const selectedCount = getSelectedCount(role.key, settings);

          return (
            <div key={role.key} className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">{role.label}</h4>
                  <p className="text-xs text-slate-400">{role.description}</p>
                </div>
                {isMultiMode && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-400">
                      {selectedCount} / {AVAILABLE_MODELS.length}
                    </span>
                    <button
                      onClick={() => handleSelectAll(role.key)}
                      disabled={disabled || selectedCount === AVAILABLE_MODELS.length}
                      className="text-xs rounded bg-slate-700 px-2 py-1 disabled:opacity-50 hover:bg-slate-600"
                      aria-label={`Select all ${role.label} models`}
                    >
                      Select All
                    </button>
                    <button
                      onClick={() => handleClearAll(role.key)}
                      disabled={disabled || selectedCount === 0}
                      className="text-xs rounded bg-slate-700 px-2 py-1 disabled:opacity-50 hover:bg-slate-600"
                      aria-label={`Clear all ${role.label} models`}
                    >
                      Clear
                    </button>
                  </div>
                )}
              </div>

              <fieldset disabled={disabled} className="space-y-2 pl-2">
                {isMultiMode ? (
                  // Multi-model mode: checkboxes
                  <>
                    {AVAILABLE_MODELS.map((model) => {
                      const checked = isModelSelected(role.key, model.id, settings);
                      return (
                        <label
                          key={model.id}
                          className="flex items-start gap-2 min-h-6 cursor-pointer"
                          title={model.tooltip}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => handleCheckboxToggle(role.key, model.id)}
                            disabled={disabled}
                            className="h-4 w-4 mt-1 accent-amber-500"
                          />
                          <span className="text-base leading-6">{model.name}</span>
                        </label>
                      );
                    })}
                  </>
                ) : (
                  // Single-model mode: radio buttons
                  <>
                    {AVAILABLE_MODELS.map((model) => {
                      const checked = isModelSelected(role.key, model.id, settings);
                      return (
                        <label
                          key={model.id}
                          className="flex items-start gap-2 min-h-6 cursor-pointer"
                          title={model.tooltip}
                        >
                          <input
                            type="radio"
                            name={`${role.key}-model`}
                            checked={checked}
                            onChange={() => handleRadioSelect(role.key, model.id)}
                            disabled={disabled}
                            className="h-4 w-4 mt-1 accent-amber-500"
                          />
                          <span className="text-base leading-6">{model.name}</span>
                        </label>
                      );
                    })}
                  </>
                )}
              </fieldset>

              {selectedCount === 0 && (
                <p className="text-xs text-yellow-400 pl-2">
                  No models selected for {role.label.toLowerCase()}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
