/**
 * Model Selection Adapter
 * 
 * Pure functions that map UI interactions to ModelSettings structure.
 * All functions are immutable (return new settings objects) to support
 * optimistic UI updates before saving to the server.
 * 
 * This adapter preserves existing UI logic while working with the new
 * ModelSettings backend structure.
 */

import type { ModelSettings } from "./apiClient";

export type ModelRole = "fit" | "tailor" | "judge";

/**
 * Enter multi-model mode.
 * 
 * Sets multi_model_enabled=true and seeds arrays from last_single_* values
 * if arrays are currently empty.
 * 
 * @param settings - Current settings
 * @returns New settings with multi-model enabled and arrays seeded
 * 
 * @example
 * ```ts
 * const settings = {
 *   multi_model_enabled: false,
 *   fit_models: [],
 *   last_single_fit: "gpt-5",
 *   // ...
 * };
 * const updated = enterMulti(settings);
 * // Result: multi_model_enabled=true, fit_models=["gpt-5"]
 * ```
 */
export function enterMulti(settings: ModelSettings): ModelSettings {
  return {
    ...settings,
    multi_model_enabled: true,
    // Seed arrays from last_single_* if empty
    fit_models: settings.fit_models.length > 0
      ? settings.fit_models
      : settings.last_single_fit
      ? [settings.last_single_fit]
      : [],
    tailor_models: settings.tailor_models.length > 0
      ? settings.tailor_models
      : settings.last_single_tailor
      ? [settings.last_single_tailor]
      : [],
    judge_models: settings.judge_models.length > 0
      ? settings.judge_models
      : settings.last_single_judge
      ? [settings.last_single_judge]
      : [],
  };
}

/**
 * Leave multi-model mode.
 * 
 * Sets multi_model_enabled=false and captures the first selected model
 * from each array into last_single_* fields (or keeps previous if array is empty).
 * 
 * @param settings - Current settings
 * @returns New settings with multi-model disabled and single selections preserved
 * 
 * @example
 * ```ts
 * const settings = {
 *   multi_model_enabled: true,
 *   fit_models: ["gpt-5", "claude-4.1-opus"],
 *   last_single_fit: null,
 *   // ...
 * };
 * const updated = leaveMulti(settings);
 * // Result: multi_model_enabled=false, last_single_fit="gpt-5"
 * ```
 */
export function leaveMulti(settings: ModelSettings): ModelSettings {
  return {
    ...settings,
    multi_model_enabled: false,
    // Capture first selected from each array, or keep previous single selection
    last_single_fit: settings.fit_models.length > 0
      ? settings.fit_models[0]
      : settings.last_single_fit,
    last_single_tailor: settings.tailor_models.length > 0
      ? settings.tailor_models[0]
      : settings.last_single_tailor,
    last_single_judge: settings.judge_models.length > 0
      ? settings.judge_models[0]
      : settings.last_single_judge,
  };
}

/**
 * Toggle a model checkbox in multi-model mode.
 * 
 * Adds the model if not present, removes if already selected.
 * Standard add/remove behavior for checkbox UIs.
 * 
 * @param role - The role (fit/tailor/judge)
 * @param modelId - The model ID to toggle
 * @param settings - Current settings
 * @returns New settings with model toggled in the role array
 * 
 * @example
 * ```ts
 * const settings = { ..., fit_models: ["gpt-5"], ... };
 * const updated = toggleCheckbox("fit", "claude-4.1-opus", settings);
 * // Result: fit_models = ["gpt-5", "claude-4.1-opus"]
 * 
 * const removed = toggleCheckbox("fit", "gpt-5", updated);
 * // Result: fit_models = ["claude-4.1-opus"]
 * ```
 */
export function toggleCheckbox(
  role: ModelRole,
  modelId: string,
  settings: ModelSettings
): ModelSettings {
  const arrayKey = `${role}_models` as "fit_models" | "tailor_models" | "judge_models";
  const currentArray = settings[arrayKey];
  const isSelected = currentArray.includes(modelId);

  return {
    ...settings,
    [arrayKey]: isSelected
      ? currentArray.filter((id) => id !== modelId) // Remove
      : [...currentArray, modelId], // Add
  };
}

/**
 * Select a model radio button in single-model mode.
 * 
 * Sets the last_single_* field for the specified role.
 * 
 * @param role - The role (fit/tailor/judge)
 * @param modelId - The model ID to select (or null to clear)
 * @param settings - Current settings
 * @returns New settings with single model selected
 * 
 * @example
 * ```ts
 * const settings = { ..., last_single_tailor: null, ... };
 * const updated = selectRadio("tailor", "gpt-5", settings);
 * // Result: last_single_tailor = "gpt-5"
 * ```
 */
export function selectRadio(
  role: ModelRole,
  modelId: string | null,
  settings: ModelSettings
): ModelSettings {
  const fieldKey = `last_single_${role}` as "last_single_fit" | "last_single_tailor" | "last_single_judge";

  return {
    ...settings,
    [fieldKey]: modelId,
  };
}

/**
 * Select all available models for a role (multi-model mode).
 * 
 * Replaces the role's array with all provided model IDs.
 * 
 * @param role - The role (fit/tailor/judge)
 * @param allModelIds - Array of all available model IDs
 * @param settings - Current settings
 * @returns New settings with all models selected
 * 
 * @example
 * ```ts
 * const settings = { ..., fit_models: ["gpt-5"], ... };
 * const updated = selectAll("fit", ["gpt-5", "claude-4.1-opus", "gemini-3.1-pro-preview"], settings);
 * // Result: fit_models = ["gpt-5", "claude-4.1-opus", "gemini-3.1-pro-preview"]
 * ```
 */
export function selectAll(
  role: ModelRole,
  allModelIds: string[],
  settings: ModelSettings
): ModelSettings {
  const arrayKey = `${role}_models` as "fit_models" | "tailor_models" | "judge_models";

  return {
    ...settings,
    [arrayKey]: [...allModelIds], // Clone array to maintain immutability
  };
}

/**
 * Clear all selected models for a role (multi-model mode).
 * 
 * Sets the role's array to empty.
 * 
 * @param role - The role (fit/tailor/judge)
 * @param settings - Current settings
 * @returns New settings with role array cleared
 * 
 * @example
 * ```ts
 * const settings = { ..., tailor_models: ["gpt-5", "claude-4.1-opus"], ... };
 * const updated = clearAll("tailor", settings);
 * // Result: tailor_models = []
 * ```
 */
export function clearAll(role: ModelRole, settings: ModelSettings): ModelSettings {
  const arrayKey = `${role}_models` as "fit_models" | "tailor_models" | "judge_models";

  return {
    ...settings,
    [arrayKey]: [],
  };
}

/**
 * Get the effectively selected models for a role.
 * 
 * Returns the appropriate selection based on multi_model_enabled:
 * - If multi-model enabled: returns the role's array
 * - If single-model: returns array with last_single_* (filtering out null)
 * 
 * This is the "source of truth" for what models are currently active for a role.
 * 
 * @param role - The role (fit/tailor/judge)
 * @param settings - Current settings
 * @returns Array of selected model IDs (may be empty)
 * 
 * @example
 * ```ts
 * // Multi-model mode
 * const settings = { multi_model_enabled: true, fit_models: ["gpt-5", "claude-4.1-opus"], ... };
 * effectiveSelected("fit", settings); // ["gpt-5", "claude-4.1-opus"]
 * 
 * // Single-model mode
 * const settings2 = { multi_model_enabled: false, last_single_tailor: "gpt-5", ... };
 * effectiveSelected("tailor", settings2); // ["gpt-5"]
 * 
 * // Single-model mode with no selection
 * const settings3 = { multi_model_enabled: false, last_single_judge: null, ... };
 * effectiveSelected("judge", settings3); // []
 * ```
 */
export function effectiveSelected(role: ModelRole, settings: ModelSettings): string[] {
  if (settings.multi_model_enabled) {
    // Multi-model mode: return the array
    const arrayKey = `${role}_models` as "fit_models" | "tailor_models" | "judge_models";
    return settings[arrayKey];
  } else {
    // Single-model mode: return last_single_* as array (filter null)
    const fieldKey = `last_single_${role}` as "last_single_fit" | "last_single_tailor" | "last_single_judge";
    const singleModel = settings[fieldKey];
    return singleModel ? [singleModel] : [];
  }
}

/**
 * Check if a specific model is currently selected for a role.
 * 
 * Convenience function that checks effectiveSelected() for the model ID.
 * 
 * @param role - The role (fit/tailor/judge)
 * @param modelId - The model ID to check
 * @param settings - Current settings
 * @returns True if the model is selected for this role
 * 
 * @example
 * ```ts
 * const settings = { multi_model_enabled: true, fit_models: ["gpt-5"], ... };
 * isModelSelected("fit", "gpt-5", settings); // true
 * isModelSelected("fit", "claude-4.1-opus", settings); // false
 * ```
 */
export function isModelSelected(
  role: ModelRole,
  modelId: string,
  settings: ModelSettings
): boolean {
  return effectiveSelected(role, settings).includes(modelId);
}

/**
 * Get count of selected models for a role.
 * 
 * @param role - The role (fit/tailor/judge)
 * @param settings - Current settings
 * @returns Number of selected models
 * 
 * @example
 * ```ts
 * const settings = { multi_model_enabled: true, fit_models: ["gpt-5", "claude-4.1-opus"], ... };
 * getSelectedCount("fit", settings); // 2
 * ```
 */
export function getSelectedCount(role: ModelRole, settings: ModelSettings): number {
  return effectiveSelected(role, settings).length;
}

/**
 * Check if any models are selected for a role.
 * 
 * @param role - The role (fit/tailor/judge)
 * @param settings - Current settings
 * @returns True if at least one model is selected
 * 
 * @example
 * ```ts
 * const settings = { multi_model_enabled: false, last_single_fit: null, ... };
 * hasSelection("fit", settings); // false
 * ```
 */
export function hasSelection(role: ModelRole, settings: ModelSettings): boolean {
  return getSelectedCount(role, settings) > 0;
}
