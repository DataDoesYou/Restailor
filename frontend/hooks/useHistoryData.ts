import { useState, useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/api";
import { normalizeStageFlags, deriveStageLabel, StageFlagState, StageLabel } from "@/lib/stageFlags";
// STEAM-LIKE: Only job ID helpers remain, all override storage removed
import {
  readJobIdMap,
  readJobIdByHashes,
  writeJobId,
  readJobToken,
} from "@/lib/historyOverrides";
import { log as rtDebugLog, isRtDebug } from "@/lib/rtDebug";

// STEAM-LIKE: All optimistic override code removed - database is single source of truth
const debugHistory = (message: string, data?: Record<string, unknown>) => {
  // TEMPORARILY DISABLED - just return
  return;
  // try {
  //   rtDebugLog(`history::${message}`, data);
  // } catch {}
  // if (!DEBUG_HISTORY_OVERRIDES_CONSOLE) return;
  // try {
  //   // eslint-disable-next-line no-console
  //   console.debug("[history::overrides]", message, data ?? {});
  // } catch {}
};

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
  fetchData: (page: number, opts?: { silent?: boolean; searchOverride?: string; showAppliedOverride?: boolean; archivedOverride?: boolean; stagesOverride?: string | null | string }) => Promise<void>;
  sortBy: "actions" | "createdAt" | "jdSnippet" | null;
  setSortBy: React.Dispatch<React.SetStateAction<"actions" | "createdAt" | "jdSnippet" | null>>;
  sortDir: "asc" | "desc";
  setSortDir: React.Dispatch<React.SetStateAction<"asc" | "desc">>;
  abortActive: () => void;
  pendingStage: Record<string, StageFlagState>;
  setPendingStage: (appliedKey: string, next: StageFlagState | null) => void;
};

// STEAM-LIKE: No pending state storage - database only
// IOH buttons use React state for optimistic updates, just like Applied checkbox

export function useHistoryData(options: UseHistoryDataOptions): UseHistoryDataReturn {
  
  const router = useRouter();
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

  // STEAM-LIKE: Removed applyOverrides function - no longer needed
  // Database is the ONLY source of truth, no sessionStorage overlays

  // STEAM-LIKE: Pure database state, no pending overlays
  const applyDatabaseState = useCallback((list: ApplicationListItem[]): ApplicationListItem[] => {
    return list.map(it => attachStageMeta(it));
  }, []);

  const [items, setItems] = useState<ApplicationListItem[]>(() => {
    // If no SSR data, start empty and fetch on mount
    if (isRtDebug()) console.log('[useHistoryData] initialResponse:', initialResponse ? 'has data' : 'null - will fetch');
    return (initialResponse?.items || []).map(it => attachStageMeta(it));
  });
  
  const [page, setPage] = useState(initialPage);
  const [total, setTotal] = useState(initialResponse?.total || 0);
  const [loading, setLoading] = useState(initialResponse === null); // Start loading if no initial data
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState(initialSearch);
  const [searchInput, setSearchInput] = useState(initialSearch);
  const [showAppliedOnly, setShowAppliedOnly] = useState(initialShowAppliedOnly);
  const [archivedTab, setArchivedTab] = useState(initialArchived);
  const [sortBy, setSortBy] = useState<"actions" | "createdAt" | "jdSnippet" | null>(initialSortBy || null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">(initialSortDir || "desc");
  const [stageFilter, setStageFilter] = useState<{ interviewing: boolean; offer: boolean; hired: boolean }>(
    initialStageFilter || { interviewing: false, offer: false, hired: false }
  );
  const [deleting, setDeleting] = useState<Record<string, boolean>>({});
  const [pendingStageMap, setPendingStageMap] = useState<Record<string, StageFlagState>>({});
  
  const activeController = useRef<AbortController | null>(null);
  const requestSeq = useRef(0);
  const itemsRef = useRef(items);
  itemsRef.current = items;
  
  const pageSize = initialPageSize;

  // STEAM-LIKE: React state only, NO sessionStorage writes
  const setPendingStage = useCallback((appliedKey: string, next: StageFlagState | null) => {
    setPendingStageMap((prev) => {
      if (!next) {
        if (!prev[appliedKey]) {
          return prev;
        }
        const cloned = { ...prev };
        delete cloned[appliedKey];
        // NO sessionStorage write - pure React state
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
      // NO sessionStorage write - pure React state
      return updated;
    });
  }, []);

  const abortActive = useCallback(() => {
    try {
      activeController.current?.abort();
    } catch {}
    activeController.current = null;
  }, []);

  // All cookie/override writes removed - database is single source of truth

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

      try {
        const searchVal = opts?.searchOverride !== undefined ? opts.searchOverride : search;
        const showApplied = opts?.showAppliedOverride !== undefined ? opts.showAppliedOverride : showAppliedOnly;
        const archivedVal = opts?.archivedOverride !== undefined ? opts.archivedOverride : archivedTab;
        
        const params = new URLSearchParams();
        params.set("page", String(targetPage));
        params.set("pageSize", String(pageSize));
        if (searchVal.trim()) params.set("search", searchVal);
        // Explicitly set applied parameter (not just when true)
        params.set("applied", showApplied ? "true" : "false");
        if (archivedVal) params.set("archived", "true");
        if (sortBy) params.set("sortBy", sortBy);
        if (sortDir) params.set("sortDir", sortDir);
        // Add cache-busting parameter when doing silent refresh (after stage update)
        if (opts?.silent) params.set("_t", String(Date.now()));
        
        // DEBUG: Log what we're sending
        if (isRtDebug()) console.log('[fetchData] Query params:', {
          showApplied,
          showAppliedOverride: opts?.showAppliedOverride,
          archivedVal,
          archivedOverride: opts?.archivedOverride,
          finalParams: params.toString()
        });
        
        // Stage filters
        if (opts?.stagesOverride !== undefined && opts.stagesOverride !== null) {
          if (opts.stagesOverride) {
            params.set("stages", opts.stagesOverride);
          }
        } else {
          const stages: string[] = [];
          if (stageFilter.interviewing) stages.push("interviewing");
          if (stageFilter.offer) stages.push("offer");
          if (stageFilter.hired) stages.push("hired");
          if (stages.length > 0) {
            params.set("stages", stages.join(","));
          }
        }

        const res = await api.get<ApplicationListResponse>(`/applications/list`, {
          query: Object.fromEntries(params.entries()),
          signal: controller.signal,
        });

        if (isRtDebug()) console.log('[fetchData] API Response:', {
          itemCount: res.items?.length ?? 0,
          appliedKeys: res.items?.map(it => ({ key: it.appliedKey, applied: it.isApplied })) ?? []
        });

        if (seq !== requestSeq.current) {
          return;
        }

        // STEAM-LIKE: Pure database state, no overlays
        const freshItems = applyDatabaseState(res.items || []);
        
        if (isRtDebug()) console.log(`[fetchData] Received ${freshItems.length} items from API. First item:`, {
          appliedKey: freshItems[0]?.appliedKey?.substring(0, 30),
          isApplied: freshItems[0]?.isApplied,
          interviewing: freshItems[0]?.interviewing,
          offer: freshItems[0]?.offer,
          hired: freshItems[0]?.hired,
        });
        // Force new array reference to ensure React detects the change
        setItems([...freshItems]);
        setTotal(res.total || 0);
        setPage(targetPage);
        setError(null);
      } catch (err: any) {
        if (seq !== requestSeq.current) {
          return;
        }
        if (err?.name === "AbortError" || err?.cause?.name === "AbortError") {
          return;
        }
        const message = err?.message || String(err);
        setError(message);
      } finally {
        if (seq === requestSeq.current) {
          setLoading(false);
        }
      }
    },
    [
      search,
      showAppliedOnly,
      archivedTab,
      sortBy,
      sortDir,
      stageFilter,
      pageSize,
      abortActive,
      applyDatabaseState,
    ]
  );

  // Fetch on mount if no initial data (client-side only mode)
  useEffect(() => {
    if (initialResponse === null) {
      if (isRtDebug()) console.log('[useHistoryData] No SSR data, establishing auth then fetching');
      // Establish auth first, then fetch data
      import('@/lib/api').then(({ api }) => {
        // Trigger auth establishment by calling /users/me
        api.get('/users/me').then(() => {
          if (isRtDebug()) console.log('[useHistoryData] Auth established, now fetching data');
          fetchData(page);
        }).catch((err) => {
          // Ignore "Auth probe deferred" - it's intentional behavior, not an error
          const message = err?.message || String(err);
          if (message.includes('Auth probe deferred') || message.includes('Auth not established')) {
            if (isRtDebug()) console.log('[useHistoryData] Auth probe deferred, will retry on user interaction');
            setLoading(false);
            return;
          }
          console.error('[useHistoryData] Auth failed:', err);
          setError(message || 'Authentication required');
          setLoading(false);
        });
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount

  // Debounced search
  useEffect(() => {
    const id = setTimeout(() => {
      if (searchInput !== search) {
        setSearch(searchInput);
        fetchData(1, { searchOverride: searchInput });
      }
    }, 300);
    return () => clearTimeout(id);
  }, [searchInput, search, fetchData]);

  // Only refetch when page becomes visible (e.g., coming back from another tab)
  // This keeps SSR data intact on initial load
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        if (isRtDebug()) console.log('[HISTORY VISIBILITY] Page visible - fetching latest data');
        try {
          const url = new URL(window.location.href);
          const rawStages = url.searchParams.get('stages') || '';
          const csv = rawStages || [
            stageFilter.interviewing ? 'interviewing' : null,
            stageFilter.offer ? 'offer' : null,
            stageFilter.hired ? 'hired' : null,
          ].filter(Boolean).join(',');
          fetchData(page, { stagesOverride: csv, silent: true });
        } catch {
          fetchData(page, { silent: true });
        }
      }
    };

    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', handleVisibilityChange);
    }

    return () => {
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', handleVisibilityChange);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // No pathname detection needed - mount effect always fetches fresh data

  return {
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
    abortActive,
    pendingStage: pendingStageMap,
    setPendingStage,
  };
}
