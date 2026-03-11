"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import StageSegments from "@/components/StageSegments";
import api from "@/lib/api";
import { updateApplicationStage } from "@/lib/apiClient";
import { normalizeStageFlags, applyStageToggle, deriveStageLabel, type StageFlagState, type StageLabel } from "@/lib/stageFlags";
import { isRtDebug, log, genNavId, setNavId } from "@/lib/rtDebug";
import {
  useHistoryData,
  type ApplicationListItem,
  type ApplicationListResponse,
} from "@/hooks/useHistoryData";
// STEAM-LIKE: Only keeping job ID helpers, removed all override cookie functions
import { writeJobId, readJobIdMap, readJobIdByHashes, readJobToken } from "@/lib/historyOverrides";
import { ToastProvider, Toast, ToastTitle, ToastDescription, ToastViewport } from "@/components/ui/toast";
import "@/lib/stageAnalyticsHelpers";

export default function HistoryClient({
  initialPage,
  initialPageSize,
  initialSearch,
  initialShowAppliedOnly,
  initialArchived,
  initialResponse,
  initialSortBy,
  initialSortDir,
  initialStageFilter,
}: {
  initialPage: number;
  initialPageSize: number;
  initialSearch: string;
  initialShowAppliedOnly: boolean;
  initialArchived: boolean;
  initialResponse: ApplicationListResponse | null;
  initialSortBy?: 'actions' | 'createdAt' | 'jdSnippet' | null;
  initialSortDir?: 'asc' | 'desc';
  // Pre-hydrated stage filter from URL (SSR) to prevent checkbox flicker and param re-computation
  initialStageFilter?: { interviewing: boolean; offer: boolean; hired: boolean };
}) {
  const isAbortError = (error: unknown): boolean => {
    if (!error) return false;
    const name = typeof (error as any)?.name === "string" ? (error as any).name : "";
    if (name === "AbortError") return true;
    const code = typeof (error as any)?.code === "string" ? (error as any).code : "";
    if (code.toUpperCase() === "ABORT_ERR" || code.toUpperCase() === "ERR_CANCELED") return true;
    const message = typeof (error as any)?.message === "string" ? (error as any).message : "";
    return /abort(ed)?/i.test(message);
  };
  // TODO(rt-hydration): Move all client-only derived state to come from server when possible (URL params -> props)
  // TODO(rt-hydration): Consider a tiny useHasMounted gate for extremely dynamic widgets if future warnings appear
  const {
    items,
    setItems,
    page,
    setPage,
    pageSize,
    total,
    loading,
    error,
    search,
    setSearch,
    searchInput,
    setSearchInput,
    showAppliedOnly,
    setShowAppliedOnly,
    stageFilter,
    setStageFilter,
    archivedTab,
    setArchivedTab,
    deleting,
    setDeleting,
    fetchData,
    sortBy,
    setSortBy,
    sortDir,
    setSortDir,
    pendingStage,
    setPendingStage,
  } = useHistoryData({
    initialPage,
    initialPageSize,
    initialSearch,
    initialShowAppliedOnly,
    initialArchived,
    initialResponse,
    initialSortBy,
    initialSortDir,
    initialStageFilter,
  });

  const [toastState, setToastState] = useState<{ id: number; title: string; description?: string } | null>(null);
  const [toastOpen, setToastOpen] = useState(false);

  const pushToast = useCallback((title: string, description?: string) => {
    setToastState({ id: Date.now(), title, description });
  }, []);

  useEffect(() => {
    if (toastState) {
      setToastOpen(true);
    }
  }, [toastState]);

  const handleToastOpenChange = useCallback((open: boolean) => {
    setToastOpen(open);
    if (!open) {
      setToastState(null);
    }
  }, []);

  const stageFetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  type StageIntent = {
    appliedKey: string;
    desiredFlags: StageFlagState;
    prevFlags: StageFlagState;
    prevLabel: StageLabel | null | undefined;
    toggleKey: keyof StageFlagState;
  };

  const stageQueueRef = useRef<Record<string, StageIntent[]>>({});
  const stageInFlightRef = useRef<Record<string, boolean>>({});
  const abortedMutationsRef = useRef<Set<string>>(new Set());
  // Track recently unapplied jobs to prevent server state from leaking through during reconciliation
  const recentlyUnappliedRef = useRef<Map<string, number>>(new Map());

  const resolveJobForItem = useCallback(
    async (appliedKey: string, item: ApplicationListItem): Promise<{ jobId?: string; jobToken?: string }> => {
      const { jobId: cachedJobId, jobToken: cachedJobToken } = findCachedJob(item);
      if (!cachedJobId) {
        return {};
      }
      if (item.jobId !== cachedJobId || item.jobToken !== cachedJobToken) {
        setItems((prev) =>
          prev.map((row) => (row.appliedKey === appliedKey ? { ...row, jobId: cachedJobId, jobToken: cachedJobToken } : row))
        );
      }
      try {
        writeJobId(appliedKey, cachedJobId, item.jobInputHashes, cachedJobToken);
      } catch {}
      return { jobId: cachedJobId, jobToken: cachedJobToken };
    },
    [setItems]
  );

  // PESSIMISTIC: Unified stage update handler with abort control + concurrency safety
  // Disables UI, awaits server, refreshes list from database
  // Aborts previous in-flight request if user clicks different stage on same row
  // Sends expectedUpdatedAt for optimistic locking (prevents overwriting concurrent changes)
  const [stagePending, setStagePending] = useState<Set<string>>(new Set());
  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());
  
  const handleSetStage = useCallback(
    async (appliedKey: string, stage: 'applied' | 'interviewing' | 'offer' | 'hired', value: boolean, expectedUpdatedAt?: string) => {
      console.log(`[handleSetStage] ${appliedKey.substring(0, 32)}... → ${stage}=${value}`, expectedUpdatedAt ? `(expectedUpdatedAt: ${expectedUpdatedAt})` : '');
      
      const pendingKey = `${appliedKey}:${stage}`;
      
      // GUARD: Prevent double-submit - if this exact request is already in flight, do nothing
      if (stagePending.has(pendingKey)) {
        console.log(`[handleSetStage] BLOCKED: ${stage} already in flight for this row`);
        return;
      }
      
      // ABORT: Cancel any other in-flight request for this row (different stage)
      const existingController = abortControllersRef.current.get(appliedKey);
      if (existingController) {
        console.log(`[handleSetStage] ABORT: Canceling previous request for ${appliedKey.substring(0, 32)}...`);
        existingController.abort();
        abortControllersRef.current.delete(appliedKey);
      }
      
      // Create new AbortController for this request
      const controller = new AbortController();
      abortControllersRef.current.set(appliedKey, controller);
      
      // OPTIMISTIC UPDATE: Immediately update UI before API call (like DB Test page)
      console.log(`[handleSetStage] Optimistically updating ${stage} to ${value}`);
      setItems(prev => prev.map(row => {
        if (row.appliedKey !== appliedKey) return row;
        
        // CASCADE: If unchecking Applied, also clear I/O/H flags
        if (stage === 'applied' && !value) {
          return { ...row, isApplied: false, interviewing: false, offer: false, hired: false };
        }
        
        // Normal update for other stages
        return { ...row, [stage === 'applied' ? 'isApplied' : stage]: value };
      }));
      
      // Disable button during request
      setStagePending(prev => new Set(prev).add(pendingKey));
      
      try {
        // PESSIMISTIC: Await server response with abort signal and optional concurrency check
        const result = await updateApplicationStage(appliedKey, stage, value, {
          signal: controller.signal,
          expectedUpdatedAt,
        });
        
        console.log(`[handleSetStage] Server responded:`, {
          isApplied: result.isApplied,
          interviewing: result.interviewing,
          offer: result.offer,
          hired: result.hired,
        });
        
        // PESSIMISTIC: Refresh list from database (single source of truth)
        // CRITICAL: Don't filter by "applied only" after update - we want to see ALL items
        console.log(`[handleSetStage] Refreshing list from database (no applied filter)...`);
        await fetchData(page, { 
          silent: true,
          showAppliedOverride: false,  // Show all items after update to verify change
          archivedOverride: archivedTab 
        });
        console.log(`[handleSetStage] List refresh complete`);
        
      } catch (error: any) {
        // Ignore abort errors (user intentionally canceled)
        if (error?.name === 'AbortError') {
          console.log(`[handleSetStage] Request aborted for ${stage}`);
          return;
        }
        
        console.error(`[handleSetStage] Error:`, error);
        const status = error?.status || error?.response?.status || 'unknown';
        const detail = error?.detail || error?.message || 'Unknown error';
        const errorSnippet = typeof detail === 'string' ? detail.substring(0, 150) : JSON.stringify(detail).substring(0, 150);
        
        // REVERT OPTIMISTIC UPDATE on error (like DB Test page)
        console.log(`[handleSetStage] Error occurred, refreshing from server to get correct state`);
        // On error, just refresh from server instead of trying to revert (simpler and safer)
        await fetchData(page, { silent: true, showAppliedOverride: false, archivedOverride: archivedTab });
        
        // CONCURRENCY: Handle 409 Conflict or 412 Precondition Failed
        if (status === 409 || status === 412) {
          pushToast("Row changed on server", "Reloading list to show latest data");
          console.log(`[handleSetStage] Concurrency conflict detected (${status}), refreshing list`);
          // Refresh list immediately to show current server state
          await fetchData(page, { silent: true, showAppliedOverride: false, archivedOverride: archivedTab });
        } else if (status === 401 || status === 403) {
          pushToast("Authentication required", `Status ${status}: Please log in again`);
        } else if (status === 404) {
          pushToast("Not found", `Status ${status}: Application not found`);
        } else if (status === 422) {
          pushToast("Validation error", `Status ${status}: ${errorSnippet}`);
        } else {
          pushToast(`Failed to update ${stage}`, `Status ${status}: ${errorSnippet}`);
        }
      } finally {
        // Clean up controller and re-enable button
        abortControllersRef.current.delete(appliedKey);
        setStagePending(prev => {
          const next = new Set(prev);
          next.delete(pendingKey);
          return next;
        });
      }
    },
    [fetchData, page, pushToast]
  );

  const runStageMutation = useCallback(
    async (intent: StageIntent): Promise<void> => {
      const { appliedKey, desiredFlags, prevFlags, prevLabel, toggleKey } = intent;
      const revert = (message?: string) => {
        setItems((prev) =>
          prev.map((row) =>
            row.appliedKey === appliedKey
              ? {
                  ...row,
                  interviewing: prevFlags.interviewing,
                  offer: prevFlags.offer,
                  hired: prevFlags.hired,
                  stageLabel: prevLabel ?? deriveStageLabel(!!row.isApplied, prevFlags),
                }
              : row
          )
        );
        setPendingStage(appliedKey, null);
        // STEAM-LIKE: No cookie writes, database is single source of truth
        if (message) {
          pushToast("Couldn't update stage", message);
        }
      };

      // CRITICAL: Check if this mutation was aborted by unapply flow
      if (abortedMutationsRef.current.has(appliedKey)) {
        console.log('🚫 [runStageMutation] ABORTED - Mutation was aborted by unapply, skipping for', appliedKey.substring(0, 20) + '...');
        abortedMutationsRef.current.delete(appliedKey);
        setPendingStage(appliedKey, null);
        return;
      }

      try {
        const currentItem = itemsRef.current.find((row) => row.appliedKey === appliedKey);
        if (!currentItem) {
          revert();
          return;
        }
        const job = await resolveJobForItem(appliedKey, currentItem);
        const desiredValue = desiredFlags[toggleKey];
        if (!job.jobId) {
          try {
            await api.patch(`/applications/stage-flags`, { appliedKey, [toggleKey]: !!desiredValue });
            
            // CRITICAL: Check AGAIN if mutation was aborted while API call was in flight
            if (abortedMutationsRef.current.has(appliedKey)) {
              console.log('🚫 [runStageMutation] ABORTED AFTER API - Mutation was aborted during API call, skipping for', appliedKey.substring(0, 20) + '...');
              abortedMutationsRef.current.delete(appliedKey);
              setPendingStage(appliedKey, null);
              return;
            }
            
            // STEAM-LIKE: Database is source of truth, no override checks needed
            // CRITICAL FIX: Clear pending BEFORE fetching fresh data so the fetch result shows through
            setPendingStage(appliedKey, null);
            try {
              await fetchData(page, { silent: true, showAppliedOverride: false, archivedOverride: archivedTab });
            } catch {}
            return;
          } catch (error: any) {
            if (isAbortError(error)) {
              return;
            }
            const status = (error && typeof error.status === "number") ? error.status : error?.response?.status;
            console.error('[runStageMutation] API error:', status, error);
            const expected = status === 401 || status === 403 || status === 404;
            if (!expected) {
              const msg = typeof status === "number"
                ? `Server responded with ${status}. Please try again.`
                : "Unexpected error. Please try again.";
              revert(msg);
            }
            return;
          }
        }
        try {
          await api.patch(`/jobs/${job.jobId}/stage-flags`, { [toggleKey]: !!desiredValue }, { xJobToken: String(job.jobToken || "") });
          
          // CRITICAL: Check AGAIN if mutation was aborted while API call was in flight
          if (abortedMutationsRef.current.has(appliedKey)) {
            console.log('🚫 [runStageMutation] ABORTED AFTER API - Mutation was aborted during API call (jobs path), skipping for', appliedKey.substring(0, 20) + '...');
            abortedMutationsRef.current.delete(appliedKey);
            setPendingStage(appliedKey, null);
            return;
          }
          
          // STEAM-LIKE: Database is source of truth, no override checks needed
          // CRITICAL FIX: Clear pending BEFORE fetching fresh data so the fetch result shows through
          setPendingStage(appliedKey, null);
          try {
            await fetchData(page, { silent: true, showAppliedOverride: false, archivedOverride: archivedTab });
          } catch {}
        } catch (error: any) {
          if (isAbortError(error)) {
            return;
          }
          const status = (error && typeof error.status === "number") ? error.status : error?.response?.status;
          console.error('[runStageMutation] API error (jobs endpoint):', status, error);
          const expected = status === 401 || status === 403 || status === 404;
          if (!expected) {
            const msg = typeof status === "number"
              ? `Server responded with ${status}. Please try again.`
              : "Unexpected error. Please try again.";
            revert(msg);
          }
        }
      } catch (err) {
        console.error('[runStageMutation] Unexpected error:', err);
        revert("We couldn't save your change. Please retry.");
      }
    },
    [fetchData, page, pushToast, resolveJobForItem, setItems, setPendingStage]
  );

  const processStageQueue = useCallback(
    async (appliedKey: string): Promise<void> => {
      const queue = stageQueueRef.current[appliedKey];
      if (!queue || queue.length === 0) {
        delete stageQueueRef.current[appliedKey];
        stageInFlightRef.current[appliedKey] = false;
        // CRITICAL FIX: Ensure pending is cleared even when queue is empty
        setPendingStage(appliedKey, null);
        return;
      }
      const intent = queue[0];
      setPendingStage(appliedKey, intent.desiredFlags);
      await runStageMutation(intent);
      queue.shift();
      
      // Note: Pending state is now cleared inside runStageMutation after API success
      // This ensures fresh data from fetchData shows through immediately
      
      if (queue.length > 0) {
        await processStageQueue(appliedKey);
        return;
      }
      delete stageQueueRef.current[appliedKey];
      stageInFlightRef.current[appliedKey] = false;
    },
    [runStageMutation, setPendingStage]
  );

  const enqueueStageIntent = useCallback(
    (intent: StageIntent) => {
      const normalizedIntent: StageIntent = {
        ...intent,
        desiredFlags: normalizeStageFlags(intent.desiredFlags),
      };
      const queue = stageQueueRef.current[intent.appliedKey] ?? [];
      queue.push(normalizedIntent);
      stageQueueRef.current[intent.appliedKey] = queue;
      if (!stageInFlightRef.current[intent.appliedKey]) {
        stageInFlightRef.current[intent.appliedKey] = true;
        void processStageQueue(intent.appliedKey);
      }
    },
    [processStageQueue]
  );

  const findCachedJob = (item: ApplicationListItem): { jobId?: string; jobToken?: string } => {
    let jobId = item.jobId ?? undefined;
    if (!jobId) {
      try {
        const map = readJobIdMap();
        const byKey = map[item.appliedKey];
        if (byKey) {
          jobId = byKey;
        }
      } catch {}
      if (!jobId) {
        try {
          jobId = readJobIdByHashes(item.jobInputHashes);
        } catch {}
      }
    }
    let jobToken = item.jobToken ?? undefined;
    if (jobId && !jobToken) {
      try {
        jobToken = readJobToken(jobId) ?? undefined;
      } catch {}
    }
    return { jobId: jobId ?? undefined, jobToken: jobToken ?? undefined };
  };

  type SortBy = 'actions' | 'createdAt' | 'jdSnippet';
  type SortDir = 'asc' | 'desc';

  useEffect(() => () => {
    if (stageFetchTimer.current) {
      clearTimeout(stageFetchTimer.current);
      stageFetchTimer.current = null;
    }
  }, []);

  // Note: Search debouncing and mount refresh are handled by useHistoryData hook

  const maxPage = Math.max(1, Math.ceil(total / pageSize));

  // Sorting (persisted)
  const SORT_STORAGE_KEY = 'rt_history_sort';
  const writeSortPref = (by: SortBy | null, dir: SortDir) => {
    try {
      if (typeof window === 'undefined') return;
      window.localStorage.setItem(SORT_STORAGE_KEY, JSON.stringify({ by, dir }));
      // Mirror to cookie so SSR renders with same state next load
      try {
        const secure = (typeof location !== 'undefined' && location.protocol === 'https:') ? '; Secure' : '';
        document.cookie = `rt_history_sort=${encodeURIComponent(JSON.stringify({ by, dir }))}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
      } catch {}
    } catch {}
  };
  // sortBy/sortDir state declared above fetchData

  const sortHydratedRef = useRef(false);

  useEffect(() => {
    if (sortHydratedRef.current) return;
    sortHydratedRef.current = true;

  let candidateBy: SortBy | null = null;
  let candidateDir: SortDir = 'desc';

    try {
      const url = new URL(window.location.href);
      const s = url.searchParams.get('sort');
      const d = url.searchParams.get('dir');
      const mapped = s === 'updatedAt' ? 'createdAt' : s;
      if (mapped === 'actions' || mapped === 'createdAt' || mapped === 'jdSnippet') {
        candidateBy = mapped as SortBy;
        candidateDir = d === 'asc' ? 'asc' : 'desc';
      }
    } catch {}

    if (!candidateBy) {
      try {
        const raw = window.localStorage.getItem(SORT_STORAGE_KEY);
        if (raw) {
          const parsed = JSON.parse(raw);
          const by = parsed?.by;
          const dir = parsed?.dir;
          if (by === 'actions' || by === 'updatedAt' || by === 'jdSnippet') {
            candidateBy = (by === 'updatedAt' ? 'createdAt' : by) as SortBy;
            candidateDir = dir === 'asc' ? 'asc' : 'desc';
          }
        }
      } catch {}
    }

    if (!candidateBy) {
      try {
        const ck = document.cookie || '';
        const match = ck.match(/(?:^|; )rt_history_sort=([^;]+)/);
        if (match && match[1]) {
          const decoded = decodeURIComponent(match[1]);
          const parsed = JSON.parse(decoded);
          const by = parsed?.by;
          const dir = parsed?.dir;
          if (by === 'actions' || by === 'updatedAt' || by === 'jdSnippet') {
            candidateBy = (by === 'updatedAt' ? 'createdAt' : by) as SortBy;
            candidateDir = dir === 'asc' ? 'asc' : 'desc';
          }
        }
      } catch {}
    }

    if (candidateBy && (candidateBy !== sortBy || candidateDir !== sortDir)) {
      setSortBy(candidateBy);
      setSortDir(candidateDir);
      fetchData(page, { silent: true, showAppliedOverride: showAppliedOnly, archivedOverride: archivedTab });
    }
  }, [fetchData, page, sortBy, sortDir, showAppliedOnly, archivedTab]);

  // DATABASE-DRIVEN: Refresh data when user navigates back to History page
  // This ensures Applied state is always fresh from database, not stale SSR/cache
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        console.log('[HISTORY] Page became visible - refreshing data from database');
        fetchData(page, { silent: true, showAppliedOverride: showAppliedOnly, archivedOverride: archivedTab });
      }
    };

    // Also refresh when user focuses the window (e.g., Alt+Tab back)
    const handleFocus = () => {
      console.log('[HISTORY] Window focused - refreshing data from database');
      fetchData(page, { silent: true, showAppliedOverride: showAppliedOnly, archivedOverride: archivedTab });
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('focus', handleFocus);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('focus', handleFocus);
    };
  }, [fetchData, page, showAppliedOnly, archivedTab]);

  // DATABASE-DRIVEN: Check flag and force immediate refresh if needed
  // This runs ONCE on mount to override stale SSR data
  useEffect(() => {
    if (typeof window === 'undefined') return;
    
    const flag = sessionStorage.getItem('rt_history_needs_refresh');
    if (flag) {
      console.log('[HISTORY] Flag detected - forcing immediate DB fetch');
      sessionStorage.removeItem('rt_history_needs_refresh');
      
      // Force immediate fetch to replace SSR data
      setTimeout(() => fetchData(page, { silent: true, showAppliedOverride: showAppliedOnly, archivedOverride: archivedTab }), 0);
    }
  }, []); // Empty deps = runs once on mount

  useEffect(() => {
    try {
      const url = new URL(window.location.href);
      const existingSort = url.searchParams.get('sort');
      const existingDir = url.searchParams.get('dir');
      if (sortBy) {
        const desiredDir = sortDir || 'desc';
        if (existingSort !== sortBy || (existingDir || 'desc') !== desiredDir) {
          url.searchParams.set('sort', sortBy);
          url.searchParams.set('dir', desiredDir);
          window.history.replaceState({}, '', url.toString());
        }
      } else if (existingSort || existingDir) {
        url.searchParams.delete('sort');
        url.searchParams.delete('dir');
        window.history.replaceState({}, '', url.toString());
      }
    } catch {}
  }, [sortBy, sortDir]);

  const toggleSort = (col: SortBy) => {
    // New column or off state: start with asc for ALL columns
    if (sortBy !== col || sortBy === null) {
      setSortBy(col);
      setSortDir('asc');
      try {
        const url = new URL(window.location.href);
        url.searchParams.set('sort', col);
        url.searchParams.set('dir', 'asc');
        window.history.replaceState({}, '', url.toString());
      } catch {}
      return;
    }
    // Same column: cycle asc -> desc -> off
    if (sortDir === 'asc') {
      setSortDir('desc');
      try {
        const url = new URL(window.location.href);
        url.searchParams.set('sort', col);
        url.searchParams.set('dir', 'desc');
        window.history.replaceState({}, '', url.toString());
      } catch {}
      return;
    }
    // Was desc: turn off sorting
    setSortBy(null);
    try {
      const url = new URL(window.location.href);
      url.searchParams.delete('sort');
      url.searchParams.delete('dir');
      window.history.replaceState({}, '', url.toString());
    } catch {}
  };

  // Persist sort choice whenever it changes
  useEffect(() => {
    writeSortPref(sortBy, sortDir);
  }, [sortBy, sortDir]);

  // Map Actions (A/I/O/H) state to an ordinal for sorting
  const actionRank = (it: ApplicationListItem): number => {
    const applied = !!it.isApplied;
    const flags = normalizeStageFlags({
      interviewing: it.interviewing,
      offer: it.offer,
      hired: it.hired,
    });
    const label = it.stageLabel ?? deriveStageLabel(applied, flags);
    if (!applied && !flags.interviewing && !flags.offer && !flags.hired) return 0;
    switch (label) {
      case "hired":
        return applied ? 4 : 7;
      case "offer":
        return applied ? 3 : 6;
      case "interviewing":
        return applied ? 2 : 5;
      case "applied":
      case null:
      default:
        return applied ? 1 : 0;
    }
  };

  const cmp = (a: ApplicationListItem, b: ApplicationListItem): number => {
    if (!sortBy) return 0;
    let v = 0;
    switch (sortBy) {
      case 'actions': {
        v = actionRank(a) - actionRank(b);
        break;
      }
      case 'createdAt': {
        const ta = new Date(a.createdAt).getTime();
        const tb = new Date(b.createdAt).getTime();
        v = ta - tb;
        break;
      }
      case 'jdSnippet': {
        const sa = (a.jdSnippet || '').toLocaleLowerCase();
        const sb = (b.jdSnippet || '').toLocaleLowerCase();
        v = sa.localeCompare(sb);
        break;
      }
    }
    if (sortDir === 'desc') v = -v;
    // Stable tiebreaker: newest first (consistent with prior default)
    if (v === 0) {
      const ta = new Date(a.createdAt).getTime();
      const tb = new Date(b.createdAt).getTime();
      v = tb - ta;
    }
    return v;
  };

  const sortedItems = (() => {
    if (!sortBy) return items;
    return [...items].sort(cmp);
  })();

  // Add a small cookie-backed map for appliedKey -> jobId to keep SSR/CSR mapping consistent

  // NOTE: We previously used a mount guard to suppress hydration warnings.
  // Given SSR/CSR state is now aligned, we render immediately to avoid any loading flash.

  // Cleanup: Abort all pending requests on unmount
  useEffect(() => {
    return () => {
      if (isRtDebug()) console.log('[HistoryClient] Unmounting - aborting', abortControllersRef.current.size, 'pending requests');
      abortControllersRef.current.forEach((controller) => {
        controller.abort();
      });
      abortControllersRef.current.clear();
    };
  }, []);

  return (
    <ToastProvider swipeDirection="right" duration={5000}>
      <div className="w-full max-w-screen-xl mx-auto px-4 md:px-6 py-4 text-slate-200">
      <h1 className="text-2xl font-semibold mb-4">History</h1>
      {/* Desktop layout - hidden on mobile */}
      <div className="hidden md:flex flex-wrap gap-3 items-end mb-4 w-full">
        <div className="flex flex-col">
          <label className="text-sm mb-1" htmlFor="search">Search</label>
          <input
            id="search"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { setSearch(e.currentTarget.value); setPage(1); fetchData(1, { searchOverride: e.currentTarget.value }); } }}
            className="rounded bg-[#131820] border border-slate-700/60 px-2 py-1 w-72"
            placeholder="Search job description"
            aria-label="Search job description"
          />
        </div>
        <label className="flex items-center gap-2 text-sm ml-4">
          <input
            type="checkbox"
            className="accent-amber-500"
            checked={showAppliedOnly}
            onChange={e => {
              setPage(1);
              setShowAppliedOnly(e.target.checked);
              // Persist in URL (?applied=1)
              try {
                const url = new URL(window.location.href);
                if (e.target.checked) url.searchParams.set('applied', '1'); else url.searchParams.delete('applied');
                window.history.replaceState({}, '', url.toString());
              } catch {}
              fetchData(1, { showAppliedOverride: e.target.checked, silent: true });
            }}
            aria-label="Applied"
          />
          <span>Applied</span>
        </label>
        <div className="flex items-center gap-4 ml-2 text-sm" aria-label="Stage filters">
          {([
            { key: 'interviewing', label: 'Interviewing' },
            { key: 'offer', label: 'Offer' },
            { key: 'hired', label: 'Hired' },
          ] as const).map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2">
              <input
                type="checkbox"
                className="accent-amber-500"
                checked={stageFilter[key]}
                onChange={e => {
                  const next = { ...stageFilter, [key]: e.target.checked } as typeof stageFilter;
                  setStageFilter(next);
                  setPage(1);
                  const csv = [
                    next.interviewing ? 'interviewing' : null,
                    next.offer ? 'offer' : null,
                    next.hired ? 'hired' : null,
                  ].filter(Boolean).join(',');
                  // Reflect in URL so filters persist on refresh/navigation
                  try {
                    const url = new URL(window.location.href);
                    if (csv) url.searchParams.set('stages', csv); else url.searchParams.delete('stages');
                    window.history.replaceState({}, '', url.toString());
                  } catch {}
                  // Debounce to coalesce multiple quick toggles and fetch silently (no table flash)
                  if (stageFetchTimer.current) {
                    clearTimeout(stageFetchTimer.current);
                  }
                  stageFetchTimer.current = setTimeout(() => {
                    fetchData(1, { stagesOverride: csv, silent: true });
                    stageFetchTimer.current = null;
                  }, 120);
                }}
                aria-label={label}
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
        <div className="ml-auto flex gap-2 items-center text-sm">
          <div className="flex rounded overflow-hidden border border-slate-700/60 mr-2" role="tablist" aria-label="Archived filter">
            <button
              role="tab"
              aria-selected={!archivedTab}
              className={`px-3 py-1 ${!archivedTab ? 'bg-slate-700 text-white' : 'bg-transparent text-slate-300'}`}
              onClick={() => { if (archivedTab) { setArchivedTab(false); setPage(1); try { const url = new URL(window.location.href); url.searchParams.set('archived', '0'); window.history.replaceState({}, '', url.toString()); } catch {}; fetchData(1, { archivedOverride: false }); } }}
            >Active</button>
            <button
              role="tab"
              aria-selected={archivedTab}
              className={`px-3 py-1 ${archivedTab ? 'bg-slate-700 text-white' : 'bg-transparent text-slate-300'}`}
              onClick={() => { if (!archivedTab) { setArchivedTab(true); setPage(1); try { const url = new URL(window.location.href); url.searchParams.set('archived', '1'); window.history.replaceState({}, '', url.toString()); } catch {}; fetchData(1, { archivedOverride: true }); } }}
            >Archived</button>
          </div>
          <span className="text-slate-400">Page {page} / {maxPage}</span>
          <button
            disabled={page <= 1 || loading}
            onClick={() => { const np = Math.max(1, page - 1); setPage(np); fetchData(np); }}
            className="px-2 py-1 rounded bg-slate-700 disabled:opacity-40"
            aria-label="Previous page"
          >Prev</button>
          <button
            disabled={page >= maxPage || loading}
            onClick={() => { const np = Math.min(maxPage, page + 1); setPage(np); fetchData(np); }}
            className="px-2 py-1 rounded bg-slate-700 disabled:opacity-40"
            aria-label="Next page"
          >Next</button>
        </div>
      </div>
      {/* Mobile layout - shown only on mobile */}
      <div className="md:hidden space-y-3 mb-4">
        {/* Search bar */}
        <div className="flex flex-col">
          <label className="text-sm mb-1" htmlFor="search-mobile">Search</label>
          <input
            id="search-mobile"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { setSearch(e.currentTarget.value); setPage(1); fetchData(1, { searchOverride: e.currentTarget.value }); } }}
            className="rounded bg-[#131820] border border-slate-700/60 px-3 py-2 w-full text-base"
            placeholder="Search job description"
            aria-label="Search job description"
          />
        </div>
        {/* Applied checkbox */}
        <label className="flex items-center gap-2 text-base">
          <input
            type="checkbox"
            className="accent-amber-500 w-5 h-5"
            checked={showAppliedOnly}
            onChange={e => {
              setPage(1);
              setShowAppliedOnly(e.target.checked);
              try {
                const url = new URL(window.location.href);
                if (e.target.checked) url.searchParams.set('applied', '1'); else url.searchParams.delete('applied');
                window.history.replaceState({}, '', url.toString());
              } catch {}
              fetchData(1, { showAppliedOverride: e.target.checked, silent: true });
            }}
            aria-label="Applied"
          />
          <span>Applied</span>
        </label>
        {/* Stage filters */}
        <div className="flex flex-col gap-2 text-base" aria-label="Stage filters">
          {([
            { key: 'interviewing', label: 'Interviewing' },
            { key: 'offer', label: 'Offer' },
            { key: 'hired', label: 'Hired' },
          ] as const).map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2">
              <input
                type="checkbox"
                className="accent-amber-500 w-5 h-5"
                checked={stageFilter[key]}
                onChange={e => {
                  const next = { ...stageFilter, [key]: e.target.checked } as typeof stageFilter;
                  setStageFilter(next);
                  setPage(1);
                  const csv = [
                    next.interviewing ? 'interviewing' : null,
                    next.offer ? 'offer' : null,
                    next.hired ? 'hired' : null,
                  ].filter(Boolean).join(',');
                  try {
                    const url = new URL(window.location.href);
                    if (csv) url.searchParams.set('stages', csv); else url.searchParams.delete('stages');
                    window.history.replaceState({}, '', url.toString());
                  } catch {}
                  if (stageFetchTimer.current) {
                    clearTimeout(stageFetchTimer.current);
                  }
                  stageFetchTimer.current = setTimeout(() => {
                    fetchData(1, { stagesOverride: csv, silent: true });
                    stageFetchTimer.current = null;
                  }, 120);
                }}
                aria-label={label}
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
        {/* Active/Archived tabs */}
        <div className="flex rounded overflow-hidden border border-slate-700/60" role="tablist" aria-label="Archived filter">
          <button
            role="tab"
            aria-selected={!archivedTab}
            className={`flex-1 px-3 py-2 text-base ${!archivedTab ? 'bg-slate-700 text-white' : 'bg-transparent text-slate-300'}`}
            onClick={() => { if (archivedTab) { setArchivedTab(false); setPage(1); try { const url = new URL(window.location.href); url.searchParams.set('archived', '0'); window.history.replaceState({}, '', url.toString()); } catch {}; fetchData(1, { archivedOverride: false }); } }}
          >Active</button>
          <button
            role="tab"
            aria-selected={archivedTab}
            className={`flex-1 px-3 py-2 text-base ${archivedTab ? 'bg-slate-700 text-white' : 'bg-transparent text-slate-300'}`}
            onClick={() => { if (!archivedTab) { setArchivedTab(true); setPage(1); try { const url = new URL(window.location.href); url.searchParams.set('archived', '1'); window.history.replaceState({}, '', url.toString()); } catch {}; fetchData(1, { archivedOverride: true }); } }}
          >Archived</button>
        </div>
        {/* Pagination */}
        <div className="flex gap-2 items-center justify-between text-base">
          <span className="text-slate-400">Page {page} / {maxPage}</span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1 || loading}
              onClick={() => { const np = Math.max(1, page - 1); setPage(np); fetchData(np); }}
              className="px-3 py-2 rounded bg-slate-700 disabled:opacity-40 min-w-[60px]"
              aria-label="Previous page"
            >Prev</button>
            <button
              disabled={page >= maxPage || loading}
              onClick={() => { const np = Math.min(maxPage, page + 1); setPage(np); fetchData(np); }}
              className="px-3 py-2 rounded bg-slate-700 disabled:opacity-40 min-w-[60px]"
              aria-label="Next page"
            >Next</button>
          </div>
        </div>
    </div>
  {error && items.length === 0 && <div className="text-red-400 mb-3">{error}</div>}
      {/* Desktop table - hidden on mobile */}
      <div className="hidden md:block rounded border border-slate-700/60 overflow-x-hidden overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-800/60 text-slate-300">
            <tr>
              <th
                className="text-left p-2 font-medium w-[300px] select-none cursor-pointer"
                onClick={() => toggleSort('actions')}
                aria-sort={sortBy === 'actions' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
              >
                {`Actions${sortBy === 'actions' ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}`}
              </th>
              <th
                className="text-left p-2 font-medium whitespace-nowrap w-[160px] select-none cursor-pointer"
                onClick={() => toggleSort('createdAt')}
                aria-sort={sortBy === 'createdAt' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
              >
                {`Created${sortBy === 'createdAt' ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}`}
              </th>
              <th
                className="text-left p-2 font-medium select-none cursor-pointer"
                onClick={() => toggleSort('jdSnippet')}
                aria-sort={sortBy === 'jdSnippet' ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
              >
                {`Job Description Snippet${sortBy === 'jdSnippet' ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}`}
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={3} className="p-4 text-center text-slate-400">Loading…</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={3} className="p-4 text-center text-slate-400">No snapshots.</td></tr>
            )}
            {!loading && sortedItems.map(it => {
              // Prefer opaque snapshotId path when available; fall back to appliedKey query
              const openHref = (it.snapshotId && String(it.snapshotId).length > 0)
                ? {
                    pathname: `/resume/s/${encodeURIComponent(String(it.snapshotId))}`,
                    ...(it.isApplied ? { query: { forceApplied: 1 as const } } : {}),
                  } as const
                : { pathname: '/resume', query: { appliedKey: it.appliedKey, ...(it.isApplied ? { forceApplied: 1 as const } : {}) } } as const;
              const isDeleting = !!deleting[it.jdHash];
              const applied = it.isApplied;
              const canEditJob = !!(it.jobId && it.jobToken);
              // Stage buttons are usable when the row represents a materialized snapshot (has snapshotId or is applied)
              // or when a jobId already exists; job token improves auth but isn't strictly needed.
              const canStage = !!it.jobId;
              // All rows in History represent persisted snapshots; keep controls enabled and resolve job on demand.
              const hasSnapshot = true;
              const canStageNow = true;
              const normalizedFlags = normalizeStageFlags({
                interviewing: it.interviewing,
                offer: it.offer,
                hired: it.hired,
              });
              const inflightFlags = pendingStage[it.appliedKey] ?? null;
              const effectiveFlags = inflightFlags ?? normalizedFlags;
              const stageLabel = it.stageLabel ?? deriveStageLabel(!!it.isApplied, effectiveFlags);
              return (
                <tr key={it.appliedKey} data-testid={`history-row-${it.appliedKey}`} className={`border-t border-slate-700/40 hover:bg-slate-800/30 ${applied ? 'bg-slate-800/20' : ''}`}>
                  <td className="p-2 align-middle">
                    <div className="flex gap-2 items-center flex-nowrap">
                      <Link
                        href={openHref}
                        prefetch={false}
                        className="h-9 px-3 rounded-md bg-slate-700 hover:bg-slate-600 flex items-center justify-center whitespace-nowrap shrink-0"
                        onMouseDown={() => {
                          // Debug logging (optional) - TEMPORARILY DISABLED
                          // if (isRtDebug()) {
                          //   const navId = genNavId();
                          //   try { setNavId(navId); } catch {}
                          //   log('NAV.CLICK_OPEN', { navId, appliedKey: it.appliedKey, isApplied: !!it.isApplied, jdHash: it.jdHash, openHref });
                          // }
                          // STEAM-LIKE: No cookie writes on navigation - SSR reads from database
                          // Removed rt_open_applied_key, rt_open_force_applied, rt_applied_state, rt_applied_overrides
                        }}
                      >Open</Link>
                      <div className="flex items-center gap-2 shrink-0">
                        <StageSegments
                          testId={`stage-segments-${it.appliedKey}`}
                          flags={effectiveFlags}
                          appliedActive={applied}
                          disabled={!canStageNow}
                          pendingStages={new Set(
                            (['applied', 'interviewing', 'offer', 'hired'] as const)
                              .filter(stage => stagePending.has(`${it.appliedKey}:${stage}`))
                          )}
                          onToggleFlag={async (key, nextVal) => {
                            // PESSIMISTIC: Simple call to unified handler with concurrency check
                            // Backend handles cascade logic automatically
                            await handleSetStage(it.appliedKey, key as 'interviewing' | 'offer' | 'hired', !!nextVal, it.updatedAt);
                          }}
                          onToggleApplied={async (nextApplied) => {
                            // PESSIMISTIC: Simple call to unified handler with concurrency check
                            if (!(canStage || hasSnapshot)) {
                              throw new Error("stage_disabled");
                            }
                            await handleSetStage(it.appliedKey, 'applied', nextApplied, it.updatedAt);
                          }}
                        />
                        <button
                          disabled={isDeleting || !(canStage || hasSnapshot)}
                          onClick={async () => {
                            // Allow archiving when a job exists OR the snapshot exists; resolve job lazily if needed
                            const resolveJob = async (): Promise<{ jobId?: string; jobToken?: string }> => {
                              const { jobId: cachedJobId, jobToken: cachedJobToken } = findCachedJob(it);
                              if (!cachedJobId) {
                                return {};
                              }
                              if (it.jobId !== cachedJobId || it.jobToken !== cachedJobToken) {
                                setItems(prev => prev.map(r =>
                                  r.appliedKey === it.appliedKey ? { ...r, jobId: cachedJobId, jobToken: cachedJobToken } : r
                                ));
                              }
                              try { writeJobId(it.appliedKey, cachedJobId, it.jobInputHashes, cachedJobToken); } catch {}
                              return { jobId: cachedJobId, jobToken: cachedJobToken };
                            };
                            const j = await resolveJob();
                            if (!j.jobId) return;
                            const nextArchived = !it.isArchived;
                            const shouldRemove = (!archivedTab && nextArchived) || (archivedTab && !nextArchived);
                            // Optimistic: remove from current view immediately to avoid label-flash flicker
                            const prevKey = it.appliedKey;
                            const prevRow = it;
                            if (shouldRemove) {
                              setItems(prevRows => prevRows.filter(r => r.appliedKey !== prevKey));
                            } else {
                              setItems(prevRows => prevRows.map(r => r.appliedKey === prevKey ? { ...r, isArchived: nextArchived } : r));
                            }
                            try {
                              if (nextArchived) {
                                await api.post(`/jobs/${j.jobId}/archive`, {}, { xJobToken: String(j.jobToken || "") });
                              } else {
                                await api.delete(`/jobs/${j.jobId}/archive`, undefined, { xJobToken: String(j.jobToken || "") });
                              }
                              fetchData(page, { silent: true, showAppliedOverride: showAppliedOnly, archivedOverride: archivedTab });
                            } catch {
                              if (shouldRemove) {
                                setItems(prevRows => [prevRow, ...prevRows]);
                              } else {
                                setItems(prevRows => prevRows.map(r => r.appliedKey === prevKey ? { ...r, isArchived: !nextArchived } : r));
                              }
                            }
                          }}
                          className="h-9 px-3 rounded-md bg-slate-700 hover:bg-slate-600 disabled:opacity-50 whitespace-nowrap shrink-0 text-center flex items-center justify-center leading-none"
                          aria-label={(it.isArchived ? 'Unarchive' : 'Archive') + ' job'}
                        >{it.isArchived ? 'Unarchive' : 'Archive'}</button>
                      </div>
                    </div>
                  </td>
                  <td className="p-2 align-middle whitespace-nowrap" title={it.createdAt}>{it.createdAt.slice(0,16).replace('T',' ')}</td>
                  <td className="p-2 align-middle">
                    {it.jdSnippet ? (
                      <span
                        className="block break-words leading-snug text-slate-200"
                        style={{ display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
                        title={it.jdSnippet}
                      >
                        {it.jdSnippet}
                      </span>
                    ) : <span className="italic text-slate-500">(no jd)</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {/* Mobile card layout - shown only on mobile */}
      <div className="md:hidden space-y-3">
        {loading && (
          <div className="p-4 text-center text-slate-400">Loading…</div>
        )}
        {!loading && items.length === 0 && (
          <div className="p-4 text-center text-slate-400">No snapshots.</div>
        )}
        {!loading && sortedItems.map(it => {
          const openHref = (it.snapshotId && String(it.snapshotId).length > 0)
            ? {
                pathname: `/resume/s/${encodeURIComponent(String(it.snapshotId))}`,
                ...(it.isApplied ? { query: { forceApplied: 1 as const } } : {}),
              } as const
            : { pathname: '/resume', query: { appliedKey: it.appliedKey, ...(it.isApplied ? { forceApplied: 1 as const } : {}) } } as const;
          const isDeleting = !!deleting[it.jdHash];
          const applied = it.isApplied;
          const canStage = !!it.jobId;
          const hasSnapshot = true;
          const canStageNow = true;
          const normalizedFlags = normalizeStageFlags({
            interviewing: it.interviewing,
            offer: it.offer,
            hired: it.hired,
          });
          const inflightFlags = pendingStage[it.appliedKey] ?? null;
          const effectiveFlags = inflightFlags ?? normalizedFlags;
          const stageLabel = it.stageLabel ?? deriveStageLabel(!!it.isApplied, effectiveFlags);
          return (
            <div
              key={it.appliedKey}
              data-testid={`history-row-${it.appliedKey}`}
              className={`rounded border border-slate-700/60 p-4 ${applied ? 'bg-slate-800/20' : ''}`}
            >
              {/* Job description snippet */}
              <div className="mb-3">
                {it.jdSnippet ? (
                  <span
                    className="block break-words leading-snug text-slate-200 text-base"
                    style={{ display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}
                    title={it.jdSnippet}
                  >
                    {it.jdSnippet}
                  </span>
                ) : <span className="italic text-slate-500">(no jd)</span>}
              </div>
              {/* Created date */}
              <div className="text-sm text-slate-400 mb-3" title={it.createdAt}>
                {it.createdAt.slice(0,16).replace('T',' ')}
              </div>
              {/* Stage segments */}
              <div className="mb-3">
                <StageSegments
                  testId={`stage-segments-${it.appliedKey}`}
                  flags={effectiveFlags}
                  appliedActive={applied}
                  disabled={!canStageNow}
                  pendingStages={new Set(
                    (['applied', 'interviewing', 'offer', 'hired'] as const)
                      .filter(stage => stagePending.has(`${it.appliedKey}:${stage}`))
                  )}
                  onToggleFlag={async (key, nextVal) => {
                    await handleSetStage(it.appliedKey, key as 'interviewing' | 'offer' | 'hired', !!nextVal, it.updatedAt);
                  }}
                  onToggleApplied={async (nextApplied) => {
                    if (!(canStage || hasSnapshot)) {
                      throw new Error("stage_disabled");
                    }
                    await handleSetStage(it.appliedKey, 'applied', nextApplied, it.updatedAt);
                  }}
                />
              </div>
              {/* Action buttons */}
              <div className="flex gap-2">
                <Link
                  href={openHref}
                  prefetch={false}
                  className="flex-1 h-11 px-4 rounded-md bg-slate-700 hover:bg-slate-600 active:bg-slate-500 flex items-center justify-center whitespace-nowrap text-base font-medium"
                  onMouseDown={() => {}}
                  onClick={() => {}}
                >Open</Link>
                <button
                  disabled={isDeleting || !(canStage || hasSnapshot)}
                  onClick={async () => {
                    const resolveJob = async (): Promise<{ jobId?: string; jobToken?: string }> => {
                      const { jobId: cachedJobId, jobToken: cachedJobToken } = findCachedJob(it);
                      if (!cachedJobId) {
                        return {};
                      }
                      if (it.jobId !== cachedJobId || it.jobToken !== cachedJobToken) {
                        setItems(prev => prev.map(r =>
                          r.appliedKey === it.appliedKey ? { ...r, jobId: cachedJobId, jobToken: cachedJobToken } : r
                        ));
                      }
                      try { writeJobId(it.appliedKey, cachedJobId, it.jobInputHashes, cachedJobToken); } catch {}
                      return { jobId: cachedJobId, jobToken: cachedJobToken };
                    };
                    const j = await resolveJob();
                    if (!j.jobId) return;
                    const nextArchived = !it.isArchived;
                    const shouldRemove = (!archivedTab && nextArchived) || (archivedTab && !nextArchived);
                    const prevKey = it.appliedKey;
                    const prevRow = it;
                    if (shouldRemove) {
                      setItems(prevRows => prevRows.filter(r => r.appliedKey !== prevKey));
                    } else {
                      setItems(prevRows => prevRows.map(r => r.appliedKey === prevKey ? { ...r, isArchived: nextArchived } : r));
                    }
                    try {
                      if (nextArchived) {
                        await api.post(`/jobs/${j.jobId}/archive`, {}, { xJobToken: String(j.jobToken || "") });
                      } else {
                        await api.delete(`/jobs/${j.jobId}/archive`, undefined, { xJobToken: String(j.jobToken || "") });
                      }
                      fetchData(page, { silent: true, showAppliedOverride: showAppliedOnly, archivedOverride: archivedTab });
                    } catch {
                      if (shouldRemove) {
                        setItems(prevRows => [prevRow, ...prevRows]);
                      } else {
                        setItems(prevRows => prevRows.map(r => r.appliedKey === prevKey ? { ...r, isArchived: !nextArchived } : r));
                      }
                    }
                  }}
                  className="flex-1 h-11 px-4 rounded-md bg-slate-700 hover:bg-slate-600 active:bg-slate-500 disabled:opacity-50 whitespace-nowrap text-base font-medium flex items-center justify-center"
                  aria-label={(it.isArchived ? 'Unarchive' : 'Archive') + ' job'}
                >{it.isArchived ? 'Unarchive' : 'Archive'}</button>
              </div>
            </div>
          );
        })}
      </div>
      </div>
      {toastState && (
        <Toast key={toastState.id} open={toastOpen} onOpenChange={handleToastOpenChange}>
          <ToastTitle>{toastState.title}</ToastTitle>
          {toastState.description ? <ToastDescription>{toastState.description}</ToastDescription> : null}
        </Toast>
      )}
      <ToastViewport />
    </ToastProvider>
  );
}
