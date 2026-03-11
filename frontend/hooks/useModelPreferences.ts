// DB-only Model Preferences State Management
// Replaces localStorage/cookie hybrid approach with pure database persistence

import { useState, useEffect } from "react";
import api, { ApiError } from "@/lib/api";
import { MODEL_OPTIONS } from "@/components/resume/models";

export interface ModelPreferences {
  multi_model_enabled: boolean;
  fit_models: string[];
  tailor_models: string[];
  judge_models: string[];
  last_single_fit: string | null;
  last_single_tailor: string | null;
  last_single_judge: string | null;
  updated_at?: string | null;
  version?: number;
}

// Helper to convert display alias to model_id for API
// Returns model_id if model found, otherwise returns alias as-is
function aliasToModelId(alias: string | null): string | null {
  if (!alias) return null;
  const model = MODEL_OPTIONS.find(m => m.alias === alias);
  return model ? model.model_id : alias; // fallback to alias if not found
}

// Helper to convert model_id to display alias for UI
function modelIdToAlias(modelId: string | null): string | null {
  if (!modelId) return null;
  const model = MODEL_OPTIONS.find(m => m.model_id === modelId);
  return model ? model.alias : modelId;
}

export interface UseModelPreferencesResult {
  preferences: ModelPreferences | null;
  loading: boolean;
  error: string | null;
  updatePreferences: (updates: Partial<ModelPreferences>) => Promise<void>;
  refreshPreferences: () => Promise<void>;
}

const DEFAULT_PREFERENCES: ModelPreferences = {
  multi_model_enabled: false,
  fit_models: [],
  tailor_models: [],
  judge_models: [],
  last_single_fit: null,
  last_single_tailor: null,
  last_single_judge: null,
};

/**
 * Hook to manage model preferences with database-only persistence.
 * Replaces the old localStorage + cookies + DB hybrid approach.
 * 
 * Usage:
 * ```tsx
 * const { preferences, loading, updatePreferences } = useModelPreferences();
 * 
 * // Update single model
 * await updatePreferences({ last_single_fit: "gpt-5" });
 * 
 * // Update multi-model
 * await updatePreferences({ 
 *   multi_model_enabled: true,
 *   fit_models: ["gpt-5", "claude-4.1-opus"]
 * });
 * ```
 */
export function useModelPreferences(): UseModelPreferencesResult {
  const [preferences, setPreferences] = useState<ModelPreferences | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Load preferences from DB on mount
  const loadPreferences = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await api.get<{ settings: ModelPreferences }>("/users/me/model-settings");
      const apiSettings = response.settings || DEFAULT_PREFERENCES;
      
      // Convert model IDs to aliases for UI
      const settingsWithAliases = {
        ...apiSettings,
        fit_models: apiSettings.fit_models.map(id => modelIdToAlias(id) || id),
        tailor_models: apiSettings.tailor_models.map(id => modelIdToAlias(id) || id),
        judge_models: apiSettings.judge_models.map(id => modelIdToAlias(id) || id),
        last_single_fit: modelIdToAlias(apiSettings.last_single_fit),
        last_single_tailor: modelIdToAlias(apiSettings.last_single_tailor),
        last_single_judge: modelIdToAlias(apiSettings.last_single_judge),
      };
      
      console.log("[useModelPreferences] Loaded from API:", apiSettings);
      console.log("[useModelPreferences] Converted to aliases:", settingsWithAliases);
      
      setPreferences(settingsWithAliases);
    } catch (e) {
      const err = e as ApiError;
      
      if (err.status === 401) {
        // Not logged in - use defaults
        setPreferences(DEFAULT_PREFERENCES);
      } else {
        let errorMessage = "Failed to load model preferences";
        
        if (err.status === 404) {
          errorMessage = "Preferences not found. API may have changed.";
        } else if (err.status === 500) {
          errorMessage = "Server error loading preferences. Please refresh.";
        } else if (err.status === 0 || !err.status) {
          errorMessage = "Network error loading preferences. Check your connection.";
        } else if (err.status) {
          errorMessage = `Failed to load model preferences (HTTP ${err.status})`;
        }
        
        console.error("[useModelPreferences] Failed to load preferences:", {
          status: err.status,
          detail: err.detail,
          message: err.message,
          error: err
        });
        
        setError(errorMessage);
        setPreferences(DEFAULT_PREFERENCES);
      }
    } finally {
      setLoading(false);
    }
  };

  // Load on mount
  useEffect(() => {
    loadPreferences();
  }, []);

  // Update preferences in DB
  const updatePreferences = async (updates: Partial<ModelPreferences>) => {
    if (!preferences) {
      console.warn("[useModelPreferences] Cannot update: preferences not loaded");
      return;
    }

    // Optimistic update (keep using aliases in local state)
    const previous = preferences;
    const updated = { ...preferences, ...updates };
    setPreferences(updated);

    try {
      // Convert aliases to model IDs for API
      const settingsForApi = {
        ...updated,
        fit_models: updated.fit_models.map(a => aliasToModelId(a) || a),
        tailor_models: updated.tailor_models.map(a => aliasToModelId(a) || a),
        judge_models: updated.judge_models.map(a => aliasToModelId(a) || a),
        last_single_fit: aliasToModelId(updated.last_single_fit),
        last_single_tailor: aliasToModelId(updated.last_single_tailor),
        last_single_judge: aliasToModelId(updated.last_single_judge),
      };

      console.log("[useModelPreferences] Sending to API:", settingsForApi);

      const response = await api.put<{ settings: ModelPreferences }>("/users/me/model-settings", {
        settings: settingsForApi,
        expectedUpdatedAt: preferences.updated_at,
      });
      
      console.log("[useModelPreferences] Received from API:", response.settings);
      
      // Convert model IDs back to aliases for UI
      const settingsWithAliases = {
        ...response.settings,
        fit_models: response.settings.fit_models.map(id => modelIdToAlias(id) || id),
        tailor_models: response.settings.tailor_models.map(id => modelIdToAlias(id) || id),
        judge_models: response.settings.judge_models.map(id => modelIdToAlias(id) || id),
        last_single_fit: modelIdToAlias(response.settings.last_single_fit),
        last_single_tailor: modelIdToAlias(response.settings.last_single_tailor),
        last_single_judge: modelIdToAlias(response.settings.last_single_judge),
      };
      
      console.log("[useModelPreferences] Converted back to aliases:", settingsWithAliases);
      
      // Update with server response (includes new timestamp)
      setPreferences(settingsWithAliases);
      setError(null);
    } catch (e) {
      const err = e as ApiError;
      // Revert optimistic update on error
      setPreferences(previous);
      
      let errorMessage = "Failed to save preferences";
      
      if (err.status === 401) {
        errorMessage = "Not authenticated. Please log in.";
      } else if (err.status === 409) {
        // Conflict - preferences were modified elsewhere
        errorMessage = "Preferences were modified elsewhere. Refreshing...";
        // Reload fresh data
        await loadPreferences();
      } else if (err.status === 400 || err.status === 422) {
        // Validation error (400 or 422) - extract detailed message
        if (typeof err.detail === "string") {
          errorMessage = err.detail;
        } else if (err.detail && typeof err.detail === "object") {
          // Try to extract useful info from detail object
          const detailStr = JSON.stringify(err.detail, null, 2);
          errorMessage = `Validation error: ${detailStr}`;
        } else {
          errorMessage = "Invalid model selection";
        }
      } else if (err.status === 404) {
        errorMessage = "API endpoint not found. Please refresh the page.";
      } else if (err.status === 500) {
        errorMessage = "Server error. Please try again or contact support.";
      } else if (err.status === 0 || !err.status) {
        errorMessage = "Network error. Check your connection and try again.";
      } else {
        errorMessage = `Failed to save preferences (HTTP ${err.status})`;
      }
      
      console.error("[useModelPreferences] Failed to save preferences:", {
        status: err.status,
        detail: err.detail,
        updates,
        error: err
      });
      
      setError(errorMessage);
      throw err; // Re-throw so caller can handle if needed
    }
  };

  return {
    preferences,
    loading,
    error,
    updatePreferences,
    refreshPreferences: loadPreferences,
  };
}
