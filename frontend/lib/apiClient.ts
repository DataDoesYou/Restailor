/**
 * API client functions for user model settings.
 * 
 * Provides type-safe wrappers around the backend /users/me/model-settings endpoint.
 * Auth is handled by the underlying api module (HttpOnly cookies via credentials: 'include').
 */

import { api } from "./api";
import { isRtDebug } from "./rtDebug";

/**
 * User model preferences for multi-model feature.
 * 
 * Matches the ModelSettings Pydantic schema from backend/restailor/settings_schemas.py
 */
export type ModelSettings = {
  multi_model_enabled: boolean;
  fit_models: string[];
  tailor_models: string[];
  judge_models: string[];
  last_single_fit?: string | null;
  last_single_tailor?: string | null;
  last_single_judge?: string | null;
  analytics_period?: string;
  admin_analytics_period?: string;
  admin_analytics_tab?: string;
  updated_at?: string | null;
  version: number;
};

/**
 * Response wrapper for GET /users/me/model-settings
 */
interface GetSettingsResponse {
  settings: ModelSettings;
}

/**
 * Request body for PUT /users/me/model-settings
 */
interface PutSettingsRequest {
  settings: ModelSettings;
  expectedUpdatedAt?: string;
}

/**
 * Response wrapper for PUT /users/me/model-settings
 */
interface PutSettingsResponse {
  settings: ModelSettings;
  message: string;
}

/**
 * Fetch current user's model preferences.
 * 
 * Returns user settings from the database, or defaults if none exist yet.
 * Requires authentication (HttpOnly session cookie).
 * 
 * @returns ModelSettings - User's current preferences
 * @throws ApiError - On network failure or 401 (auth required)
 * 
 * @example
 * ```ts
 * const settings = await getUserSettings();
 * if (isRtDebug()) console.log(settings.multi_model_enabled);
 * ```
 */
export async function getUserSettings(): Promise<ModelSettings> {
  if (isRtDebug()) console.log('[apiClient] getUserSettings() - calling GET /users/me/model-settings');
  const response = await api.get<GetSettingsResponse>("/users/me/model-settings");
  if (isRtDebug()) console.log('[apiClient] getUserSettings() response:', response);
  return response.settings;
}

/**
 * Update user's model preferences.
 * 
 * Accepts partial settings (any changed fields) and optional optimistic lock timestamp.
 * If expectedUpdatedAt is provided and doesn't match current DB timestamp, returns 409.
 * 
 * All model IDs are validated against server-side allowlist. Invalid models return 422.
 * 
 * @param next - Partial settings to update + optional expectedUpdatedAt for concurrency control
 * @returns ModelSettings - Updated settings with new updated_at timestamp
 * @throws ApiError - 401 (auth), 409 (stale timestamp), 422 (invalid model IDs)
 * 
 * @example
 * ```ts
 * // Simple update (no concurrency control)
 * const updated = await putUserSettings({
 *   multi_model_enabled: true,
 *   fit_models: ["gpt-5", "claude-4.1-opus"]
 * });
 * 
 * // With optimistic locking
 * const current = await getUserSettings();
 * try {
 *   const updated = await putUserSettings({
 *     multi_model_enabled: false,
 *     expected_updated_at: current.updated_at
 *   });
 * } catch (err) {
 *   if (err.status === 409) {
 *     // Settings were modified by another request, refetch and retry
 *   }
 * }
 * ```
 */
export async function putUserSettings(
  next: Partial<ModelSettings> & { expected_updated_at?: string }
): Promise<ModelSettings> {
  if (isRtDebug()) console.log('[apiClient] putUserSettings called with:', next);
  
  // Extract optimistic lock field
  const { expected_updated_at, ...settingsFields } = next;
  
  // Build full settings object (backend expects all fields)
  // Caller must provide complete settings or fetch current first
  const settings: ModelSettings = settingsFields as ModelSettings;
  
  const requestBody: PutSettingsRequest = {
    settings,
    ...(expected_updated_at && { expectedUpdatedAt: expected_updated_at }),
  };
  
  if (isRtDebug()) console.log('[apiClient] Making PUT request to /users/me/model-settings with body:', JSON.stringify(requestBody, null, 2));
  
  try {
    const response = await api.put<PutSettingsResponse>(
      "/users/me/model-settings",
      requestBody
    );
    
    if (isRtDebug()) console.log('[apiClient] PUT response:', response);
    
    return response.settings;
  } catch (error) {
    console.error('[apiClient] PUT request failed:', error);
    if (error && typeof error === 'object' && 'detail' in error) {
      console.error('[apiClient] Error detail:', (error as any).detail);
    }
    throw error;
  }
}

/**
 * Application list item from the backend.
 * Matches ApplicationListItem from the backend response.
 */
export type ApplicationListItemType = {
  appliedKey: string;
  company?: string | null;
  role?: string | null;
  jdUrl?: string | null;
  jdHash: string;
  baseHash: string;
  createdAt: string;
  updatedAt: string;
  jdSnippet?: string | null;
  isApplied: boolean;
  jobId?: string | null;
  jobToken?: string | null;
  isArchived?: boolean | null;
  isStaged?: boolean | null;
  interviewing?: boolean | null;
  offer?: boolean | null;
  hired?: boolean | null;
  stageLabel?: string | null;
  jobInputHashes?: string[] | null;
};

/**
 * Response from GET /applications (list endpoint).
 */
interface ListApplicationsResponse {
  items: ApplicationListItemType[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/**
 * Fetch paginated list of applications.
 * 
 * PESSIMISTIC: Returns only server state, no local caching or manipulation.
 * 
 * @param params - Optional pagination, search, and filter parameters
 * @returns Promise<ListApplicationsResponse> - Paginated application list from database
 * @throws ApiError - On network failure or 401 (auth required)
 * 
 * @example
 * ```ts
 * const { items, total } = await listApplications({ 
 *   page: 1, 
 *   page_size: 20, 
 *   search: 'engineer',
 *   stage_filter: 'interviewing,offer',
 *   archived: false 
 * });
 * ```
 */
export async function listApplications(params?: {
  page?: number;
  page_size?: number;
  search?: string;
  stage_filter?: string;
  archived?: boolean;
}): Promise<ListApplicationsResponse> {
  if (isRtDebug()) console.log('[apiClient] listApplications() - calling GET /applications/list with params:', params);
  
  const response = await api.get<ListApplicationsResponse>("/applications/list", {
    query: params as Record<string, string | number | boolean | null | undefined>
  });
  
  if (isRtDebug()) console.log('[apiClient] listApplications() response:', {
    totalItems: response.total,
    itemsCount: response.items.length,
    page: response.page,
  });
  
  return response;
}

/**
 * Response from PATCH /applications/stage-flags
 */
interface UpdateStageFlagsResponse {
  ok: boolean;
  appliedKey: string;
  interviewing: boolean;
  offer: boolean;
  hired: boolean;
  isApplied: boolean;
  stageLabel: string | null;
}

/**
 * Update application stage flags using appliedKey.
 * 
 * PESSIMISTIC: Awaits server response and returns the server's updated flags.
 * NO local patching - caller must use returned data to update UI.
 * 
 * Auth handled via HttpOnly session cookie (credentials: 'include').
 * 
 * Backend enforces cascade logic: unchecking lower stages clears higher stages.
 * Setting any I/O/H flag automatically sets is_applied=true.
 * 
 * CONCURRENCY: If expectedUpdatedAt provided, sends it to backend for optimistic locking.
 * Backend returns 409 Conflict if row was modified by another request/user.
 * 
 * @param appliedKey - Application key (format: "userId:jdHash:baseHash")
 * @param stage - Stage to set: 'applied' | 'interviewing' | 'offer' | 'hired'
 * @param value - Boolean value to set (true = check, false = uncheck)
 * @param options - Optional settings
 * @param options.signal - AbortSignal for cancellation
 * @param options.expectedUpdatedAt - ISO timestamp for optimistic locking (prevents overwriting concurrent changes)
 * @returns Promise<UpdateStageFlagsResponse> - Server's updated flags
 * @throws ApiError - On network failure, 401 (auth required), 404 (not found), 409 (conflict), 422 (validation)
 * 
 * @example
 * ```ts
 * const result = await updateApplicationStage(item.appliedKey, 'interviewing', true, {
 *   expectedUpdatedAt: item.updatedAt
 * });
 * // result.interviewing === true (from server)
 * // result.isApplied === true (automatically set by backend)
 * ```
 */
export async function updateApplicationStage(
  appliedKey: string,
  stage: 'applied' | 'interviewing' | 'offer' | 'hired',
  value: boolean,
  options?: { signal?: AbortSignal; expectedUpdatedAt?: string }
): Promise<UpdateStageFlagsResponse> {
  if (isRtDebug()) console.log(`[apiClient] updateApplicationStage(${appliedKey.substring(0, 32)}..., ${stage}, ${value})`);
  
  const signal = options?.signal;
  const expectedUpdatedAt = options?.expectedUpdatedAt;
  
  const body: Record<string, any> = { appliedKey };
  
  // Add optimistic lock timestamp if provided
  if (expectedUpdatedAt) {
    body.expectedUpdatedAt = expectedUpdatedAt;
    if (isRtDebug()) console.log(`[apiClient] Sending expectedUpdatedAt for concurrency check:`, expectedUpdatedAt);
  }
  
  // For 'applied', use the /jd/apply or /jd/apply DELETE endpoints
  if (stage === 'applied') {
    if (value) {
      // Apply: POST /applications/jd/apply with appliedKey
      const response = await api.post<{ ok: boolean; jdHash: string; appliedKey: string; updatedAt: string; isApplied: boolean }>(
        `/applications/jd/apply`,
        body, // Send body with appliedKey and optional expectedUpdatedAt
        { signal }
      );
      if (isRtDebug()) console.log(`[apiClient] POST /jd/apply response:`, { isApplied: response.isApplied });
      return {
        ok: response.ok,
        appliedKey: response.appliedKey,
        interviewing: false, // Backend response doesn't include these
        offer: false,
        hired: false,
        isApplied: response.isApplied,
        stageLabel: null,
      };
    } else {
      // Unapply: DELETE /applications/jd/apply
      const jdHash = appliedKey.split(':')[1]; // Extract jdHash from appliedKey
      const queryParams: Record<string, string> = { jdHash, appliedKey };
      if (expectedUpdatedAt) {
        queryParams.expectedUpdatedAt = expectedUpdatedAt;
      }
      const response = await api.delete<{ ok: boolean; jdHash: string; appliedKey: string; changed: boolean; isApplied: boolean }>(
        `/applications/jd/apply`,
        undefined,
        { query: queryParams, signal }
      );
      if (isRtDebug()) console.log(`[apiClient] DELETE /jd/apply response:`, { isApplied: response.isApplied });
      return {
        ok: response.ok,
        appliedKey: response.appliedKey,
        interviewing: false,
        offer: false,
        hired: false,
        isApplied: response.isApplied,
        stageLabel: null,
      };
    }
  }
  
  // For I/O/H stages, use PATCH /applications/stage-flags
  body[stage] = value;
  
  const response = await api.patch<UpdateStageFlagsResponse>(
    `/applications/stage-flags`,
    body,
    { signal }
  );
  
  if (isRtDebug()) console.log(`[apiClient] PATCH /stage-flags response:`, {
    appliedKey: response.appliedKey.substring(0, 32) + '...',
    interviewing: response.interviewing,
    offer: response.offer,
    hired: response.hired,
    isApplied: response.isApplied,
  });
  
  return response;
}
