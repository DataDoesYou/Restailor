import { useState, useCallback, useEffect, useLayoutEffect, useRef } from "react";
import api from "@/lib/api";
import { normalizeStageFlags, deriveStageLabel, StageFlagState, StageLabel } from "@/lib/stageFlags";
import {
  readPendingStageMap,
  writePendingStageMap,
  readJobIdMap,
  readJobIdByHashes,
  writeJobId,
  readJobToken,
} from "@/lib/historyOverrides";

// STEAM-LIKE: Removed all override storage imports (readAppliedOverrideMap, readFlagOverrideMap, etc.)
// Database is the single source of truth. Only pending state for in-flight mutations.

function attachStageMeta(item: ApplicationListItem): ApplicationListItem {
  const normalized = normalizeStageFlags({
    interviewing: item.interviewing,
    offer: item.offer,
    hired: item.hired,
  });
  const next: ApplicationListItem = {
    ...item,
    interviewing: normalized.interviewing,
    offer: normalized.offer,
    hired: normalized.hired,
    stageLabel: deriveStageLabel(!!item.isApplied, normalized),
  };
  try {
    if (next.jobId) {
      if (!next.jobToken) {
        const cachedToken = readJobToken(next.jobId);
        if (cachedToken) {
          next.jobToken = cachedToken;
        }
      }
      writeJobId(next.appliedKey, next.jobId, next.jobInputHashes, next.jobToken);
    } else {
      const byKey = readJobIdMap()[next.appliedKey];
      const byHash = byKey || readJobIdByHashes(next.jobInputHashes);
      if (byHash) {
        next.jobId = byHash;
        const cachedToken = readJobToken(byHash);
        if (cachedToken) {
          next.jobToken = cachedToken;
        }
        writeJobId(next.appliedKey, byHash, next.jobInputHashes, next.jobToken);
      }
    }
  } catch {}
  return next;
}

export interface ApplicationListItem {
  appliedKey: string;
  jdSnippet?: string | null;
  jdHash: string;
  baseHash: string;
  createdAt: string;
  updatedAt: string;
  isApplied: boolean;
  snapshotId?: string | null;
  jobId?: string | null;
  jobToken?: string | null;
  isArchived?: boolean | null;
  isStaged?: boolean | null;
  interviewing?: boolean | null;
  offer?: boolean | null;
  hired?: boolean | null;
  stageLabel?: StageLabel | null;
  jobInputHashes?: string[] | null;
}

export interface ApplicationListResponse {
  page: number;
  pageSize: number;
  total: number;
  items: ApplicationListItem[];
}

export type UseHistoryDataOptions = {
  initialPage: number;
  initialPageSize: number;
  initialSearch: string;
  initialShowAppliedOnly: boolean;
  initialArchived: boolean;
  initialResponse: ApplicationListResponse | null;
  initialSortBy?: "actions" | "createdAt" | "jdSnippet" | null;
  initialSortDir?: "asc" | "desc";
  initialStageFilter?: { interviewing: boolean; offer: boolean; hired: boolean };
};

export type UseHistoryDataReturn = {
  items: ApplicationListItem[];
  setItems: React.Dispatch<React.SetStateAction<ApplicationListItem[]>>;
  page: number;
  setPage: React.Dispatch<React.SetStateAction<number>>;
  pageSize: number;
  total: number;
  loading: boolean;
  error: string | null;
  search: string;
  setSearch: React.Dispatch<React.SetStateAction<string>>;
  searchInput: string;
  setSearchInput: React.Dispatch<React.SetStateAction<string>>;
  showAppliedOnly: boolean;
  setShowAppliedOnly: React.Dispatch<React.SetStateAction<boolean>>;
  stageFilter: { interviewing: boolean; offer: boolean; hired: boolean };
  setStageFilter: React.Dispatch<React.SetStateAction<{ interviewing: boolean; offer: boolean; hired: boolean }>>;
  archivedTab: boolean;
  setArchivedTab: React.Dispatch<React.SetStateAction<boolean>>;
  deleting: Record<string, boolean>;
  setDeleting: React.Dispatch<React.SetStateAction<Record<string, boolean>>>;
  markHistoryDirty: () => void;
  fetchData: (page: number, opts?: { silent?: boolean; searchOverride?: string; showAppliedOverride?: boolean; archivedOverride?: boolean; stagesOverride?: string | null | string }) => Promise<void>;
  writeFlagOverrides: (
    appliedKey: string,
    next: { interviewing?: boolean; offer?: boolean; hired?: boolean } | null,
    opts?: { optimistic?: boolean }
  ) => void;
  writeAppliedOverride: (appliedKey: string, isApplied: boolean | null, opts?: { clearSiblingsOfJdHash?: string; selfOnly?: boolean; optimistic?: boolean }) => void;
  writeAppliedOverridesMap: (map: Record<string, boolean>) => void;
  sortBy: "actions" | "createdAt" | "jdSnippet" | null;
  setSortBy: React.Dispatch<React.SetStateAction<"actions" | "createdAt" | "jdSnippet" | null>>;
  sortDir: "asc" | "desc";
  setSortDir: React.Dispatch<React.SetStateAction<"asc" | "desc">>;
  abortActive: () => void;
  pendingStage: Record<string, StageFlagState>;
  setPendingStage: (appliedKey: string, next: StageFlagState | null) => void;
};

export function useHistoryData(options: UseHistoryDataOptions): UseHistoryDataReturn {
  // STEAM-LIKE: Clear stale pending state IMMEDIATELY (before any renders)
  // Only pending state is kept for in-flight mutations
  if (typeof window !== "undefined") {
    try {
      const stale = readPendingStageMap();
      if (stale && Object.keys(stale).length > 0) {
        console.log('[HISTORY INIT] Clearing', Object.keys(stale).length, 'stale pending states from previous session');
        writePendingStageMap({});
      }
    } catch {}
  }
  
  const useClientLayoutEffect = typeof window !== "undefined" ? useLayoutEffect : useEffect;
  const {
    initialPage,
    initialPageSize,
    initialSearch,
    initialShowAppliedOnly,
    initialArchived,
    initialResponse,
    initialSortBy,
    initialSortDir,
    initialStageFilter,
  } = options;

  // STEAM-LIKE: No override application - database is single source of truth
  // Only apply pending state for immediate visual feedback on in-flight mutations
  const applyPendingOnly = useCallback((list: ApplicationListItem[]): ApplicationListItem[] => {
    const pendingMap = readPendingStageMap();
    
    return list.map((it) => {
      const pending = pendingMap?.[it.appliedKey];
      if (!pending) {
        // No pending state - use database state as-is
        return attachStageMeta(it);
      }
      
      // Show pending state for in-flight mutation
      const next: ApplicationListItem = {
        ...it,
        interviewing: pending.interviewing,
        offer: pending.offer,
        hired: pending.hired,
      };
      
      return attachStageMeta(next);
    });
  }, []);

  // STEAM-LIKE: Pure database state on initialization, with pending state applied
  const [items, setItems] = useState<ApplicationListItem[]>(() => {
    return applyPendingOnly(initialResponse?.items || []);
  });
  const [page, setPage] = useState(initialPage);
  const [total, setTotal] = useState(initialResponse?.total || 0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState(initialSearch);
  const [searchInput, setSearchInput] = useState(initialSearch);
  const [showAppliedOnly, setShowAppliedOnly] = useState(initialShowAppliedOnly);
  const [stageFilter, setStageFilter] = useState(initialStageFilter ?? { interviewing: false, offer: false, hired: false });
  const [archivedTab, setArchivedTab] = useState(initialArchived);
  const [deleting, setDeleting] = useState<Record<string, boolean>>({});
  const [sortBy, setSortBy] = useState<"actions" | "createdAt" | "jdSnippet" | null>(initialSortBy ?? null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">(initialSortDir ?? "desc");
  const [pendingStage, setPendingStageMap] = useState<Record<string, StageFlagState>>(() => readPendingStageMap());
  const activeController = useRef<AbortController | null>(null);
  const requestSeq = useRef(0);
  const pageSize = initialPageSize;
  const pendingStageRef = useRef(pendingStage);

  useEffect(() => {
    pendingStageRef.current = pendingStage;
  }, [pendingStage]);

  // Pending state cleanup moved to hook initialization (above) for synchronous execution
  useClientLayoutEffect(() => {
    // Placeholder for future mount effects
  }, []);

  const hydrationAppliedRef = useRef(false);
  
  // Track if this is the first fetch after a true page load (refresh, not navigation)
  // Use window-level flag that clears on page refresh but persists during SPA navigation
  const shouldReconcileOnFirstFetch = (() => {
    if (typeof window === 'undefined') return false;
    try {
      const key = '_rtHistoryMounted';
      const alreadyMounted = (window as any)[key] === true;
      if (!alreadyMounted) {
        // First component mount after page load/refresh - should reconcile
        (window as any)[key] = true;
        console.log('[INIT] First History mount after page load - will reconcile on first fetch');
        return true;
      }
      console.log('[INIT] Subsequent History mount (navigation) - will NOT reconcile');
      return false; // Subsequent mounts during navigation - don't reconcile
    } catch {
      return false;
    }
  })();
  
  const hasReconciledRef = useRef(false); // Track if we've reconciled in this component instance
  
  useClientLayoutEffect(() => {
    // DISABLED: Skip all hydration for applied overrides
    // Fresh data fetch with reconciliation handles everything properly
    return;
    
    if (hydrationAppliedRef.current) return;
    hydrationAppliedRef.current = true;
    try {
      const appliedOverrides = readAppliedOverrideMap() || {};
      const flagOverrides = readFlagOverrideMap() || {};
      const pendingStages = readPendingStageMap() || {};
      
      console.log('[HYDRATION]', {
        appliedKeys: Object.keys(appliedOverrides).length,
        appliedOverrides: Object.keys(appliedOverrides),
        flagKeys: Object.keys(flagOverrides).length,
        pendingKeys: Object.keys(pendingStages).length,
      });
      
      // CRITICAL FIX: Don't hydrate applied overrides - reconciliation handles them
      // Applied overrides should only be processed during fresh data fetches with reconciliation
      const hasIOHOverrides = Object.keys(flagOverrides).length > 0;
      const hasPending = Object.keys(pendingStages).length > 0;
      
      if (!hasIOHOverrides && !hasPending) {
        console.log('[HYDRATION] No IOH/pending overrides found, skipping');
        return;
      }
      
      console.log('[HYDRATION] Found IOH/pending overrides');
      
      debugHistory("hydrating overrides on mount", {
        appliedKeys: Object.keys(appliedOverrides).length,
        flagKeys: Object.keys(flagOverrides).length,
        pendingKeys: Object.keys(pendingStages).length,
      });
      
      // CRITICAL: Do NOT call setItems here - it causes A button to disappear after H→O→I→A cascading
      // Problem: During cascading, multiple rapid API calls + state updates occur
      // If hydration runs during this sequence, it can call setItems with stale prev state
      // This overwrites the correct state from useState initialization
      // IOH overrides work fine without this because they're applied in applyOverrides during fetch
      // Applied overrides MUST be applied only in useState initialization, never in hydration
    } catch {}
  }, [applyOverrides]);

  const setPendingStage = useCallback((appliedKey: string, next: StageFlagState | null) => {
    setPendingStageMap((prev) => {
      if (!next) {
        const overrides = readFlagOverrideMap();
        const optimisticOverride = overrides?.[appliedKey];
        if (optimisticOverride?.optimistic) {
          const normalizedOverride = normalizeStageFlags({
            interviewing: optimisticOverride.interviewing,
            offer: optimisticOverride.offer,
            hired: optimisticOverride.hired,
          });
          const existing = prev[appliedKey];
          const matchesExisting =
            !!existing &&
            existing.interviewing === normalizedOverride.interviewing &&
            existing.offer === normalizedOverride.offer &&
            existing.hired === normalizedOverride.hired;
          if (matchesExisting) {
            debugHistory("pending stage already matches optimistic override", { appliedKey, normalizedOverride });
            return prev;
          }
          debugHistory("restoring pending stage from optimistic override", { appliedKey, normalizedOverride });
          const restored = { ...prev, [appliedKey]: normalizedOverride };
          writePendingStageMap(restored);
          return restored;
        }
        if (!prev[appliedKey]) {
          if (Object.keys(prev).length === 0) {
            writePendingStageMap({});
          }
          debugHistory("pending stage already empty", { appliedKey });
          return prev;
        }
        const cloned = { ...prev };
        delete cloned[appliedKey];
        writePendingStageMap(cloned);
        debugHistory("removed pending stage entry", { appliedKey });
        return cloned;
      }
      const normalized = normalizeStageFlags(next);
      const existing = prev[appliedKey];
      if (
        existing &&
        existing.interviewing === normalized.interviewing &&
        existing.offer === normalized.offer &&
        existing.hired === normalized.hired
      ) {
        return prev;
      }
      const updated = { ...prev, [appliedKey]: normalized };
      writePendingStageMap(updated);
      debugHistory("updated pending stage", { appliedKey, normalized });
      return updated;
    });
  }, []);

  const abortActive = useCallback(() => {
    try {
      activeController.current?.abort();
    } catch {}
    activeController.current = null;
  }, []);

  const markHistoryDirty = useCallback(() => {
    try {
      const secure = typeof location !== "undefined" && location.protocol === "https:" ? "; Secure" : "";
      document.cookie = `rt_history_dirty=1; Path=/${secure}`;
    } catch {}
  }, []);

  const writeFlagOverrides = useCallback(
    (
      appliedKey: string,
      next: { interviewing?: boolean; offer?: boolean; hired?: boolean } | null,
      opts?: { optimistic?: boolean }
    ) => {
      try {
        if (next) {
          const normalized = normalizeStageFlags({
            interviewing: next.interviewing,
            offer: next.offer,
            hired: next.hired,
          });
          const payload: HistoryFlagOverride = {
            interviewing: normalized.interviewing,
            offer: normalized.offer,
            hired: normalized.hired,
            optimistic: !!opts?.optimistic,
            updatedAt: Date.now(),
          };
          persistFlagOverride(appliedKey, payload);
        } else {
          persistFlagOverride(appliedKey, null);
        }
      } catch {}
    },
    []
  );

  const writeAppliedOverridesMap = useCallback((map: Record<string, boolean>) => {
    try {
      // Convert boolean map to new object format
      const converted: Record<string, import("@/lib/historyOverrides").HistoryAppliedOverride> = {};
      for (const [key, value] of Object.entries(map)) {
        converted[key] = {
          isApplied: value,
          optimistic: false,
          updatedAt: Date.now(),
        };
      }
      persistAppliedOverrideMap(converted);
    } catch {}
  }, []);

  const writeAppliedOverride = useCallback(
    (appliedKey: string, isApplied: boolean | null, opts?: { clearSiblingsOfJdHash?: string; selfOnly?: boolean; optimistic?: boolean }) => {
      try {
        if (typeof window === "undefined") return;
        const map = { ...readAppliedOverrideMap() };
        
        // CRITICAL FIX: Don't try to clear siblings client-side!
        // The server API already handles "only one applied per jdHash" via:
        // UPDATE applications SET is_applied=false WHERE user_id=:uid AND jd_hash=:jd
        //
        // The old client-side clearSiblingsOfJdHash logic had a FATAL BUG:
        // - It used items.filter() which only has current page
        // - Siblings on other pages weren't found
        // - Their overrides stayed in storage
        // - But after fetchData(), server says isApplied=false
        // - Reconciliation didn't clean them up (we removed that)
        // - Result: Stale overrides accumulate and cause button disappearing
        //
        // SOLUTION: Remove client-side sibling clearing entirely
        // Server is source of truth for "which snapshot is applied"
        // Client overrides just track optimistic/confirmed state
        
        if (isApplied === null) {
          delete map[appliedKey];
        } else {
          map[appliedKey] = {
            isApplied: !!isApplied,
            optimistic: !!opts?.optimistic,
            updatedAt: Date.now(),
          };
        }
        persistAppliedOverrideMap(map);
      } catch {}
    },
    [] // Removed items dependency - we don't need it anymore
  );

  const fetchData = useCallback(
    async (
      targetPage: number,
      opts?: {
        silent?: boolean;
        searchOverride?: string;
        showAppliedOverride?: boolean;
        archivedOverride?: boolean;
        stagesOverride?: string | null | string;
      }
    ) => {
      if (!opts?.silent) setLoading(true);
      setError(null);
      abortActive();
      const controller = new AbortController();
      activeController.current = controller;
  const seq = ++requestSeq.current;
      const qSearch = (opts?.searchOverride ?? search) || undefined;
      const qApplied = (opts?.showAppliedOverride ?? showAppliedOnly) ? 1 : undefined;
      const stageCsv = Object.prototype.hasOwnProperty.call(opts ?? {}, "stagesOverride")
        ? (opts?.stagesOverride ?? "")
        : [stageFilter.interviewing ? "interviewing" : null, stageFilter.offer ? "offer" : null, stageFilter.hired ? "hired" : null]
            .filter(Boolean)
            .join(",");
      const qStages = stageCsv ? stageCsv : undefined;
      const qArchived = (opts?.archivedOverride ?? archivedTab) ? 1 : 0;
      try {
        const qSort: "actions" | "createdAt" | "jdSnippet" | undefined = sortBy ?? undefined;
        const qDir: "asc" | "desc" | undefined = sortBy ? sortDir ?? "asc" : undefined;
        let extraHeaders: Record<string, string> | undefined = undefined;
        try {
          const m = readJobIdMap();
          if (m && Object.keys(m).length > 0) {
            extraHeaders = { "X-RT-JobMap": encodeURIComponent(JSON.stringify(m)) };
          }
        } catch {}
        const data = await api.get<ApplicationListResponse>("/applications/list", {
          query: {
            page: targetPage,
            pageSize,
            search: qSearch,
            applied: qApplied,
            stages: qStages,
            archived: qArchived,
            sort: qSort,
            dir: qDir,
          },
          signal: controller.signal,
          headers: extraHeaders,
        });
        if (seq !== requestSeq.current) return;
        
        // DEBUG: Log raw server response
        console.log('[FETCH] Raw server response:', {
          totalItems: data.items?.length || 0,
          appliedCount: data.items?.filter(it => it.isApplied).length || 0,
          firstFewItems: data.items?.slice(0, 3).map(it => ({
            appliedKey: it.appliedKey,
            isApplied: it.isApplied,
            jdHash: it.jdHash
          }))
        });
        
        try {
          // SIMPLIFIED RECONCILIATION: Only clear pending states when server catches up
          // Overrides are PERMANENT user intent - never cleaned up here
          
          const pendingSnapshot = pendingStageRef.current;
          const resolvedPendingKeys: string[] = [];
          
          // Check which pending states have been confirmed by server
          for (const it of data.items || []) {
            const pending = pendingSnapshot[it.appliedKey];
            if (!pending) continue;
            
            const serverFlags = normalizeStageFlags({
              interviewing: it.interviewing,
              offer: it.offer,
              hired: it.hired,
            });
            
            const matchesPending =
              serverFlags.interviewing === pending.interviewing &&
              serverFlags.offer === pending.offer &&
              serverFlags.hired === pending.hired;
            
            if (matchesPending) {
              // Server caught up - clear pending state
              debugHistory("server caught up with pending mutation - clearing pending", { 
                appliedKey: it.appliedKey, 
                serverFlags 
              });
              resolvedPendingKeys.push(it.appliedKey);
            } else {
              // Server hasn't caught up yet - keep pending
              debugHistory("server not yet synced with pending - keeping pending", {
                appliedKey: it.appliedKey,
                serverFlags,
                pending,
              });
            }
          }
          
          // Clear resolved pending states
          if (resolvedPendingKeys.length) {
            debugHistory("clearing resolved pending stages", { keys: resolvedPendingKeys });
            resolvedPendingKeys.forEach((key) => setPendingStage(key, null));
          }
        } catch (err) {
          debugHistory("simple reconciliation error", { error: String(err) });
        }
        
        // CRITICAL: Reconcile Applied overrides ONLY on first fetch after page load/refresh
        // Page load: shouldReconcileOnFirstFetch=true (from window flag check)
        // Navigation: shouldReconcileOnFirstFetch=false (window flag already set)
        const shouldReconcile = shouldReconcileOnFirstFetch && !hasReconciledRef.current;
        if (shouldReconcile) {
          console.log('[FETCH] First fetch after page load/refresh - will reconcile Applied overrides');
          hasReconciledRef.current = true; // Only reconcile once per component instance
        }
        
        setItems(applyOverrides(data.items || [], shouldReconcile));
        setTotal(data.total || 0);
        setError(null);
      } catch (e: any) {
        if (controller.signal.aborted) return;
        setError("Failed to load.");
      } finally {
        if (seq === requestSeq.current) {
          if (!opts?.silent) setLoading(false);
        }
      }
    },
    [
      abortActive,
      applyOverrides,
      archivedTab,
      pageSize,
      search,
      showAppliedOnly,
      stageFilter,
      sortBy,
      sortDir,
      setPendingStage,
    ]
  );

  useEffect(() => () => abortActive(), [abortActive]);

  // DISABLED: This aggressive hydration causes button disappearance during navigation
  // The reconciliation logic in applyOverrides() handles staleness more conservatively
  // useEffect(() => {
  //   try {
  //     const srv = initialResponse?.items || [];
  //     if (!srv.length) return;
  //     const appliedMap = { ...readAppliedOverrideMap() };
  //     if (!appliedMap || Object.keys(appliedMap).length === 0) return;
  //     let changed = false;
  //     for (const it of srv) {
  //       if (Object.prototype.hasOwnProperty.call(appliedMap, it.appliedKey)) {
  //         const ov = !!appliedMap[it.appliedKey];
  //         if (ov !== !!it.isApplied) {
  //           delete appliedMap[it.appliedKey];
  //           changed = true;
  //         }
  //       }
  //     }
  //     if (changed) {
  //       persistAppliedOverrideMap(appliedMap);
  //       setItems(applyOverrides(srv));
  //     }
  //   } catch {}
  // }, [applyOverrides, initialResponse]);

  const pageSizeRef = pageSize; // keep for return clarity

  return {
    items,
    setItems,
    page,
    setPage,
    pageSize: pageSizeRef,
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
    markHistoryDirty,
    fetchData,
    writeFlagOverrides,
    writeAppliedOverride,
    writeAppliedOverridesMap,
    sortBy,
    setSortBy,
    sortDir,
    setSortDir,
    abortActive,
    pendingStage,
    setPendingStage,
  };
}
