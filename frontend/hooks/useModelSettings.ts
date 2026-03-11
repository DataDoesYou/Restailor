/**
 * React hook for managing user model settings.
 * 
 * Database-only storage - no localStorage or cookie caching.
 * 
 * Features:
 * - Automatic fetching on mount
 * - Optimistic locking via expected_updated_at
 * - Error handling with retry support
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { getUserSettings, putUserSettings, type ModelSettings } from "@/lib/apiClient";
import { isRtDebug } from "@/lib/rtDebug";

interface UseModelSettingsResult {
  /** Current settings (loaded from database) */
  settings?: ModelSettings;
  /** True while initial fetch is in progress */
  isLoading: boolean;
  /** True while save mutation is in progress */
  isSaving: boolean;
  /** Error from fetch or save operation */
  error: Error | null;
  /** Save partial settings with optimistic locking */
  save: (partial: Partial<ModelSettings>) => Promise<ModelSettings>;
  /** Force refetch from server */
  refetch: () => Promise<void>;
}

/**
 * Hook for managing user model settings with database-only storage.
 * 
 * @returns {UseModelSettingsResult} Settings state and mutation functions
 * 
 * @example
 * ```tsx
 * function SettingsPanel() {
 *   const { settings, save, isLoading, isSaving, error } = useModelSettings();
 *   
 *   if (isLoading) return <div>Loading...</div>;
 *   if (error) return <div>Error: {error.message}</div>;
 *   
 *   const handleToggle = async () => {
 *     try {
 *       await save({
 *         multi_model_enabled: !settings?.multi_model_enabled
 *       });
 *     } catch (err) {
 *       console.error('Failed to save:', err);
 *     }
 *   };
 *   
 *   return (
 *     <button onClick={handleToggle} disabled={isSaving}>
 *       {settings?.multi_model_enabled ? 'Disable' : 'Enable'} Multi-Model
 *     </button>
 *   );
 * }
 * ```
 */
export function useModelSettings(): UseModelSettingsResult {
  const [settings, setSettings] = useState<ModelSettings | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Track if component is mounted to prevent state updates after unmount
  const isMountedRef = useRef(true);
  
  // Use ref to access latest settings without adding to dependency arrays
  const settingsRef = useRef<ModelSettings | undefined>(settings);
  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);
  
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  /**
   * Fetch settings from server (database-only, no caching).
   */
  const fetchSettings = useCallback(async () => {
    if (isRtDebug()) console.log('[useModelSettings] fetchSettings() called - loading settings from API...');
    try {
      setIsLoading(true);
      setError(null);

      const freshSettings = await getUserSettings();
      if (isRtDebug()) console.log('[useModelSettings] Successfully fetched settings:', freshSettings);
      
      // Always set settings, even if component is unmounting
      // React will handle ignoring the state update if needed
      setSettings(freshSettings);
    } catch (err) {
      if (!isMountedRef.current) return;
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      
      // Suppress auth errors on logged-out pages (expected pre-login)
      const isAuthError = (err: any) => 
        err?.status === 401 || 
        err?.status === 403 || 
        (err instanceof Error && err.message.includes('Auth not established'));
      
      if (!isAuthError(err)) {
        console.error('[useModelSettings] Failed to fetch model settings:', error);
      } else if (isRtDebug()) {
        console.log('[useModelSettings] Failed to fetch model settings: ApiError: Auth not established (suppressed pre-login fetch)');
      }
    } finally {
      // Always set isLoading to false, even if component unmounted
      // This prevents stuck loading state on remounts (e.g., React Strict Mode)
      setIsLoading(false);
    }
  }, []);

  /**
   * Force refetch from server (ignores cache).
   */
  const refetch = useCallback(async () => {
    await fetchSettings();
  }, [fetchSettings]);

  /**
   * Save partial settings with optimistic locking (database-only, no caching).
   * 
   * Automatically includes expected_updated_at from current settings
   * to prevent concurrent modification conflicts (409 errors).
   * 
   * If a 409 conflict occurs, automatically retries once with fresh data.
   */
  const save = useCallback(async (partial: Partial<ModelSettings>): Promise<ModelSettings> => {
    const currentSettings = settingsRef.current;
    if (!currentSettings) {
      console.error('[useModelSettings] save() called before settings loaded!');
      throw new Error("Cannot save before settings are loaded");
    }

    if (isRtDebug()) console.log('[useModelSettings] save() called', { partial, currentSettings });

    try {
      setIsSaving(true);
      setError(null);

      // Merge partial with current settings and include optimistic lock
      const payload = {
        ...currentSettings,
        ...partial,
        expected_updated_at: currentSettings.updated_at || undefined,
      };

      if (isRtDebug()) console.log('[useModelSettings] Calling API with payload:', payload);
      const updatedSettings = await putUserSettings(payload);
      if (isRtDebug()) console.log('[useModelSettings] API call succeeded, updated settings:', updatedSettings);

      if (!isMountedRef.current) return updatedSettings;

      // Update state with server response
      setSettings(updatedSettings);

      return updatedSettings;
    } catch (err: any) {
      console.error('[useModelSettings] Save failed with error:', err);
      
      // Handle 409 conflict - retry once with fresh data
      if (err?.status === 409) {
        if (isRtDebug()) console.log('[useModelSettings] Conflict detected, retrying with fresh data...');
        try {
          // Refetch current settings
          const freshSettings = await getUserSettings();
          if (isRtDebug()) console.log('[useModelSettings] Fetched fresh settings:', freshSettings);
          
          // Update our ref with fresh data
          settingsRef.current = freshSettings;
          
          // Retry save with fresh base
          const retryPayload = {
            ...freshSettings,
            ...partial,
            expected_updated_at: freshSettings.updated_at || undefined,
          };
          
          if (isRtDebug()) console.log('[useModelSettings] Retrying save with fresh payload:', retryPayload);
          const updatedSettings = await putUserSettings(retryPayload);
          if (isRtDebug()) console.log('[useModelSettings] Retry succeeded:', updatedSettings);
          
          if (!isMountedRef.current) return updatedSettings;
          
          setSettings(updatedSettings);
          return updatedSettings;
        } catch (retryErr) {
          console.error('[useModelSettings] Retry also failed:', retryErr);
          if (!isMountedRef.current) throw retryErr;
          const error = retryErr instanceof Error ? retryErr : new Error(String(retryErr));
          setError(error);
          throw error;
        }
      }
      
      if (!isMountedRef.current) throw err;
      const error = err instanceof Error ? err : new Error(String(err));
      setError(error);
      throw error;
    } finally {
      // Always clear isSaving flag, even if component unmounted
      // This prevents stuck "Saving..." state on remounts
      setIsSaving(false);
    }
  }, []); // Empty deps - uses ref to access latest settings

  // Initial fetch on mount (database-only, no caching)
  useEffect(() => {
    fetchSettings();
  }, []); // Only run on mount

  return {
    settings,
    isLoading,
    isSaving,
    error,
    save,
    refetch,
  };
}
