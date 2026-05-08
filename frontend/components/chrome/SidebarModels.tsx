"use client";
import { useEffect, useState, useRef } from "react";
import api, { ApiError } from "@/lib/api";
import { MODEL_OPTIONS } from "@/components/resume/models";
import { isRtDebug } from "@/lib/rtDebug";

interface Props {
  showJudge?: boolean;
  running?: boolean;
  trialModels?: string[] | null | undefined; // undefined = not loaded yet, null = loaded but no restrictions, array = restrictions
  isAuthenticated?: boolean; // Pass auth state from parent to avoid race conditions
}

export const SidebarModels: React.FC<Props> = ({
  showJudge = true,
  running = false,
  trialModels = undefined,
  isAuthenticated = undefined
}) => {
  // Multi-model mode toggle
  const [multiModelEnabled, setMultiModelEnabled] = useState(false);
  
  // Single source of truth: always use model_ids
  // Single-model: one model_id per phase
  const [fitModelId, setFitModelId] = useState<string | null>(null);
  const [tailorModelId, setTailorModelId] = useState<string | null>(null);
  const [judgeModelId, setJudgeModelId] = useState<string | null>(null);
  
  // Multi-model: arrays of model_ids per phase
  const [fitModels, setFitModels] = useState<string[]>([]);
  const [tailorModels, setTailorModels] = useState<string[]>([]);
  const [judgeModels, setJudgeModels] = useState<string[]>([]);
  
  const [loading, setLoading] = useState(isAuthenticated !== false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  
  // Save queue to prevent concurrent modifications (409 conflicts)
  const saveQueueRef = useRef<Promise<any>>(Promise.resolve());

  // Helper to check if a model is available (not restricted by trial)
  const isModelAvailable = (modelId: string): boolean => {
    // If trialModels is undefined, we haven't loaded trial data yet - allow all models to show
    // This prevents radio buttons from disappearing on refresh
    if (trialModels === undefined) return true;
    // If trialModels is null or empty array, all models are available
    if (!trialModels || trialModels.length === 0) return true;
    // Otherwise, check if this model is in the trial list
    if (trialModels.includes(modelId)) return true;

    // Check legacy IDs (if backend returns old ID but frontend uses new ID)
    const model = MODEL_OPTIONS.find(m => m.model_id === modelId);
    if (model?.legacy_model_ids) {
      return model.legacy_model_ids.some(legacyId => trialModels.includes(legacyId));
    }

    return false;
  };

  // Load when authenticated
  useEffect(() => {
    // If parent hasn't determined auth yet, wait
    if (isAuthenticated === undefined) {
      setLoading(true);
      return;
    }
    
    if (!isAuthenticated) {
      setLoading(false);
      return;
    }
    
    // User is authenticated - load settings
    let mounted = true;
    
    const load = async (retryCount = 0) => {
      try {
        const resp = await api.get<any>("/users/me/model-settings");
        
        if (!mounted) return;
        
        const settings = resp.settings || resp;
        
        // Helper to migrate legacy IDs to current IDs
        const migrateId = (id: string | null): string | null => {
          if (!id) return null;
          // Check if ID is current
          if (MODEL_OPTIONS.some(m => m.model_id === id)) return id;
          // Check if ID is legacy
          const newModel = MODEL_OPTIONS.find(m => m.legacy_model_ids?.includes(id));
          return newModel ? newModel.model_id : id;
        };

        const migrateIds = (ids: string[]): string[] => {
          if (!ids) return [];
          return ids.map(id => migrateId(id)).filter((id): id is string => id !== null);
        };
        
        // Load state directly from DB - batch update all state first
        const updates = {
          multiModelEnabled: settings.multi_model_enabled || false,
          fitModelId: migrateId(settings.last_single_fit),
          tailorModelId: migrateId(settings.last_single_tailor),
          judgeModelId: migrateId(settings.last_single_judge),
          fitModels: migrateIds(settings.fit_models || []),
          tailorModels: migrateIds(settings.tailor_models || []),
          judgeModels: migrateIds(settings.judge_models || []),
          updatedAt: settings.updated_at
        };
        
        setMultiModelEnabled(updates.multiModelEnabled);
        setFitModelId(updates.fitModelId);
        setTailorModelId(updates.tailorModelId);
        setJudgeModelId(updates.judgeModelId);
        setFitModels(updates.fitModels);
        setTailorModels(updates.tailorModels);
        setJudgeModels(updates.judgeModels);
        setUpdatedAt(updates.updatedAt);
        
        // ONLY set loading=false after all state is updated
        // Use setTimeout to ensure state updates have been processed
        setTimeout(() => {
          if (mounted) setLoading(false);
        }, 0);
      } catch (e) {
        if (!mounted) return;

        const errorMessage = e instanceof Error ? e.message : String(e);
        const isExpectedAuthError =
          (e instanceof ApiError && (e.status === 401 || e.status === 403)) ||
          errorMessage.includes("Auth not established") ||
          errorMessage === "Could not validate credentials";
        
        // Retry with exponential backoff if auth not established yet (up to 3 retries)
        if (errorMessage.includes("Auth not established") && retryCount < 3) {
          const delay = Math.min(100 * Math.pow(2, retryCount), 800); // 100ms, 200ms, 400ms, max 800ms
          // Suppress logging on first retry (expected during React StrictMode)
          if (retryCount > 0) {
            console.log(`[SidebarModels] Retrying in ${delay}ms (attempt ${retryCount + 1}/3)...`);
          }
          setTimeout(() => {
            if (mounted) load(retryCount + 1);
          }, delay);
          return; // Don't set loading=false yet
        }

        // Suppress pre-login auth errors silently (expected during initial load)
        if (!isExpectedAuthError) {
          console.error('[SidebarModels] ❌ Fetch failed:', e);
          console.error("[SidebarModels] Load error:", e);
        }
        
        // On error, stop loading
        if (mounted) {
          setLoading(false);
        }
      }
    };
    
    load();
    
    return () => {
      mounted = false;
    };
  }, [isAuthenticated]);

  // Sync selections to window object for ResumeTailorClient
  useEffect(() => {
    if (typeof window === 'undefined') return;
    
    const w = window as any;
    
    // Helper: convert model_ids to aliases (page expects aliases)
    const toAliases = (ids: string[]) => ids.map(id => 
      MODEL_OPTIONS.find(m => m.model_id === id)?.alias || id
    ).filter(Boolean);
    
    // Simple rule: if multi-mode is enabled, set the multi flags
    if (multiModelEnabled) {
      w.__rt_fit_multi = { enabled: true, models: toAliases(fitModels) };
      w.__rt_tailor_multi = { enabled: true, models: toAliases(tailorModels) };
      w.__rt_judge_multi = { enabled: true, models: toAliases(judgeModels) };
    } else {
      // Single-mode: clear multi flags
      try { delete w.__rt_fit_multi; } catch {}
      try { delete w.__rt_tailor_multi; } catch {}
      try { delete w.__rt_judge_multi; } catch {}
    }
    
    // Dispatch event with all current state
    const fitAlias = fitModelId ? MODEL_OPTIONS.find(m => m.model_id === fitModelId)?.alias || "" : "";
    const tailorAlias = tailorModelId ? MODEL_OPTIONS.find(m => m.model_id === tailorModelId)?.alias || "" : "";
    const judgeAlias = judgeModelId ? MODEL_OPTIONS.find(m => m.model_id === judgeModelId)?.alias || "" : "";
    
    try {
      const eventDetail = {
        multiMode: multiModelEnabled,
        multiFit: toAliases(fitModels),
        multiTailor: toAliases(tailorModels),
        multiJudge: toAliases(judgeModels),
        singleFit: fitAlias,
        singleTailor: tailorAlias,
        singleJudge: judgeAlias
      };
      
      window.dispatchEvent(new CustomEvent('rt-multi-models', { detail: eventDetail }));
      
      // Also dispatch legacy rt-sidebar event for backwards compatibility
      // Convert aliases back to full label format
      const fitOpt = MODEL_OPTIONS.find(m => m.model_id === fitModelId);
      const tailorOpt = MODEL_OPTIONS.find(m => m.model_id === tailorModelId);
      const judgeOpt = MODEL_OPTIONS.find(m => m.model_id === judgeModelId);
      
      const fitModelLabel = fitOpt ? `${fitOpt.alias} — ${fitOpt.provider_display} (${fitOpt.description})` : "";
      const tailorModelLabel = tailorOpt ? `${tailorOpt.alias} — ${tailorOpt.provider_display} (${tailorOpt.description})` : "";
      const judgeLabelStr = judgeOpt ? `${judgeOpt.alias} — ${judgeOpt.provider_display}` : "";
      
      window.dispatchEvent(new CustomEvent('rt-sidebar', { 
        detail: { fitModelLabel, tailorModelLabel, judgeLabel: judgeLabelStr }
      }));
    } catch {}
  }, [multiModelEnabled, fitModels, tailorModels, judgeModels, fitModelId, tailorModelId, judgeModelId]);

  // Listen for state requests from other components (e.g., ResumeTailorClient on mount)
  useEffect(() => {
    const onRequest = () => {
      // Respond with current state
      const fitOpt = MODEL_OPTIONS.find(m => m.model_id === fitModelId);
      const tailorOpt = MODEL_OPTIONS.find(m => m.model_id === tailorModelId);
      const judgeOpt = MODEL_OPTIONS.find(m => m.model_id === judgeModelId);
      
      const fitModelLabel = fitOpt ? `${fitOpt.alias} — ${fitOpt.provider_display} (${fitOpt.description})` : "";
      const tailorModelLabel = tailorOpt ? `${tailorOpt.alias} — ${tailorOpt.provider_display} (${tailorOpt.description})` : "";
      const judgeLabelStr = judgeOpt ? `${judgeOpt.alias} — ${judgeOpt.provider_display}` : "";
      
      window.dispatchEvent(new CustomEvent('rt-sidebar', { 
        detail: { fitModelLabel, tailorModelLabel, judgeLabel: judgeLabelStr }
      }));
    };
    window.addEventListener('rt-sidebar-request', onRequest);
    return () => window.removeEventListener('rt-sidebar-request', onRequest);
  }, [fitModelId, tailorModelId, judgeModelId]);

  // Queue save operations to prevent concurrent modifications and 409 conflicts
  // Uses optimistic UI updates - no loading states, just queue saves in background
  const queueSave = async (saveFn: () => Promise<any>) => {
    // Wait for previous save to complete
    await saveQueueRef.current.catch(() => {}); // Ignore previous errors
    
    // Execute this save in background (no loading state)
    const savePromise = (async () => {
      if ((!isAuthenticated) || loading) return;
      
      try {
        const resp = await saveFn();
        // Update state from server response (handles auto-upgrades, etc.)
        if (resp?.settings) {
          const settings = resp.settings;
          
          if (isRtDebug()) {
            console.log('[SidebarModels] 📥 Received server response, updating state:', {
              last_single_fit: settings.last_single_fit,
              last_single_tailor: settings.last_single_tailor,
              last_single_judge: settings.last_single_judge,
              currentFitModelId: fitModelId,
              willSetFitModelId: settings.last_single_fit || null
            });
          }
          
          setUpdatedAt(settings.updated_at);
          setMultiModelEnabled(settings.multi_model_enabled || false);
          setFitModelId(settings.last_single_fit || null);
          setTailorModelId(settings.last_single_tailor || null);
          setJudgeModelId(settings.last_single_judge || null);
          setFitModels(settings.fit_models || []);
          setTailorModels(settings.tailor_models || []);
          setJudgeModels(settings.judge_models || []);
        }
        return resp;
      } catch (e: any) {
        console.error("Save failed:", e);
        
        // On 409 conflict, refetch fresh data and retry once
        if (e?.status === 409) {
          if (isRtDebug()) console.log('[SidebarModels] 409 conflict, refetching and retrying...');
          try {
            const fresh = await api.get<any>("/users/me/model-settings");
            const freshSettings = fresh.settings || fresh;
            
            // Update state from fresh data
            setUpdatedAt(freshSettings.updated_at);
            setMultiModelEnabled(freshSettings.multi_model_enabled || false);
            setFitModelId(freshSettings.last_single_fit || null);
            setTailorModelId(freshSettings.last_single_tailor || null);
            setJudgeModelId(freshSettings.last_single_judge || null);
            setFitModels(freshSettings.fit_models || []);
            setTailorModels(freshSettings.tailor_models || []);
            setJudgeModels(freshSettings.judge_models || []);
            
            if (isRtDebug()) console.log('[SidebarModels] Refetched, retrying save with fresh timestamp:', freshSettings.updated_at);
            
            // Retry the save with fresh timestamp
            const retryResp = await saveFn();
            if (retryResp?.settings) {
              const retrySettings = retryResp.settings;
              setUpdatedAt(retrySettings.updated_at);
              setMultiModelEnabled(retrySettings.multi_model_enabled || false);
              setFitModelId(retrySettings.last_single_fit || null);
              setTailorModelId(retrySettings.last_single_tailor || null);
              setJudgeModelId(retrySettings.last_single_judge || null);
              setFitModels(retrySettings.fit_models || []);
              setTailorModels(retrySettings.tailor_models || []);
              setJudgeModels(retrySettings.judge_models || []);
            }
            return retryResp;
          } catch (retryErr) {
            console.error("[SidebarModels] Retry also failed:", retryErr);
            throw retryErr;
          }
        }
        throw e;
      }
    })();
    
    saveQueueRef.current = savePromise;
    return savePromise;
  };

  // Single-model handlers: update model_id and save
  const handleFitClick = async (alias: string) => {
    if (loading || running) return;
    
    const opt = MODEL_OPTIONS.find(m => m.alias === alias);
    if (!opt) return;

    const newModelId = opt.model_id;
    setFitModelId(newModelId);
    if (!isAuthenticated) return;

    await queueSave(async () => {
      const payload = {
        settings: {
          multi_model_enabled: multiModelEnabled,
          fit_models: fitModels,
          tailor_models: tailorModels,
          judge_models: judgeModels,
          last_single_fit: newModelId,
          last_single_tailor: tailorModelId,
          last_single_judge: judgeModelId
        },
        expected_updated_at: updatedAt
      };
      
      if (isRtDebug()) {
        console.log('[SidebarModels] 📤 handleFitClick - sending payload:', {
          last_single_fit: payload.settings.last_single_fit,
          last_single_tailor: payload.settings.last_single_tailor,
          last_single_judge: payload.settings.last_single_judge
        });
      }
      
      return await api.put<any>("/users/me/model-settings", payload);
    });
  };

  // Single-model handler: tailor
  const handleTailorClick = async (alias: string) => {
    if (loading || running) return;
    
    const opt = MODEL_OPTIONS.find(m => m.alias === alias);
    if (!opt) return;

    const newModelId = opt.model_id;
    setTailorModelId(newModelId);
    if (!isAuthenticated) return;

    await queueSave(async () => {
      return await api.put<any>("/users/me/model-settings", {
        settings: {
          multi_model_enabled: multiModelEnabled,
          fit_models: fitModels,
          tailor_models: tailorModels,
          judge_models: judgeModels,
          last_single_fit: fitModelId,
          last_single_tailor: newModelId,
          last_single_judge: judgeModelId
        },
        expected_updated_at: updatedAt
      });
    });
  };

  const handleJudgeClick = async (alias: string) => {
    if (loading || running) return;
    
    const opt = MODEL_OPTIONS.find(m => m.alias === alias);
    if (!opt) return;

    const newModelId = opt.model_id;
    setJudgeModelId(newModelId);
    if (!isAuthenticated) return;

    await queueSave(async () => {
      return await api.put<any>("/users/me/model-settings", {
        settings: {
          multi_model_enabled: multiModelEnabled,
          fit_models: fitModels,
          tailor_models: tailorModels,
          judge_models: judgeModels,
          last_single_fit: fitModelId,
          last_single_tailor: tailorModelId,
          last_single_judge: newModelId
        },
        expected_updated_at: updatedAt
      });
    });
  };

  // Multi-model toggle
  const handleMultiModelToggle = async () => {
    if (loading || running) return;
    
    const newValue = !multiModelEnabled;
    setMultiModelEnabled(newValue);
    
    if (newValue) {
      // Entering multi-mode: seed arrays from single selection if empty
      const newFitModels = fitModels.length === 0 && fitModelId ? [fitModelId] : fitModels;
      const newTailorModels = tailorModels.length === 0 && tailorModelId ? [tailorModelId] : tailorModels;
      const newJudgeModels = judgeModels.length === 0 && judgeModelId ? [judgeModelId] : judgeModels;
      
      setFitModels(newFitModels);
      setTailorModels(newTailorModels);
      setJudgeModels(newJudgeModels);
      
      if (!isAuthenticated) return;
      
      await queueSave(async () => {
        return await api.put<any>("/users/me/model-settings", {
          settings: {
            multi_model_enabled: true,
            fit_models: newFitModels,
            tailor_models: newTailorModels,
            judge_models: newJudgeModels,
            last_single_fit: fitModelId,
            last_single_tailor: tailorModelId,
            last_single_judge: judgeModelId
          },
          expected_updated_at: updatedAt
        });
      });
    } else {
      // Leaving multi-mode: use first selected model from each array (or keep current single)
      const newFitModelId = fitModels.length > 0 ? fitModels[0] : fitModelId;
      const newTailorModelId = tailorModels.length > 0 ? tailorModels[0] : tailorModelId;
      const newJudgeModelId = judgeModels.length > 0 ? judgeModels[0] : judgeModelId;
      
      setFitModelId(newFitModelId);
      setTailorModelId(newTailorModelId);
      setJudgeModelId(newJudgeModelId);
      
      if (!isAuthenticated) return;
      
      await queueSave(async () => {
        return await api.put<any>("/users/me/model-settings", {
          settings: {
            multi_model_enabled: false,
            last_single_fit: newFitModelId,
            last_single_tailor: newTailorModelId,
            last_single_judge: newJudgeModelId,
            fit_models: fitModels,
            tailor_models: tailorModels,
            judge_models: judgeModels
          },
          expected_updated_at: updatedAt
        });
      });
    }
  };

  // Multi-model checkbox handlers
  const handleFitCheckbox = async (alias: string) => {
    if (loading || running) return;
    
    const opt = MODEL_OPTIONS.find(m => m.alias === alias);
    if (!opt) return;
    
    const modelId = opt.model_id;
    const newFitModels = fitModels.includes(modelId)
      ? fitModels.filter(m => m !== modelId)
      : [...fitModels, modelId];
    setFitModels(newFitModels);

    if (!isAuthenticated) return;

    await queueSave(async () => {
      return await api.put<any>("/users/me/model-settings", {
        settings: {
          multi_model_enabled: multiModelEnabled,
          fit_models: newFitModels,
          tailor_models: tailorModels,
          judge_models: judgeModels,
          last_single_fit: fitModelId,
          last_single_tailor: tailorModelId,
          last_single_judge: judgeModelId
        },
        expected_updated_at: updatedAt
      });
    });
  };

  const handleTailorCheckbox = async (alias: string) => {
    if (loading || running) return;
    
    const opt = MODEL_OPTIONS.find(m => m.alias === alias);
    if (!opt) return;
    
    const modelId = opt.model_id;
    const newTailorModels = tailorModels.includes(modelId)
      ? tailorModels.filter(m => m !== modelId)
      : [...tailorModels, modelId];
    setTailorModels(newTailorModels);

    if (!isAuthenticated) return;

    await queueSave(async () => {
      return await api.put<any>("/users/me/model-settings", {
        settings: {
          multi_model_enabled: multiModelEnabled,
          fit_models: fitModels,
          tailor_models: newTailorModels,
          judge_models: judgeModels,
          last_single_fit: fitModelId,
          last_single_tailor: tailorModelId,
          last_single_judge: judgeModelId
        },
        expected_updated_at: updatedAt
      });
    });
  };

  const handleJudgeCheckbox = async (alias: string) => {
    if (loading || running) return;
    
    const opt = MODEL_OPTIONS.find(m => m.alias === alias);
    if (!opt) return;
    
    const modelId = opt.model_id;
    const newJudgeModels = judgeModels.includes(modelId)
      ? judgeModels.filter(m => m !== modelId)
      : [...judgeModels, modelId];
    setJudgeModels(newJudgeModels);

    if (!isAuthenticated) return;

    await queueSave(async () => {
      return await api.put<any>("/users/me/model-settings", {
        settings: {
          multi_model_enabled: multiModelEnabled,
          fit_models: fitModels,
          tailor_models: tailorModels,
          judge_models: newJudgeModels,
          last_single_fit: fitModelId,
          last_single_tailor: tailorModelId,
          last_single_judge: judgeModelId
        },
        expected_updated_at: updatedAt
      });
    });
  };

  // Select all handlers
  const handleSelectAllFit = async () => {
    if (loading || running) return; // Only block during initial load or job running
    
    const availableIds = MODEL_OPTIONS
      .filter(m => isModelAvailable(m.model_id))
      .map(m => m.model_id);
    const newFitModels = fitModels.length === availableIds.length ? [] : availableIds;
    setFitModels(newFitModels);
    
    // Skip API call if not logged in
    if ((!isAuthenticated)) return;
    
    await saveSetting({ fit_models: newFitModels });
  };

  const handleSelectAllTailor = async () => {
    if (loading || running) return; // Only block during initial load or job running
    
    const availableIds = MODEL_OPTIONS
      .filter(m => isModelAvailable(m.model_id))
      .map(m => m.model_id);
    const newTailorModels = tailorModels.length === availableIds.length ? [] : availableIds;
    setTailorModels(newTailorModels);
    
    // Skip API call if not logged in
    if ((!isAuthenticated)) return;
    
    await saveSetting({ tailor_models: newTailorModels });
  };

  const handleSelectAllJudge = async () => {
    if (loading || running) return; // Only block during initial load or job running
    
    const availableIds = MODEL_OPTIONS.filter(m => isModelAvailable(m.model_id)).map(m => m.model_id);
    const newJudgeModels = judgeModels.length === availableIds.length ? [] : availableIds;
    setJudgeModels(newJudgeModels);
    
    // Skip API call if not logged in
    if ((!isAuthenticated)) return;
    
    await saveSetting({ judge_models: newJudgeModels });
  };

  // Helper to save settings
  const saveSetting = async (updates: any) => {
    // Skip API call if not logged in
    if ((!isAuthenticated)) return;
    
    await queueSave(async () => {
      return await api.put<any>("/users/me/model-settings", {
        settings: {
          multi_model_enabled: multiModelEnabled,
          fit_models: fitModels,
          tailor_models: tailorModels,
          judge_models: judgeModels,
          last_single_fit: fitModelId,
          last_single_tailor: tailorModelId,
          last_single_judge: judgeModelId,
          ...updates
        },
        expected_updated_at: updatedAt
      });
    });
  };

  // Authenticated users wait for persisted DB settings. Logged-out users render the
  // deterministic default controls immediately so SSR and hydration do not swap a
  // one-line loading placeholder for the full model UI on page load.
  if (loading) {
    if (isRtDebug()) console.log('[SidebarModels] Rendering loading state:', { loading, fitModelId });
    return <div className="text-slate-400" suppressHydrationWarning>Loading...</div>;
  }
  
  if (isRtDebug()) console.log('[SidebarModels] Rendering full UI:', { loading, fitModelId, multiModelEnabled });

  return (
    <div className="space-y-5" suppressHydrationWarning>
      {/* Multi-model toggle */}
      <label className="flex items-center gap-2 font-semibold text-lg cursor-pointer select-none">
        <input
          type="checkbox"
          className="accent-amber-500"
          checked={multiModelEnabled}
          onChange={handleMultiModelToggle}
          disabled={loading || running}
        />
        <span>Multi-model</span>
      </label>

      {/* Fit Models */}
      <div key={`fit-section-${fitModelId || 'none'}`}>
        <div className="text-lg font-semibold mb-2">
          {multiModelEnabled ? "Fit Models" : "Fit Model"}
        </div>
        <div className={`space-y-1.5 ${multiModelEnabled ? 'mb-4' : ''}`}>
          {multiModelEnabled && (
            <label className="flex items-start gap-1.5 min-h-5 cursor-pointer">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 mt-1 accent-amber-500"
                checked={(() => {
                  const availableIds = MODEL_OPTIONS.filter(m => isModelAvailable(m.model_id)).map(m => m.model_id);
                  return availableIds.length > 0 && fitModels.length === availableIds.length;
                })()}
                onChange={handleSelectAllFit}
                disabled={loading || running}
              />
              <span className="text-sm leading-5">Select all</span>
            </label>
          )}
          {MODEL_OPTIONS.map(m => {
            const available = isModelAvailable(m.model_id);
            const modelId = m.model_id;
            const isChecked = multiModelEnabled ? fitModels.includes(modelId) : fitModelId === modelId;
            
            // Debug: log the check for Claude Sonnet 4.6
            if (isRtDebug() && m.alias === "Claude Sonnet 4.6") {
              console.log('[SidebarModels] Radio button render:', {
                alias: m.alias,
                modelId: m.model_id,
                fitModelId: fitModelId,
                isChecked: isChecked,
                multiModelEnabled: multiModelEnabled,
                matches: fitModelId === modelId,
                willRenderChecked: isChecked // This should be passed to the input
              });
            }
            
            // Keep selected radio enabled during running, disable others
            const isDisabled = loading || !available || (running && !isChecked);
            
            return (
              <label 
                key={`fit-${multiModelEnabled ? 'multi' : 'single'}-${m.alias}`}
                className={`flex items-start gap-2 min-h-6 ${available ? 'cursor-pointer' : 'opacity-50'}`}
                title={available ? `${m.provider_display} (${m.description})` : `Not available during trial`}
              >
                {multiModelEnabled ? (
                  <input
                    key={`fit-checkbox-${m.model_id}-${isDisabled}`}
                    type="checkbox"
                    className="h-4 w-4 mt-1 accent-amber-500"
                    disabled={isDisabled}
                    checked={isChecked}
                    onChange={() => handleFitCheckbox(m.alias)}
                  />
                ) : (
                  <input
                    key={`fit-radio-${m.model_id}`}
                    type="radio"
                    value={m.model_id}
                    className="h-4 w-4 mt-1 accent-amber-500"
                    disabled={isDisabled}
                    checked={isChecked}
                    onChange={() => handleFitClick(m.alias)}
                  />
                )}
                <span className="text-base leading-6">{m.alias}</span>
              </label>
            );
          })}
        </div>
      </div>

      {/* Tailor Models */}
      <div key={`tailor-section-${tailorModelId || 'none'}`}>
        <div className="text-lg font-semibold mb-2">
          {multiModelEnabled ? "Tailor Models" : "Tailor Model"}
        </div>
        <div className={`space-y-1.5 ${multiModelEnabled ? 'mb-4' : ''}`}>
          {multiModelEnabled && (
            <label className="flex items-start gap-1.5 min-h-5 cursor-pointer">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 mt-1 accent-amber-500"
                checked={(() => {
                  const availableIds = MODEL_OPTIONS.filter(m => isModelAvailable(m.model_id)).map(m => m.model_id);
                  return availableIds.length > 0 && tailorModels.length === availableIds.length;
                })()}
                onChange={handleSelectAllTailor}
                disabled={loading || running}
              />
              <span className="text-sm leading-5">Select all</span>
            </label>
          )}
          {MODEL_OPTIONS.map(m => {
            const available = isModelAvailable(m.model_id);
            const modelId = m.model_id;
            const isChecked = multiModelEnabled ? tailorModels.includes(modelId) : tailorModelId === modelId;
            // Keep selected radio enabled during running, disable others
            const isDisabled = loading || !available || (running && !isChecked);
            
            return (
              <label 
                key={`tailor-${multiModelEnabled ? 'multi' : 'single'}-${m.alias}`}
                className={`flex items-start gap-2 min-h-6 ${available ? 'cursor-pointer' : 'opacity-50'}`}
                title={available ? `${m.provider_display} (${m.description})` : `Not available during trial`}
              >
                {multiModelEnabled ? (
                  <input
                    key={`tailor-checkbox-${m.model_id}-${isDisabled}`}
                    type="checkbox"
                    className="h-4 w-4 mt-1 accent-amber-500"
                    disabled={isDisabled}
                    checked={isChecked}
                    onChange={() => handleTailorCheckbox(m.alias)}
                  />
                ) : (
                  <input
                    key={`tailor-radio-${m.model_id}`}
                    type="radio"
                    value={m.model_id}
                    className="h-4 w-4 mt-1 accent-amber-500"
                    disabled={isDisabled}
                    checked={isChecked}
                    onChange={() => handleTailorClick(m.alias)}
                  />
                )}
                <span className="text-base leading-6">{m.alias}</span>
              </label>
            );
          })}
        </div>
      </div>

      {/* Judge Models */}
      {showJudge && (
        <div key={`judge-section-${judgeModelId || 'none'}`}>
          <div className="text-lg font-semibold mb-2">
            {multiModelEnabled ? "Judge Models" : "Judge Model"}
          </div>
          <div className={`space-y-1.5 ${multiModelEnabled ? 'mb-4' : ''}`}>
            {multiModelEnabled && (
              <label className="flex items-start gap-1.5 min-h-5 cursor-pointer">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 mt-1 accent-amber-500"
                  checked={(() => {
                    const availableIds = MODEL_OPTIONS.filter(m => isModelAvailable(m.model_id)).map(m => m.model_id);
                    return availableIds.length > 0 && judgeModels.length === availableIds.length;
                  })()}
                  onChange={handleSelectAllJudge}
                  disabled={loading || running}
                />
                <span className="text-sm leading-5">Select all</span>
              </label>
            )}
            {MODEL_OPTIONS.map(m => {
            const available = isModelAvailable(m.model_id);
            const modelId = m.model_id;
            const isChecked = multiModelEnabled ? judgeModels.includes(modelId) : judgeModelId === modelId;
              // Keep selected radio enabled during running, disable others
              const isDisabled = loading || !available || (running && !isChecked);
              
              return (
                <label 
                  key={`judge-${multiModelEnabled ? 'multi' : 'single'}-${m.alias}`}
                  className={`flex items-start gap-2 min-h-6 ${available ? 'cursor-pointer' : 'opacity-50'}`}
                  title={available ? `${m.provider_display} (${m.description})` : `Not available during trial`}
                >
                  {multiModelEnabled ? (
                    <input
                      key={`judge-checkbox-${m.model_id}-${isDisabled}`}
                      type="checkbox"
                      className="h-4 w-4 mt-1 accent-amber-500"
                      disabled={isDisabled}
                      checked={isChecked}
                      onChange={() => handleJudgeCheckbox(m.alias)}
                    />
                  ) : (
                    <input
                      key={`judge-radio-${m.model_id}`}
                      type="radio"
                      value={m.model_id}
                      className="h-4 w-4 mt-1 accent-amber-500"
                      disabled={isDisabled}
                      checked={isChecked}
                      onChange={() => handleJudgeClick(m.alias)}
                    />
                  )}
                  <span className="text-base leading-6">{m.alias}</span>
                </label>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default SidebarModels;
