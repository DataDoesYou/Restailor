"use client";

import { useState, useEffect, useRef } from "react";
import { MODEL_OPTIONS } from "@/components/resume/models";
import api, { ApiError } from "@/lib/api";

/**
 * Test page for reproducing single-model radio button functionality
 * 
 * This page isolates and tests the core radio button selection behavior
 * from SidebarModels.tsx without the full sidebar context.
 * 
 * Features tested:
 * - Radio button selection for three model roles (fit, tailor, judge)
 * - Disabled state management during simulated "running" state
 * - Model availability filtering (simulated trial restrictions)
 * - State persistence and synchronization
 * - Database saving with optimistic concurrency control
 */
export default function TestRadioPage() {
  // State for each role (single model per role)
  const [fitModelId, setFitModelId] = useState<string | null>(null);
  const [tailorModelId, setTailorModelId] = useState<string | null>(null);
  const [judgeModelId, setJudgeModelId] = useState<string | null>(null);
  
  // UI state
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [lastSaveError, setLastSaveError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | undefined>(undefined);
  
  // Simulated trial restrictions (null = all models available, array = restricted list)
  const [trialModels, setTrialModels] = useState<string[] | null>(null);
  
  // Save queue to prevent concurrent modifications (409 conflicts)
  const saveQueueRef = useRef<Promise<any>>(Promise.resolve());
  
  // Check authentication and load initial settings
  useEffect(() => {
    let mounted = true;
    
    const checkAuth = async () => {
      try {
        const meResp = await api.get<any>("/users/me");
        if (!mounted) return;
        setIsAuthenticated(true);
        
        // Load existing settings
        await loadSettings();
      } catch (e) {
        if (!mounted) return;
        console.log('[TestRadio] Not authenticated, using defaults');
        setIsAuthenticated(false);
        setLoading(false);
        
        // Set default selections
        if (MODEL_OPTIONS.length > 0) {
          setFitModelId(MODEL_OPTIONS[0].model_id);
          setTailorModelId(MODEL_OPTIONS[6].model_id);
          setJudgeModelId(MODEL_OPTIONS[6].model_id);
        }
      }
    };
    
    checkAuth();
    return () => { mounted = false; };
  }, []);
  
  // Load settings from database
  const loadSettings = async () => {
    try {
      const resp = await api.get<any>("/users/me/model-settings");
      const settings = resp.settings || resp;
      
      // Load state directly from DB
      setFitModelId(settings.last_single_fit || null);
      setTailorModelId(settings.last_single_tailor || null);
      setJudgeModelId(settings.last_single_judge || null);
      setUpdatedAt(settings.updated_at);
      
      console.log('[TestRadio] Loaded settings:', {
        fit: settings.last_single_fit,
        tailor: settings.last_single_tailor,
        judge: settings.last_single_judge,
        updated_at: settings.updated_at
      });
    } catch (e) {
      console.error('[TestRadio] Failed to load settings:', e);
    } finally {
      setLoading(false);
    }
  };
  
  // Queue save operations to prevent conflicts
  const queueSave = async (saveFn: () => Promise<any>) => {
    const savePromise = saveQueueRef.current.then(async () => {
      setSaving(true);
      setLastSaveError(null);
      
      try {
        const resp = await saveFn();
        if (resp?.settings?.updated_at) {
          setUpdatedAt(resp.settings.updated_at);
        }
        console.log('[TestRadio] Save successful, new updated_at:', resp?.settings?.updated_at);
        return resp;
      } catch (e) {
        console.error('[TestRadio] Save failed:', e);
        
        // Handle 409 conflict - refetch and retry
        if (e instanceof ApiError && e.status === 409) {
          setLastSaveError('Conflict detected, retrying...');
          try {
            await loadSettings();
            const retryResp = await saveFn();
            if (retryResp?.settings?.updated_at) {
              setUpdatedAt(retryResp.settings.updated_at);
            }
            setLastSaveError(null);
            return retryResp;
          } catch (retryErr) {
            const msg = retryErr instanceof Error ? retryErr.message : 'Retry failed';
            setLastSaveError(msg);
            throw retryErr;
          }
        }
        
        const msg = e instanceof Error ? e.message : 'Save failed';
        setLastSaveError(msg);
        throw e;
      } finally {
        setSaving(false);
      }
    });
    
    saveQueueRef.current = savePromise;
    return savePromise;
  };
  
  // Helper to check if a model is available
  const isModelAvailable = (modelId: string): boolean => {
    if (!trialModels) return true; // null = all available
    return trialModels.includes(modelId);
  };
  
  // Click handlers for each role
  const handleFitClick = async (modelId: string) => {
    if (loading || running || saving) return;
    console.log('[TestRadio] Fit model selected:', modelId);
    setFitModelId(modelId);
    
    if (!isAuthenticated) return;
    
    await queueSave(async () => {
      return await api.put<any>("/users/me/model-settings", {
        settings: {
          last_single_fit: modelId,
          last_single_tailor: tailorModelId,
          last_single_judge: judgeModelId
        },
        expected_updated_at: updatedAt
      });
    });
  };
  
  const handleTailorClick = async (modelId: string) => {
    if (loading || running || saving) return;
    console.log('[TestRadio] Tailor model selected:', modelId);
    setTailorModelId(modelId);
    
    if (!isAuthenticated) return;
    
    await queueSave(async () => {
      return await api.put<any>("/users/me/model-settings", {
        settings: {
          last_single_fit: fitModelId,
          last_single_tailor: modelId,
          last_single_judge: judgeModelId
        },
        expected_updated_at: updatedAt
      });
    });
  };
  
  const handleJudgeClick = async (modelId: string) => {
    if (loading || running || saving) return;
    console.log('[TestRadio] Judge model selected:', modelId);
    setJudgeModelId(modelId);
    
    if (!isAuthenticated) return;
    
    await queueSave(async () => {
      return await api.put<any>("/users/me/model-settings", {
        settings: {
          last_single_fit: fitModelId,
          last_single_tailor: tailorModelId,
          last_single_judge: modelId
        },
        expected_updated_at: updatedAt
      });
    });
  };
  
  // Toggle running state for testing disabled behavior
  const toggleRunning = () => {
    setRunning(!running);
  };
  
  // Toggle trial restrictions
  const toggleTrialRestrictions = () => {
    if (trialModels === null) {
      // Restrict to first 3 models
      setTrialModels([
        MODEL_OPTIONS[0].model_id, // Claude Sonnet 4.5
        MODEL_OPTIONS[2].model_id, // Gemini 2.5 Flash
        MODEL_OPTIONS[6].model_id, // Grok 4 Fast
      ]);
    } else {
      // Remove restrictions
      setTrialModels(null);
    }
  };
  
  // Render a model radio button group
  const renderModelGroup = (
    title: string,
    selectedModelId: string | null,
    handleClick: (modelId: string) => void,
    groupName: string
  ) => {
    return (
      <div className="space-y-3">
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <div className="space-y-1.5">
          {MODEL_OPTIONS.map((model) => {
            const available = isModelAvailable(model.model_id);
            const isChecked = selectedModelId === model.model_id;
            // Keep selected radio enabled during running, disable others
            const isDisabled = loading || saving || !available || (running && !isChecked);
            
            return (
              <label
                key={`${groupName}-radio-${model.model_id}`}
                className={`flex items-start gap-2 min-h-6 ${
                  available ? 'cursor-pointer' : 'opacity-50'
                }`}
                title={
                  available
                    ? `${model.provider_display} (${model.description})`
                    : `Not available during trial`
                }
              >
                <input
                  type="radio"
                  name={groupName}
                  className="h-4 w-4 mt-1 accent-amber-500"
                  disabled={isDisabled}
                  checked={isChecked}
                  onChange={() => handleClick(model.model_id)}
                />
                <span className="text-base leading-6 text-white">
                  {model.alias}
                </span>
              </label>
            );
          })}
        </div>
      </div>
    );
  };
  
  return (
    <div className="min-h-screen bg-slate-900 p-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">
            Radio Button Test Page
          </h1>
          <p className="text-slate-400">
            Testing single-model radio button selection from SidebarModels.tsx
          </p>
        </div>
        
        {/* Control Panel */}
        <div className="bg-slate-800 rounded-lg p-6 mb-6 space-y-4">
          <h2 className="text-xl font-semibold text-white mb-4">Controls</h2>
          
          <div className="flex gap-4">
            <button
              onClick={toggleRunning}
              className={`px-4 py-2 rounded font-medium ${
                running
                  ? 'bg-red-600 hover:bg-red-700'
                  : 'bg-green-600 hover:bg-green-700'
              } text-white`}
            >
              {running ? 'Stop Running' : 'Start Running'}
            </button>
            
            <button
              onClick={toggleTrialRestrictions}
              className="px-4 py-2 rounded font-medium bg-blue-600 hover:bg-blue-700 text-white"
            >
              {trialModels === null
                ? 'Apply Trial Restrictions'
                : 'Remove Trial Restrictions'}
            </button>
          </div>
          
          {/* Status Display */}
          <div className="text-sm space-y-1">
            <p className="text-slate-300">
              <span className="font-medium">Authenticated:</span>{' '}
              <span className={isAuthenticated ? 'text-green-400' : 'text-red-400'}>
                {isAuthenticated === undefined ? 'Checking...' : isAuthenticated ? 'Yes' : 'No'}
              </span>
            </p>
            <p className="text-slate-300">
              <span className="font-medium">Loading:</span>{' '}
              <span className={loading ? 'text-yellow-400' : 'text-green-400'}>
                {loading ? 'Yes' : 'No'}
              </span>
            </p>
            <p className="text-slate-300">
              <span className="font-medium">Saving:</span>{' '}
              <span className={saving ? 'text-yellow-400' : 'text-green-400'}>
                {saving ? 'Yes' : 'No'}
              </span>
            </p>
            <p className="text-slate-300">
              <span className="font-medium">Running:</span>{' '}
              <span className={running ? 'text-red-400' : 'text-green-400'}>
                {running ? 'Yes' : 'No'}
              </span>
            </p>
            <p className="text-slate-300">
              <span className="font-medium">Trial Restrictions:</span>{' '}
              <span className={trialModels === null ? 'text-green-400' : 'text-yellow-400'}>
                {trialModels === null ? 'None (all models available)' : `Active (${trialModels.length} models)`}
              </span>
            </p>
            {lastSaveError && (
              <p className="text-red-400">
                <span className="font-medium">Last Error:</span> {lastSaveError}
              </p>
            )}
            {updatedAt && (
              <p className="text-slate-400 text-xs">
                <span className="font-medium">DB Updated:</span> {new Date(updatedAt).toLocaleString()}
              </p>
            )}
          </div>
        </div>
        
        {/* Current Selections */}
        <div className="bg-slate-800 rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold text-white mb-4">Current Selections</h2>
          <div className="space-y-2 text-sm">
            <p className="text-slate-300">
              <span className="font-medium">Fit:</span>{' '}
              <span className="text-amber-400">
                {fitModelId
                  ? MODEL_OPTIONS.find((m) => m.model_id === fitModelId)?.alias || fitModelId
                  : 'None'}
              </span>
            </p>
            <p className="text-slate-300">
              <span className="font-medium">Tailor:</span>{' '}
              <span className="text-amber-400">
                {tailorModelId
                  ? MODEL_OPTIONS.find((m) => m.model_id === tailorModelId)?.alias || tailorModelId
                  : 'None'}
              </span>
            </p>
            <p className="text-slate-300">
              <span className="font-medium">Judge:</span>{' '}
              <span className="text-amber-400">
                {judgeModelId
                  ? MODEL_OPTIONS.find((m) => m.model_id === judgeModelId)?.alias || judgeModelId
                  : 'None'}
              </span>
            </p>
          </div>
        </div>
        
        {/* Radio Button Groups */}
        <div className="bg-slate-800 rounded-lg p-6 space-y-6">
          {renderModelGroup('Fit Model', fitModelId, handleFitClick, 'fit_model')}
          {renderModelGroup('Tailor Model', tailorModelId, handleTailorClick, 'tailor_model')}
          {renderModelGroup('Judge Model', judgeModelId, handleJudgeClick, 'judge_model')}
        </div>
        
        {/* Instructions */}
        <div className="mt-6 bg-slate-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-3">Test Instructions</h2>
          <ul className="text-slate-300 space-y-2 text-sm list-disc list-inside">
            <li>Select different models to test radio button behavior and DB saving</li>
            <li>Click "Start Running" to test disabled state (selected radios stay enabled)</li>
            <li>Click "Apply Trial Restrictions" to test model availability filtering</li>
            <li>Check console for selection events and save operations</li>
            <li>Verify that only one model can be selected per role at a time</li>
            <li>Watch the "Saving" indicator to see when DB operations are in progress</li>
            <li>The "DB Updated" timestamp shows when the last successful save occurred</li>
            <li>Refresh the page to verify settings persist from database</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
