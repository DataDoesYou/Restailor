"use client";

import { useEffect, useMemo, useRef, useState, useCallback, useLayoutEffect } from "react";
import type { Dispatch, SetStateAction } from "react";
import { flushSync } from "react-dom";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { isRtDebug, log, getNavId } from "@/lib/rtDebug";
import api, { ApiError, getApiBaseUrl } from "@/lib/api";
// Batch (multi-model) hook & banner (FIT phase wiring only per prompt)
import useBatchPhase from "@/hooks/useBatchPhase";
// BatchStatusBanner removed: consolidate UI into existing single-phase spinner rows & buttons.
import { getClientId } from "@/lib/client";
import useSSE from "@/lib/sse";
import Markdown from "@/components/resume/Markdown";
import { useSharedInputs } from "@/components/resume/inputStore";
import { useSharedOutputs } from "@/components/resume/outputStore";
import { DISPLAY_OPTIONS, MODEL_REGISTRY, JUDGE_OPTIONS, RESUME_STATS_KEY, RESUME_STATS_TS_KEY, MODEL_OPTIONS } from "@/components/resume/models";
import apiClient from "@/lib/api";
import Tooltip from "@/components/ui/Tooltip";
import Disclosure from "@/components/ui/Disclosure";
import { normalizeText, makeAppliedKey, makeJdHash, stableHash } from "@/app/lib/hash";
// Model settings for self-contained job submissions
import { useModelSettings } from "@/hooks/useModelSettings";
import { effectiveSelected } from "@/lib/modelSelectionAdapter";
// STEAM-LIKE: Database is single source of truth, no cookie/storage helpers needed


type Alert = { kind: "info" | "success" | "warning" | "error"; text: string } | null;
type ResumeRunDebugEvent = { iso: string; relMs: number; name: string; data?: Record<string, unknown> };

type Props = { initialLoggedIn?: boolean; initialAuthVerified?: boolean; initialApplied?: boolean; initialJudgeLabel?: string; initialResultType?: string; initialStatsMd?: string; initialFitOutput?: string; initialTailoredOutput?: string; initialJudgeOutput?: string; initialSnapshotLoaded?: boolean; initialResumeText?: string; initialJdText?: string; initialAppliedBanner?: string; initialTrialUsd?: string; initialFreeReqHint?: number; __seedDebug?: any };

function clipDebugData(data: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
	if (!data) return undefined;
	try {
		return JSON.parse(JSON.stringify(data, (_key, value) => {
			if (typeof value === "string" && value.length > 220) return `${value.slice(0, 220)}...`;
			return value;
		}));
	} catch {
		return { unserializable: true };
	}
}

function ResumeRunDebugOverlay({
	events,
	setEvents,
}: {
	events: ResumeRunDebugEvent[];
	setEvents: Dispatch<SetStateAction<ResumeRunDebugEvent[]>>;
}) {
	const [minimized, setMinimized] = useState(true);
	const copyText = useMemo(() => {
		return events.map((event) => {
			const payload = event.data ? ` ${JSON.stringify(event.data)}` : "";
			return `${event.iso} +${event.relMs}ms ${event.name}${payload}`;
		}).join("\n");
	}, [events]);

	return (
		<div
			style={{
				position: "fixed",
				right: 12,
				bottom: 12,
				zIndex: 100000,
				width: minimized ? 230 : "min(760px, calc(100vw - 24px))",
				maxHeight: minimized ? 44 : "min(540px, calc(100vh - 24px))",
				overflow: "hidden",
				border: "1px solid rgba(148, 163, 184, 0.45)",
				borderRadius: 8,
				background: "rgba(2, 6, 23, 0.94)",
				boxShadow: "0 18px 60px rgba(0,0,0,0.4)",
				color: "#dbeafe",
				fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
				fontSize: 11,
			}}
		>
			<div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", borderBottom: minimized ? 0 : "1px solid rgba(148, 163, 184, 0.25)" }}>
				<strong style={{ color: "#93c5fd", marginRight: "auto" }}>Resume Run Debug</strong>
				<button type="button" onClick={() => navigator.clipboard?.writeText(copyText).catch(() => {})} style={{ color: "#bfdbfe", background: "rgba(30, 41, 59, 0.9)", border: "1px solid rgba(148, 163, 184, 0.4)", borderRadius: 6, padding: "3px 8px" }}>copy</button>
				<button type="button" onClick={() => setEvents([])} style={{ color: "#bfdbfe", background: "transparent", border: "1px solid rgba(148, 163, 184, 0.35)", borderRadius: 6, padding: "3px 8px" }}>clear</button>
				<button type="button" onClick={() => setMinimized((value) => !value)} style={{ color: "#bfdbfe", background: "transparent", border: "1px solid rgba(148, 163, 184, 0.35)", borderRadius: 6, padding: "3px 8px" }}>{minimized ? "maximize" : "minimize"}</button>
			</div>
			{!minimized ? (
				<div style={{ maxHeight: 490, overflow: "auto", padding: 10 }}>
					{events.length === 0 ? (
						<div style={{ color: "#94a3b8" }}>Waiting for submit events...</div>
					) : events.map((event, index) => (
						<div key={`${event.iso}-${index}`} style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", paddingBottom: 4 }}>
							<span style={{ color: "#38bdf8" }}>{event.iso}</span>{" "}
							<span style={{ color: "#fbbf24" }}>+{event.relMs}ms</span>{" "}
							<span style={{ color: "#86efac" }}>{event.name}</span>
							{event.data ? <span style={{ color: "#cbd5e1" }}> {JSON.stringify(event.data)}</span> : null}
						</div>
					))}
				</div>
			) : null}
		</div>
	);
}

function submission402Message(err?: ApiError): string {
	const detail = typeof err?.detail === "string" ? err.detail : String((err?.detail as any)?.detail || "");
	if (detail === "missing_byok_key") {
		return "Missing provider API key. Add your BYOK key in Settings before running a model.";
	}
	return "Insufficient Budget credits. Add Budget credits before running a model.";
}

async function getLocalByokKey(provider: string): Promise<string | null> {
	if (typeof window === "undefined") return null;
	const stored = localStorage.getItem(`rt_byok_local_${provider}`);
	if (!stored) return null;
	const payload = JSON.parse(stored);
	const cryptoKey = await new Promise<CryptoKey | null>((resolve) => {
		const open = indexedDB.open("restailor-byok", 1);
		open.onerror = () => resolve(null);
		open.onsuccess = () => {
			const tx = open.result.transaction("keys", "readonly");
			const req = tx.objectStore("keys").get(provider);
			req.onsuccess = () => resolve((req.result as CryptoKey) || null);
			req.onerror = () => resolve(null);
		};
	});
	if (!cryptoKey) return null;
	const plain = await crypto.subtle.decrypt(
		{ name: "AES-GCM", iv: new Uint8Array(payload.iv || []) },
		cryptoKey,
		new Uint8Array(payload.cipher || []),
	);
	return new TextDecoder().decode(plain);
}

export default function ResumeTailorClient({ initialLoggedIn, initialAuthVerified, initialApplied, initialJudgeLabel, initialResultType, initialStatsMd, initialFitOutput, initialTailoredOutput, initialJudgeOutput, initialSnapshotLoaded, initialResumeText, initialJdText, initialAppliedBanner, initialTrialUsd, initialFreeReqHint, __seedDebug }: Props) {
	if (isRtDebug()) console.log('[ResumeTailorClient] Component mounting/rendering');
	const router = useRouter();
	const pathname = usePathname();
	const searchParams = useSearchParams();
	const [rtDebugEnabled, setRtDebugEnabled] = useState(false);
	const debugStartedAtRef = useRef(0);
	const [runDebugEvents, setRunDebugEvents] = useState<ResumeRunDebugEvent[]>([]);
	const addRunDebugEvent = useCallback((name: string, data?: Record<string, unknown>) => {
		if (!isRtDebug()) return;
		const now = typeof performance !== "undefined" ? performance.now() : Date.now();
		const startedAt = debugStartedAtRef.current || now;
		debugStartedAtRef.current = startedAt;
		setRunDebugEvents((prev) => [...prev.slice(-249), {
			iso: new Date().toISOString(),
			relMs: Math.round(now - startedAt),
			name,
			data: clipDebugData(data),
		}]);
	}, []);

	useEffect(() => {
		setRtDebugEnabled(isRtDebug());
		addRunDebugEvent("overlay.mounted", {
			pathname: window.location.pathname,
			search: window.location.search,
			apiBaseUrl: getApiBaseUrl(),
			initialLoggedIn,
			initialAuthVerified,
		});
	}, [addRunDebugEvent, initialAuthVerified, initialLoggedIn]);
	
	// 🔍 PAGE RELOAD DETECTION - Track double-loading issues
	const [reloadDiagnostic, setReloadDiagnostic] = useState<{
		showWarning: boolean;
		loadCount: number;
		loadTimestamps: number[];
		diagnostics: string[];
	} | null>(null);
	
	// Feature flag for reload detection (disabled by default, no config fetch needed)
	// To enable, set NEXT_PUBLIC_RELOAD_DETECTION=1 in env
	const enableReloadDetection = typeof process !== 'undefined' && 
		process.env.NEXT_PUBLIC_RELOAD_DETECTION === '1';
	
	useEffect(() => {
		// Skip if detection is disabled
		if (!enableReloadDetection) {
			return;
		}
		
		// Initialize or retrieve reload tracking from sessionStorage
		const RELOAD_KEY = '__rt_reload_tracking';
		const now = Date.now();
		
		// Skip detection on home page - only detect on /resume
		if (typeof window !== 'undefined' && window.location.pathname !== '/resume') {
			return;
		}
		
		try {
			// Get existing tracking data
			let tracking = JSON.parse(sessionStorage.getItem(RELOAD_KEY) || 'null') as {
				loadCount: number;
				loadTimestamps: number[];
				firstLoadTime: number;
				lastResetTime: number;
				userAgent: string;
				referrer: string;
				navigationEntries: any[];
			} | null;
			
			// Clear tracking if it's been more than 10 seconds since first load (prevents false positives from normal navigation)
			if (tracking && (now - tracking.firstLoadTime) > 10000) {
				tracking = null;
				sessionStorage.removeItem(RELOAD_KEY);
			}
			
			// ALSO clear if it's been more than 1 second since LAST load (new visit)
			if (tracking && tracking.loadTimestamps.length > 0) {
				const timeSinceLastLoad = now - tracking.loadTimestamps[tracking.loadTimestamps.length - 1];
				if (timeSinceLastLoad > 1000) {
					tracking = null;
					sessionStorage.removeItem(RELOAD_KEY);
				}
			}
			
			// Initialize or increment tracking
			if (!tracking) {
				tracking = {
					loadCount: 1,
					loadTimestamps: [now],
					firstLoadTime: now,
					lastResetTime: now,
					userAgent: navigator.userAgent,
					referrer: document.referrer,
					navigationEntries: []
				};
			} else {
				tracking.loadCount += 1;
				tracking.loadTimestamps.push(now);
				const gap = now - tracking.loadTimestamps[tracking.loadTimestamps.length - 2];
				console.warn(`🟡 [LOAD TRACKING] Load #${tracking.loadCount} detected (+${gap}ms from previous)`, {
					loadCount: tracking.loadCount,
					gap: `${gap}ms`,
					totalTime: `${now - tracking.firstLoadTime}ms`
				});
			}
			
			// Collect navigation performance data
			if (performance && performance.getEntriesByType) {
				const navEntries = performance.getEntriesByType('navigation') as PerformanceNavigationTiming[];
				if (navEntries.length > 0) {
					const nav = navEntries[0];
					tracking.navigationEntries.push({
						type: nav.type,
						redirectCount: nav.redirectCount,
						timestamp: now,
						loadEventEnd: nav.loadEventEnd,
						domContentLoadedEventEnd: nav.domContentLoadedEventEnd,
						transferSize: nav.transferSize
					});
				}
			}
			
			// Save updated tracking
			sessionStorage.setItem(RELOAD_KEY, JSON.stringify(tracking));
			
			// Check if this is a double-load scenario
			// ONLY detect if within first 1 second and multiple rapid loads
			const timeSinceFirst = now - tracking.firstLoadTime;
			
			// Only check for double load if we're within the initial load window (1 second)
			if (timeSinceFirst > 1000) {
				// Too old, ignore (this is normal navigation back to page)
				sessionStorage.removeItem(RELOAD_KEY);
				return;
			}
			
			// Count reloads that happen within 1 second of each other
			let rapidReloadCount = 0;
			for (let i = 1; i < tracking.loadTimestamps.length; i++) {
				const gap = tracking.loadTimestamps[i] - tracking.loadTimestamps[i - 1];
				if (gap < 1000) {
					rapidReloadCount++;
				}
			}
			
			// In development, React StrictMode causes double-mounting with tiny gaps (<10ms)
			// This is expected and not a real issue - only warn if gap is meaningful
			const isDevelopment = process.env.NODE_ENV === 'development';
			const hasVeryTinyGap = tracking.loadTimestamps.length >= 2 && 
				tracking.loadTimestamps.slice(1).every((t, i) => (t - tracking.loadTimestamps[i]) < 10);
			
			// Skip detection if this looks like StrictMode double-mounting
			if (isDevelopment && hasVeryTinyGap && tracking.loadCount === 2) {
				return;
			}
			
			// Trigger if any rapid reloads detected (but not StrictMode)
			const isDoubleLoad = rapidReloadCount > 0;
			
			if (isDoubleLoad) {
				// Add detection reason to diagnostics
				const detectionReasons: string[] = [];
				
				// List all gaps that were < 1 second
				const rapidGaps: number[] = [];
				for (let i = 1; i < tracking.loadTimestamps.length; i++) {
					const gap = tracking.loadTimestamps[i] - tracking.loadTimestamps[i - 1];
					if (gap < 1000) {
						rapidGaps.push(gap);
					}
				}
				
				detectionReasons.push(`Found ${rapidReloadCount} rapid reload(s) with gaps < 1 second`);
				detectionReasons.push(`Rapid gaps: ${rapidGaps.map(g => `${g}ms`).join(', ')}`);
				
				console.error('🚨 [DOUBLE LOAD DETECTED]', {
					loadCount: tracking.loadCount,
					timeSinceFirst: `${timeSinceFirst}ms`,
					timestamps: tracking.loadTimestamps,
					rapidReloadCount,
					rapidGaps,
					detectionReasons,
					tracking
				});
				
				// Build diagnostic message
				const diagnostics: string[] = [];
				diagnostics.push(`🔴 DETECTION REASONS:`);
				detectionReasons.forEach(reason => diagnostics.push(`  • ${reason}`));
				diagnostics.push(``);
				diagnostics.push(`Total loads: ${tracking.loadCount}`);
				diagnostics.push(`Rapid reloads (< 1s gap): ${rapidReloadCount}`);
				diagnostics.push(`Time since first load: ${timeSinceFirst}ms`);
				diagnostics.push(`Referrer: ${tracking.referrer || 'none'}`);
				
				// Analyze timing between loads
				if (tracking.loadTimestamps.length >= 2) {
					const gaps = tracking.loadTimestamps.slice(1).map((t, i) => 
						t - tracking.loadTimestamps[i]
					);
					diagnostics.push(`Load gaps: ${gaps.map(g => `${g}ms`).join(', ')}`);
				}
				
				// Analyze navigation type
				if (tracking.navigationEntries.length > 0) {
					const navTypes = tracking.navigationEntries.map(e => e.type);
					diagnostics.push(`Navigation types: ${navTypes.join(', ')}`);
					
					// Check for suspicious patterns
					if (navTypes.includes('reload')) {
						diagnostics.push('⚠️ Browser reload detected');
					}
					if (tracking.navigationEntries.some(e => e.redirectCount > 0)) {
						diagnostics.push('⚠️ Redirects detected');
					}
				}
				
				// Check URL parameters
				const params = new URLSearchParams(window.location.search);
				if (params.has('appliedKey')) {
					diagnostics.push(`URL param: appliedKey=${params.get('appliedKey')}`);
				}
				if (params.has('forceApplied')) {
					diagnostics.push(`URL param: forceApplied=${params.get('forceApplied')}`);
				}
				
				// Check authentication state
				diagnostics.push(`Auth: initialLoggedIn=${initialLoggedIn}, initialAuthVerified=${initialAuthVerified}`);
				
				// Check React strict mode (common cause of double-mounting in dev)
				if (process.env.NODE_ENV === 'development') {
					diagnostics.push('⚠️ Running in DEVELOPMENT mode (React StrictMode may cause double-mounting)');
				}
				
				setReloadDiagnostic({
					showWarning: true,
					loadCount: tracking.loadCount,
					loadTimestamps: tracking.loadTimestamps,
					diagnostics
				});
			}
			
		} catch (err) {
			console.error('[RELOAD DETECTION] Error:', err);
		}
	}, [enableReloadDetection]); // Re-run if feature flag changes
	
	// Client id is only meaningful on the client; during SSR this will be empty.
	const [xClient, setXClient] = useState<string>("");
	useEffect(() => { try { setXClient(getClientId()); } catch {} }, []);

	// Load model settings for self-contained job submissions
	// This ensures each job includes explicit resolved model lists for reproducibility
	const { settings: modelSettings, isLoading: modelSettingsLoading } = useModelSettings();
	useEffect(() => {
		if (isRtDebug()) console.log('[ResumeTailorClient] Component mounted');
		
		// CRITICAL: STEAM-LIKE navigation blocking
		// Block browser navigation (tab close, refresh, external links) while mutations are in progress
		const handleBeforeUnload = (e: BeforeUnloadEvent) => {
			if ((window as any).__rt_mutation_in_progress) {
				console.warn('[NAVIGATION GUARD] 🚫 Blocked browser navigation - database update in progress');
				e.preventDefault();
				e.returnValue = ''; // Chrome requires returnValue to be set
				return ''; // Some browsers show this message
			}
		};
		
		// STEAM APPROACH: Block ALL link clicks during mutations (capture phase)
		// This makes the UI feel "locked" for 50-100ms while request completes - exactly like Steam
		const handleClick = (e: MouseEvent) => {
			if ((window as any).__rt_mutation_in_progress) {
				const target = e.target as HTMLElement;
				// Check if click is on a link or inside a link
				const link = target.closest('a[href], button[type="button"]');
				if (link) {
					e.preventDefault();
					e.stopPropagation();
					e.stopImmediatePropagation();
					console.warn('[NAVIGATION GUARD] 🚫 Blocked link click - database update in progress');
					
					// Optional: Show visual feedback
					const banner = document.querySelector('[class*="applied-banner"]') as HTMLElement;
					if (banner) {
						const originalText = banner.textContent;
						banner.textContent = 'Saving to database...';
						banner.style.color = '#f59e0b';  // amber
						setTimeout(() => {
							banner.textContent = originalText || '';
							banner.style.color = '';
						}, 500);
					}
				}
			}
		};
		
		window.addEventListener('beforeunload', handleBeforeUnload);
		document.addEventListener('click', handleClick, true);  // Capture phase = runs before Link onClick
		
		if (isRtDebug()) console.log('[ResumeTailorClient] Navigation guard installed (browser + client-side)');
		
		return () => {
			if (isRtDebug()) console.log('[ResumeTailorClient] Component unmounting');
			window.removeEventListener('beforeunload', handleBeforeUnload);
			document.removeEventListener('click', handleClick, true);
			if (isRtDebug()) console.log('[ResumeTailorClient] Navigation guard removed');
		};
	}, []);
	// useEffect(() => {
	// 	if (!isRtDebug()) return;
	// 	let appliedKey: string | undefined = undefined; let forceApplied = false;
	// 	try { const sp = new URLSearchParams(window.location.search); appliedKey = sp.get('appliedKey') || undefined; forceApplied = sp.get('forceApplied') === '1'; } catch {}
	// 	log('SSR.SEED', {
	// 		initialApplied,
	// 		initialResultType,
	// 		initialStatsMd: !!initialStatsMd,
	// 		hasFit: !!initialFitOutput,
	// 		hasTailor: !!initialTailoredOutput,
	// 		hasJudge: !!initialJudgeOutput,
	// 		initialSnapshotLoaded,
	// 		appliedKeyParam: appliedKey ?? __seedDebug?.appliedKeyParam,
	// 		forceAppliedParam: typeof forceApplied === 'boolean' ? forceApplied : !!__seedDebug?.forceAppliedParam,
	// 		cookies: __seedDebug?.cookies,
	// 		viewParam: __seedDebug?.viewParam,
	// 		navId: getNavId(),
	// 	});
	// }, []);

    // Debug logging removed

	// Inputs (shared across pages, persisted locally and to server)
	const { resumeText, setResumeText, jdText, setJdText } = useSharedInputs({ 
		initialResume: initialResumeText, 
		initialJd: initialJdText 
	});
	// Per-phase model selections - load from DB, no localStorage
	// Start with empty string to indicate no selection (will be populated from DB or remain empty)
	const [fitModelLabel, setFitModelLabel] = useState<string>("");
	const [tailorModelLabel, setTailorModelLabel] = useState<string>("");
	// Re-enable judge selection UI (needed to choose non-default judge model)
	const showJudge = true;
	const [judgeLabel, setJudgeLabel] = useState<string>("");

	// Load model selections from database on mount
	useEffect(() => {
		const loadModelSettings = async () => {
			try {
				const resp = await api.get<any>("/users/me/model-settings");
				const settings = resp.settings || resp;
				
				// Helper to convert model_id to legacy label format
				const toLegacyLabel = (modelId: string | null | undefined, isJudge: boolean = false) => {
					if (!modelId) return null;
					const opt = MODEL_OPTIONS.find(m => m.model_id === modelId);
					if (!opt) return null;
					return isJudge 
						? `${opt.alias} — ${opt.provider_display}`
						: `${opt.alias} — ${opt.provider_display} (${opt.description})`;
				};
				
				// Load single-model selections
				const fitLabel = toLegacyLabel(settings.last_single_fit);
				const tailorLabel = toLegacyLabel(settings.last_single_tailor);
				const judgeLabel = toLegacyLabel(settings.last_single_judge, true);
				
				if (fitLabel) setFitModelLabel(fitLabel);
				if (tailorLabel) setTailorModelLabel(tailorLabel);
				if (judgeLabel) setJudgeLabel(judgeLabel);
				
				if (isRtDebug()) console.log('[ResumeTailorClient] Loaded model settings from DB:', { fitLabel, tailorLabel, judgeLabel });
			} catch (e) {
				// Suppress all pre-login auth errors silently
				if (e instanceof Error && 
				    !e.message.includes("Auth not established") && 
				    e.message !== "Could not validate credentials") {
					console.error('[ResumeTailorClient] Failed to load model settings:', e);
				}
			}
		};
		loadModelSettings();
	}, []);

	useEffect(() => {
		const onSidebar = (e: Event) => {
			const d = (e as CustomEvent).detail || {};
			if (isRtDebug()) console.log('[ResumeTailorClient] rt-sidebar event received:', d);
			if (typeof d.judgeLabel === 'string') {
				if (isRtDebug()) console.log('[ResumeTailorClient] Setting judgeLabel to:', d.judgeLabel);
				setJudgeLabel(d.judgeLabel);
			}
			// Accept empty string (no model selected) or valid label from DISPLAY_OPTIONS
			if (typeof d.fitModelLabel === 'string' && (d.fitModelLabel === '' || DISPLAY_OPTIONS.some(o=>o.label===d.fitModelLabel))) {
				if (isRtDebug()) console.log('[ResumeTailorClient] Setting fitModelLabel to:', d.fitModelLabel);
				setFitModelLabel(d.fitModelLabel);
			}
			// Accept empty string (no model selected) or valid label from DISPLAY_OPTIONS
			if (typeof d.tailorModelLabel === 'string' && (d.tailorModelLabel === '' || DISPLAY_OPTIONS.some(o=>o.label===d.tailorModelLabel))) {
				if (isRtDebug()) console.log('[ResumeTailorClient] Setting tailorModelLabel to:', d.tailorModelLabel);
				setTailorModelLabel(d.tailorModelLabel);
			}
		};
		window.addEventListener('rt-sidebar', onSidebar as EventListener);
		
		// Request current sidebar state on mount
		if (isRtDebug()) console.log('[ResumeTailorClient] Requesting sidebar state...');
		window.dispatchEvent(new CustomEvent('rt-sidebar-request'));
		
		return () => window.removeEventListener('rt-sidebar', onSidebar as EventListener);
	}, []);

	// Running state
	const [fitRequested, setFitRequested] = useState(false);
	const fitRequestedRef = useRef(fitRequested); useEffect(() => { fitRequestedRef.current = fitRequested; }, [fitRequested]);

	const [tailorRequested, setTailorRequested] = useState<boolean>(false);
	const tailorRequestedRef = useRef(tailorRequested); useEffect(() => { tailorRequestedRef.current = tailorRequested; }, [tailorRequested]);

	const [awaitingJudge, setAwaitingJudge] = useState(false);
	const awaitingJudgeRef = useRef(awaitingJudge); useEffect(() => { awaitingJudgeRef.current = awaitingJudge; }, [awaitingJudge]);

	const [judgeRequested, setJudgeRequested] = useState(false);
	const judgeRequestedRef = useRef(judgeRequested); useEffect(() => { judgeRequestedRef.current = judgeRequested; }, [judgeRequested]);
	// Active multi-batch phase (fit|tailor|judge) or null
	const [batchPhase, setBatchPhase] = useState<"fit"|"tailor"|"judge"|null>(null);
	// Optimistic UI state - set immediately on button click
	const [optimisticRunning, setOptimisticRunning] = useState<'fit' | 'tailor' | 'judge' | null>(null);
	const optimisticRunningRef = useRef(optimisticRunning); useEffect(() => { optimisticRunningRef.current = optimisticRunning; }, [optimisticRunning]);
	// Suppress any late snapshot/LS reconcile that might repopulate cleared outputs when a new run starts
	const suppressRefillUntilRef = useRef<number>(0);

	// Timing + stats (ported style from benchmark) – now cumulative across phases until JD changes
	const phaseTimesRef = useRef<{ fit?: { start: number; end?: number; model?: string }; tailor?: { start: number; end?: number; model?: string }; judge?: { start: number; end?: number; model?: string } }>({});
	// Accumulated completed phase times (secs + model label at time of run)
	const accumulatedTimesRef = useRef<{ fit?: { secs: number; model: string }; tailor?: { secs: number; model: string }; judge?: { secs: number; model: string } }>({});
	// When the JD changes we defer clearing accumulated totals until the next run actually starts
	const pendingAccumResetRef = useRef<boolean>(false);
	// Track JD snapshot used for accumulated times; if user edits JD we reset accumulated stats
	const lastJdSnapshotRef = useRef<string>("");
	// Stats markdown (SSR seeded to prevent flicker if provided)
	const [statsMd, setStatsMd] = useState<string>(() => initialStatsMd || "");
	const statsTsRef = useRef<number>(0);
	const [tick, setTick] = useState(0); // force re-render for elapsed timers
	const somethingRunning = fitRequested || !!tailorRequested || awaitingJudge || judgeRequested;
	useEffect(() => {
		if (!somethingRunning) return;
		const id = window.setInterval(() => setTick((t) => t + 1), 1000);
		return () => { clearInterval(id); };
	}, [somethingRunning]);
	function fmtElapsedWhole(secs: number): string {
		if (!isFinite(secs) || secs < 0) secs = 0;
		if (secs < 60) return `${Math.floor(secs)}s`;
		const m = Math.floor(secs / 60);
		const s = Math.floor(secs - m * 60);
		return `${m}m ${String(s).padStart(2, "0")}s`;
	}

	// Parse durations like "45s" or "1m 05s" back into seconds
	function parseElapsed(text: string): number | null {
		if (!text) return null;
		try {
			// Accept forms: "12s", "1m 2s", "1m 02s"
			const m = text.trim().match(/^(?:(\d+)m\s*)?(\d+)?s$/i);
			if (!m) return null;
			const mins = m[1] ? Number(m[1]) : 0;
			const secs = m[2] ? Number(m[2]) : 0;
			if (Number.isNaN(mins) || Number.isNaN(secs)) return null;
			return mins * 60 + secs;
		} catch { return null; }
	}

	// Recompute stats markdown from accumulated times (used to clear a phase on new run start)
	const recomputeStatsFromAccum = useCallback(() => {
		try {
			const acc = accumulatedTimesRef.current || {} as any;
			const total = [acc.fit?.secs, acc.tailor?.secs, acc.judge?.secs].filter((v: any) => typeof v === 'number') as number[];
			const totalSum = total.reduce((a,b)=>a+b,0);
			const lines: string[] = [];
		if (totalSum > 0) lines.push(`**Total time:** ${fmtElapsedWhole(totalSum)}`);
		if (acc.fit) lines.push(`Fit time (${acc.fit.model}): ${fmtElapsedWhole(acc.fit.secs)}`);
		if (acc.tailor) lines.push(`Tailor time (${acc.tailor.model}): ${fmtElapsedWhole(acc.tailor.secs)}`);
		if (acc.judge) lines.push(`Judge time (${acc.judge.model}): ${fmtElapsedWhole(acc.judge.secs)}`);
		const newStats = lines.join("  \n");
		setStatsMd(newStats);
	} catch {}
}, []);	function rebuildAccumulatorFromStats(md: string | null | undefined) {
		if (!md) return;
		try {
			// If already hydrated don't overwrite (user might have newer in-memory totals)
			const existing = accumulatedTimesRef.current;
			if (existing && (existing.fit || existing.tailor || existing.judge)) return;
			const lines = md.split(/\r?\n/).map(l=>l.trim()).filter(Boolean);
			const acc: any = {};
		for (const line of lines) {
			let m = line.match(/^Fit time \(([^)]+)\):\s+(.+)$/i);
			if (m) { const secs = parseElapsed(m[2]); if (secs!=null) acc.fit = { secs, model: m[1] }; continue; }
			m = line.match(/^Tailor time \(([^)]+)\):\s+(.+)$/i);
			if (m) { const secs = parseElapsed(m[2]); if (secs!=null) acc.tailor = { secs, model: m[1] }; continue; }
			m = line.match(/^Judge time \(([^)]+)\):\s+(.+)$/i);
			if (m) { const secs = parseElapsed(m[2]); if (secs!=null) acc.judge = { secs, model: m[1] }; continue; }
		}
		if (acc.fit || acc.tailor || acc.judge) {
			accumulatedTimesRef.current = acc;
		}
	} catch {}
}	// Results (shared across pages, database-backed via snapshots) – pass SSR-seeded values to avoid flicker
	const { resultType, setResultType, fitOutput, setFitOutput, tailoredOutput, setTailoredOutput, judgeOutput, setJudgeOutput, clearOutputs, clearFitOnly } = useSharedOutputs({ resultType: (initialResultType as any), fitOutput: initialFitOutput, tailoredOutput: initialTailoredOutput, judgeOutput: initialJudgeOutput });
	
	// Sync props to state when navigating (since useSharedInputs/Outputs ignore prop changes after mount)
	useEffect(() => { if (initialResumeText !== undefined) setResumeText(initialResumeText); }, [initialResumeText, setResumeText]);
	useEffect(() => { if (initialJdText !== undefined) setJdText(initialJdText); }, [initialJdText, setJdText]);
	useEffect(() => { if (initialFitOutput !== undefined) setFitOutput(initialFitOutput); }, [initialFitOutput, setFitOutput]);
	useEffect(() => { if (initialTailoredOutput !== undefined) setTailoredOutput(initialTailoredOutput); }, [initialTailoredOutput, setTailoredOutput]);
	useEffect(() => { if (initialJudgeOutput !== undefined) setJudgeOutput(initialJudgeOutput); }, [initialJudgeOutput, setJudgeOutput]);
	useEffect(() => { if (initialStatsMd !== undefined) setStatsMd(initialStatsMd); }, [initialStatsMd, setStatsMd]);

	// Manual selection lock: when user clicks a radio, prevent auto-switch until a new job actively starts.
	const autoSwitchLockedRef = useRef<boolean>(false);
	// Deterministic single run metadata replacing heuristic lastSingleRunPhaseRef logic.
	// Each single-model submission increments a counter; on completion we only auto-switch
	// if the runId matches and the user hasn't manually changed resultType since start.
	const globalRunCounterRef = useRef(0);
	const manualChangeVersionRef = useRef(0);
	const singleRunMetaRef = useRef<{ runId: number; intendedResultType: 'fit'|'tailor'|'judge'; manualVersionAtStart: number }|null>(null);
	// Tracks last runId we successfully auto-switched for (to prevent duplicate fallback firing)
	const lastAutoSwitchRunIdRef = useRef<number>(0);
	// Mutable refs so async callbacks (SSE completion, timeouts) always see latest outputs (avoid stale closure issue causing judge missing in snapshot)
	const fitOutputRef = useRef(fitOutput); useEffect(()=>{ fitOutputRef.current = fitOutput; },[fitOutput]);
	const tailoredOutputRef = useRef(tailoredOutput); useEffect(()=>{ tailoredOutputRef.current = tailoredOutput; },[tailoredOutput]);
	const judgeOutputRef = useRef(judgeOutput); useEffect(()=>{ judgeOutputRef.current = judgeOutput; },[judgeOutput]);
	// We still allow localStorage hydration to override only if it had a stored selection (handled inside useSharedOutputs)
	const effectiveResultType = resultType || (initialResultType as any) || "fit"; // stable during first paint with default
	const resultTypeRef = useRef(resultType); useEffect(()=>{ resultTypeRef.current = resultType; }, [resultType]);
	const lastForcedResultRef = useRef<{type:string; ts:number}|null>(null);
	// Temporary debug effect removed (resultType change logging)
	// If SSR provided a resultType but hook hasn't persisted yet, write cookie immediately (synchronous effect)
	useEffect(() => {
		if (!initialResultType) return;
		try {
			const secure = (typeof location !== 'undefined' && location.protocol === 'https:') ? '; Secure' : '';
			// Only set if no existing cookie to avoid churn
			if (!document.cookie.includes('rt_result_type=')) {
				document.cookie = `rt_result_type=${encodeURIComponent(initialResultType)}; Path=/; SameSite=Lax${secure}; Max-Age=300`;
			}
		} catch {}
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);

	// URL-driven view: on mount, if ?view is present use it; otherwise reflect current effective type into URL.
	// URL parameter manipulation removed - state managed via localStorage/cookies only
	// This keeps URLs clean and simple: /resume instead of /resume?view=fit
	// Clean up any lingering view parameters from old bookmarks/links
	useEffect(() => {
		if (typeof window === 'undefined') return;
		const url = new URL(window.location.href);
		if (url.searchParams.has('view')) {
			url.searchParams.delete('view');
			window.history.replaceState({}, '', url.toString());
		}
	}, []);
	
	// Still set cookie for SSR parity (prevents flicker on page load)
	useEffect(() => {
		try {
			const eff = (resultType || initialResultType || 'fit').toLowerCase();
			const secure = (typeof location !== 'undefined' && location.protocol === 'https:') ? '; Secure' : '';
			document.cookie = `rt_result_type=${encodeURIComponent(eff)}; Path=/; SameSite=Lax${secure}; Max-Age=300`;
		} catch {}
	}, [resultType, initialResultType]);

	// --- Applied snapshot feature state ---
	// Auth state first (needed by applied sync effect)
	const [isLoggedIn, setIsLoggedIn] = useState<boolean | null>(initialLoggedIn === true ? true : null);
	// appliedChecked must reflect SSR on first render to prevent hydration mismatch.
	// Initialize strictly from SSR-provided initialApplied; do NOT force-true based solely on ?appliedKey,
	// because SSR already fetched by key/id when present. Hydrate will reconcile if needed.
	const [appliedChecked, setAppliedChecked] = useState<boolean>(() => !!initialApplied);
	const [appliedSaving, setAppliedSaving] = useState<boolean>(false); // Track saving state for UI disable
	const [appliedLoading, setAppliedLoading] = useState<boolean>(false); // Track initial fetch from database

	// STEAM: No cookie-based promotion - database only
	// Removed rt_open_force_applied cookie check

	// STEAM-LIKE: No cookie writes on mount - HistoryClient owns rt_applied_state
	// SSR can read the cookie that HistoryClient set, but we don't write it here.
	useEffect(() => {
		// Intentionally empty - removed all cookie writes for state/jd/hash
		// run once on mount only
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);
	// STEAM: No cookie reads - database only
	// Removed cookie-based checkbox promotion logic
	const [restoredFromApplied, setRestoredFromApplied] = useState<boolean>(!!initialApplied && (initialFitOutput || initialTailoredOutput || initialJudgeOutput ? true : false));
	const [appliedBanner, setAppliedBanner] = useState<string>(() => initialAppliedBanner || (initialApplied ? "Applied snapshot" : ""));
	// Legacy appliedKey reference (still used when opening old history entries via ?appliedKey=)
	const lastAppliedKeyRef = useRef<string | null>(null);

	// If SSR already loaded the snapshot (initialSnapshotLoaded === true), DO NOT immediately clean
	// query params on mount. Hydrate (or the early cookie effect) will persist cookies first, and the
	// hydrate finalize path will then clean the URL. This avoids a refresh window with no params and
	// no cookies yet.
	// (left intentionally empty)
	const awaitingAppliedHydrateRef = useRef<boolean>(false);
	const mountedAtRef = useRef<number>(Date.now());
	// Track guard window timing for debug logs
	const guardStartAtRef = useRef<number | null>(null);
	// Short protection window after hydrate to prevent JD-level lookup from flipping applied state
	const protectAppliedUntilRef = useRef<number>(0);
	// If SSR provided initial outputs, set protection window on mount to prevent immediate clearing
	useEffect(() => {
		if (initialSnapshotLoaded && (initialFitOutput || initialTailoredOutput || initialJudgeOutput)) {
			const protectUntil = Date.now() + 8000;
			protectAppliedUntilRef.current = protectUntil;
			// Also initialize snapshot refs to match SSR-loaded state
			snapshotOutputsRef.current = {
				fit: initialFitOutput || null,
				tailored: initialTailoredOutput || null,
				judge: initialJudgeOutput || null,
				statsMd: initialStatsMd || null
			};
			// CRITICAL: Set snapshot baseline from SSR props, NOT current state
			// (inputs from useSharedInputs haven't hydrated yet at mount time)
			const jdNorm = initialJdText?.trim() ? normalizeText(initialJdText) : '';
			const baseNorm = initialResumeText?.trim() ? normalizeText(initialResumeText) : '';
			if (jdNorm) {
				snapshotInputsRef.current = { jd: jdNorm, base: baseNorm };
			}
		}
	}, []); // Only run on mount
	// If user edits during protection, remember to demote once guard lifts
	const pendingAutoDemoteRef = useRef<{ type: 'jd-change' | 'input-diff' | 'output-diff'; cause?: string; at: number } | null>(null);
	// Helper: demote logic for JD content change (clears outputs + stats and unchecks Applied)
	const demoteForJDChange = useCallback((cause: string) => {
		try {
			if (isRtDebug()) log('APPLIED.DEMOTE', { cause, deferred: true, navId: getNavId() });
		} catch {}
		// Clear visible outputs + stats + applied flags
		clearOutputs();
		setStatsMd("");
		setAppliedBanner("");
		setAppliedChecked(false);
		setRestoredFromApplied(false);
		currentJdHashRef.current = null;
		lastJdSnapshotRef.current = "";
		snapshotOutputsRef.current = { fit: null, tailored: null, judge: null, statsMd: null };
		if (pendingAccumResetRef.current) { pendingAccumResetRef.current = false; }
		accumulatedTimesRef.current = {} as any;
		phaseTimesRef.current = {};
		// Rebuild snapshot input baseline from current text (if any)
		try {
			const jdNorm = jdText.trim() ? normalizeText(jdText) : '';
			snapshotInputsRef.current = jdNorm ? { jd: jdNorm, base: normalizeText(resumeText || "") } : null;
		} catch { snapshotInputsRef.current = null; }
		// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
	}, [clearOutputs, resumeText, jdText]);

	// Helper: demote logic for input/output divergence (does not clear outputs)
	const demoteForInputDiff = useCallback((cause: string) => {
		try {
			if (isRtDebug()) log('APPLIED.DEMOTE', { cause, deferred: true, navId: getNavId() });
		} catch {}
		setAppliedChecked(false);
		// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
		setRestoredFromApplied(false);
		if (cause === 'OUTPUT_DIFF') setAppliedBanner("Outputs updated – this is a new draft (not yet saved)");
		else setAppliedBanner("Edited – this is a new draft (not yet saved)");
	}, []);

	// Schedule a deferred demotion after the protection window ends
	const scheduleDeferredDemote = useCallback((type: 'jd-change'|'input-diff'|'output-diff', cause?: string) => {
		const now = Date.now();
		pendingAutoDemoteRef.current = { type, cause, at: now };
		const target = Math.max(protectAppliedUntilRef.current || now, now);
		const delay = Math.max(0, target - now + 30);
		window.setTimeout(() => {
			if (Date.now() < (protectAppliedUntilRef.current || 0)) return; // still protected
			const pending = pendingAutoDemoteRef.current;
			if (!pending || pending.type !== type) return;
			if (type === 'jd-change') demoteForJDChange(pending.cause || 'JD_CHANGED');
			else demoteForInputDiff(pending.cause || (type === 'output-diff' ? 'OUTPUT_DIFF' : 'INPUT_DIFF'));
			pendingAutoDemoteRef.current = null;
		}, delay);
	}, [demoteForJDChange, demoteForInputDiff]);
		// Pre-hydrate guard: if URL has ?appliedKey, suppress any auto-uncheck effects until hydrate runs.
		// Do not force the checkbox to "checked" here; let the hydrate step decide after fetching by-key.
	useLayoutEffect(() => {
		if (typeof window === 'undefined') return;
		try {
			const sp = new URLSearchParams(window.location.search);
			const directKey = sp.get('appliedKey');
			const forceAppliedFlag = (sp.get('forceApplied') === '1');
				if (!directKey) return;
				if (isRtDebug()) log('GUARD.START', { reason: 'appliedKey', appliedKey: directKey, navId: getNavId() });
				if (isRtDebug()) log('HYDRATE.BEGIN', { appliedKey: directKey, forceApplied: forceAppliedFlag, navId: getNavId() });
				// Hold a guard until hydrate clears it so demotion effects don't run during lookup
				awaitingAppliedHydrateRef.current = true;
				guardStartAtRef.current = typeof performance !== 'undefined' ? performance.now() : Date.now();
			// Failsafe: if hydrate never runs (e.g., user not logged in), release the guard after a short time
			const start = guardStartAtRef.current || (typeof performance !== 'undefined' ? performance.now() : Date.now());
			const t = setTimeout(() => {
				awaitingAppliedHydrateRef.current = false;
				const end = (typeof performance !== 'undefined' ? performance.now() : Date.now());
				if (isRtDebug()) log('GUARD.END', { reason: 'timeout', appliedKey: directKey, durationMs: Math.round(end - (start || end)), navId: getNavId() });
				guardStartAtRef.current = null;
			}, 8000);
			return () => clearTimeout(t);
		} catch {}
	}, []);
	// New JD hash single-snapshot model
	const currentJdHashRef = useRef<string | null>(null);
	const currentAppliedKeyRef = useRef<string | null>(null); // Store appliedKey for clearing IOH flags on unapply
	const snapshotInputsRef = useRef<{ jd: string; base: string } | null>(null); // normalized texts of snapshot for edit detection
	const snapshotOutputsRef = useRef<{ fit?: string | null; tailored?: string | null; judge?: string | null; statsMd?: string | null } | null>(null); // outputs+stats at time of snapshot
	const debTimerRef = useRef<any>(null); // debounce timer id
	const savingRef = useRef<boolean>(false); // prevent duplicate saves
	const userIdRef = useRef<string | null>(null); // captured user id when logged in
	// Track if the user has edited/pasted since mount to suppress snapshot-loading banners on user actions
	const userEditedSinceMountRef = useRef<boolean>(false);
	// Track hashes that were looked up and not found earlier in this session so we can
	// distinguish first-time creation from loading existing history.
	const jdNotFoundRef = useRef<Set<string>>(new Set());
	// Track a recently first-created JD hash + expiry so lookup doesn't overwrite the 'JD saved' banner immediately.
	const firstCreationBannerRef = useRef<{ hash: string; until: number } | null>(null);

	// When JD text changes (including clearing) before any new run, nuke prior outputs so user isn't shown stale history.
	// This covers both: (a) user clears box, (b) user edits even a single character making hash differ from snapshotInputsRef.
	useEffect(() => {
		try {
			// Short-circuit demotion effects during post-hydrate protection window – except
			// when the JD truly changed due to user input (diverged/cleared/new JD). In that case,
			// demote immediately even if protected to avoid 5–10s delay.
			if (Date.now() < protectAppliedUntilRef.current) {
				const jdNormNow = jdText.trim() ? normalizeText(jdText) : '';
				const snapInNow = snapshotInputsRef.current;
				const hadSnapNow = !!snapInNow?.jd;
				const divergedNow = jdNormNow && snapInNow && jdNormNow !== snapInNow.jd;
				const clearedNow = !jdNormNow && hadSnapNow;
				const newNoSnapshotButStaleOutputsNow = jdNormNow && !snapInNow && (fitOutput || tailoredOutput || judgeOutput);
				// Brand-new JD paste: no snapshot baseline and no outputs – treat as user-initiated so we suppress 'Loading snapshot…'
				const brandNewUserJdNow = jdNormNow && !snapInNow && !(fitOutput || tailoredOutput || judgeOutput);
				// CRITICAL: Don't treat empty jdText as "cleared" during hydration if SSR loaded outputs
				// (useSharedInputs temporarily sets empty before hydrating from props/localStorage)
				const isHydrating = initialSnapshotLoaded && jdText.length === 0;
				if (!isHydrating && (divergedNow || clearedNow || newNoSnapshotButStaleOutputsNow)) {
					// Flag as user edit so initial lookup won't show the loading banner
					userEditedSinceMountRef.current = true;
					if (isRtDebug()) log('APPLIED.PROTECT', { phase: 'jd-change', until: protectAppliedUntilRef.current - Date.now(), immediate: true });
					// Immediate demotion on real user edit
					demoteForJDChange(clearedNow ? 'JD_CLEAR' : (divergedNow ? 'JD_CHANGED' : 'NO_SNAPSHOT_STALE_OUTPUTS'));
				}
				// Mark explicit user edit on fresh paste with no outputs to avoid re-showing 'Loading snapshot…'
				if (brandNewUserJdNow) { userEditedSinceMountRef.current = true; setAppliedBanner(""); }
				return;
			}
			if (awaitingAppliedHydrateRef.current) return;
			// If we're opening via ?appliedKey, do not clear/demote until hydrate resolves
			try { const sp = new URLSearchParams(window.location.search); if (sp.get('appliedKey')) return; } catch {}
			// If a job is running, defer; clearing will happen when next run starts via existing pendingAccumReset logic
			if (fitRequested || tailorRequested || awaitingJudge || judgeRequested) return;
			const jdNorm = jdText.trim() ? normalizeText(jdText) : '';
			const snapIn = snapshotInputsRef.current;
			const hadSnapshot = !!snapIn?.jd;
			const diverged = jdNorm && snapIn && jdNorm !== snapIn.jd;
			const cleared = !jdNorm && hadSnapshot; // previously had a JD snapshot but now empty
			// New JD with no snapshot yet (user pasted brand new JD) while stale outputs from prior JD still visible
			const newNoSnapshotButStaleOutputs = jdNorm && !snapIn && (fitOutput || tailoredOutput || judgeOutput);
			// Brand-new JD paste (no baseline and no outputs)
			const brandNewUserJd = jdNorm && !snapIn && !(fitOutput || tailoredOutput || judgeOutput);
			// If we recently opened an applied snapshot without inputs and seeded synthetic inputs, do not demote here
			// until the user actually edits the content (which will diverge from the synthetic baseline).
			if (newNoSnapshotButStaleOutputs && awaitingAppliedHydrateRef.current) return;
				if (diverged || cleared || newNoSnapshotButStaleOutputs) {
					userEditedSinceMountRef.current = true;
				if (isRtDebug()) log('APPLIED.DEMOTE', { cause: cleared ? 'JD_CLEAR' : (diverged ? 'JD_CHANGED' : 'NO_SNAPSHOT_STALE_OUTPUTS'), hasSnapshot: hadSnapshot, navId: getNavId(), awaitingHydrate: awaitingAppliedHydrateRef.current, inProtectWindow: Date.now() < protectAppliedUntilRef.current, restoredFromApplied });
				// Clear visible outputs + stats + applied flags
				clearOutputs();
				setStatsMd("");
				setAppliedBanner("");
				setAppliedChecked(false);
				// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
				setRestoredFromApplied(false);
				currentJdHashRef.current = null;
				lastJdSnapshotRef.current = "";
				snapshotOutputsRef.current = { fit: null, tailored: null, judge: null, statsMd: null };
				if (pendingAccumResetRef.current) { pendingAccumResetRef.current = false; }
				// Also drop accumulator so prior times don't linger for a new JD
				accumulatedTimesRef.current = {}; // ensure stale phase times removed immediately
				phaseTimesRef.current = {};
				// Replace snapshotInputsRef only if we actually have content (for edited case) else null when cleared
				snapshotInputsRef.current = jdNorm ? { jd: jdNorm, base: normalizeText(resumeText || "") } : null;
			}
			// Mark explicit user edit on fresh paste with no outputs to avoid re-showing 'Loading snapshot…'
			if (brandNewUserJd) { userEditedSinceMountRef.current = true; setAppliedBanner(""); }
			// Strong invariant: empty JD => no outputs.
			// Skip during protection window because hydrate may still be applying state.
			if (!(Date.now() < protectAppliedUntilRef.current) && !jdNorm && (fitOutput || tailoredOutput || judgeOutput || statsMd)) {
				if (isRtDebug()) log('APPLIED.DEMOTE', { cause: 'JD_EMPTY', navId: getNavId(), awaitingHydrate: awaitingAppliedHydrateRef.current, inProtectWindow: Date.now() < protectAppliedUntilRef.current, restoredFromApplied });
				clearOutputs({ preserveResultType: true });
				setStatsMd("");
				currentJdHashRef.current = null;
				lastJdSnapshotRef.current = "";
				snapshotInputsRef.current = null;
				snapshotOutputsRef.current = { fit: null, tailored: null, judge: null, statsMd: null };
				setAppliedChecked(false); setAppliedBanner(""); setRestoredFromApplied(false);
				// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
				accumulatedTimesRef.current = {};
			}
		} catch {}
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [jdText, fitOutput, tailoredOutput, judgeOutput, statsMd]);

	// Job ids/tokens
	const [jobId, setJobId] = useState<string | null>(null);
	const [jobToken, setJobToken] = useState<string | null>(null);
	const [lastCancelJobId, setLastCancelJobId] = useState<string | null>(null);

	// Model metadata (define early so hooks below can reference) + cached alias
	const fitModelAlias = useMemo(() => {
		if (!fitModelLabel) {
			if (isRtDebug()) {
				console.log('[fitModelAlias] No fitModelLabel, returning null');
			}
			return null;
		}
		
		const alias = DISPLAY_OPTIONS.find(o=>o.label===fitModelLabel)?.alias || null;
		
		if (isRtDebug()) {
			console.log('[fitModelAlias] Derived alias:', {
				fitModelLabel,
				alias,
				allDisplayOptions: DISPLAY_OPTIONS.map(o => ({ label: o.label, alias: o.alias }))
			});
		}
		
		return alias;
	}, [fitModelLabel]);
	const tailorModelAlias = useMemo(() => {
		if (!tailorModelLabel) {
			if (isRtDebug()) {
				console.log('[tailorModelAlias] No tailorModelLabel, returning null');
			}
			return null;
		}
		
		const alias = DISPLAY_OPTIONS.find(o=>o.label===tailorModelLabel)?.alias || null;
		
		if (isRtDebug()) {
			console.log('[tailorModelAlias] Derived alias:', {
				tailorModelLabel,
				alias
			});
		}
		
		return alias;
	}, [tailorModelLabel]);
	// Backward compatibility alias (used in existing stats/jd save code referencing modelAlias/modelMeta for tailor)
	const modelAlias = tailorModelAlias;
	const fitModelMeta = useMemo(() => {
		if (!fitModelAlias) {
			if (isRtDebug()) {
				console.log('[fitModelMeta] No fitModelAlias, returning null');
			}
			return null;
		}
		
		const meta = MODEL_REGISTRY[fitModelAlias] || null;
		
		if (isRtDebug()) {
			console.log('[fitModelMeta] Resolved meta:', {
				fitModelAlias,
				meta,
				registryKeys: Object.keys(MODEL_REGISTRY)
			});
		}
		
		return meta;
	}, [fitModelAlias]);
	const tailorModelMeta = useMemo(() => {
		if (!tailorModelAlias) {
			if (isRtDebug()) {
				console.log('[tailorModelMeta] No tailorModelAlias, returning null');
			}
			return null;
		}
		
		const meta = MODEL_REGISTRY[tailorModelAlias] || null;
		
		if (isRtDebug()) {
			console.log('[tailorModelMeta] Resolved meta:', {
				tailorModelAlias,
				meta
			});
		}
		
		return meta;
	}, [tailorModelAlias]);
	const modelMeta = tailorModelMeta;
	const judgeMeta = useMemo(() => {
		if (!judgeLabel) return null;
		const alias = judgeLabel.includes(" — ") ? judgeLabel.split(" — ")[0] : judgeLabel;
		const m = MODEL_OPTIONS.find(o => o.alias === alias);
		if (m) {
			if (isRtDebug()) try { console.debug('[judgeMeta] resolved', { judgeLabel, alias, provider: m.provider, model_id: m.model_id }); } catch {}
			return { provider: m.provider, model_id: m.model_id };
		}
		return null;
	}, [judgeLabel]);

	// Alias code mapping (shared with BenchmarkClient) for anonymized comparative judging
	const CODE_MAP: Record<string,string> = useMemo(()=>({
		"Claude Sonnet 4.6": "CS4.6",
		"Claude Opus 4.6": "CO4.6",
		"Gemini 2.5 Flash": "G2.5F",
		"Gemini 3.1 Pro": "G3.1P",
		"GPT-4.1": "G4.1",
		"GPT-5": "G5",
		"Grok 4.1 Fast Reasoning": "Gr4.1FR",
		"Grok 4": "Gr4",
	}), []);
	const aliasCode = useCallback((alias: string) => CODE_MAP[alias] || ("C" + Math.abs(alias.split('').reduce((a,c)=>a+c.charCodeAt(0),0)) % 10000), [CODE_MAP]);
	// Flag that current judge run is a multi-model comparative ranking (Option B)
	const rankingJudgeRef = useRef<boolean>(false);
	// Capture legend to append after SSE completion
	const rankingLegendRef = useRef<string>("");
	// Snapshot of candidate count for stats / possible future pricing display
	const rankingCandidateCountRef = useRef<number>(0);

	// Tooltips (averages)
	const [fitTip, setFitTip] = useState<string>("");
	const [tailorTip, setTailorTip] = useState<string>("");
	const [judgeTip, setJudgeTip] = useState<string>("");
	// Multi-model aggregate tooltips (benchmark style, no separate Judge: section, use full model names)
	const [multiModeActive, setMultiModeActive] = useState<boolean>(false);
	const [multiFitAliases, setMultiFitAliases] = useState<string[]>([]);
	const [multiTailorAliases, setMultiTailorAliases] = useState<string[]>([]);
	const [multiJudgeAliases, setMultiJudgeAliases] = useState<string[]>([]);
	const [multiFitTip, setMultiFitTip] = useState<string>("");
	const [multiTailorTip, setMultiTailorTip] = useState<string>("");
	const [multiJudgeTip, setMultiJudgeTip] = useState<string>("");
	// Cached averages so tooltips can update instantly on model/judge toggles
	const [avgRowsUser, setAvgRowsUser] = useState<Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }> | null>(null);
	const [avgRowsGlobal, setAvgRowsGlobal] = useState<Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }> | null>(null);
	const [useMyAvgs, setUseMyAvgs] = useState<boolean>(() => {
		try { return (localStorage.getItem("use_my_avgs") === "1"); } catch { return false; }
	});
	useEffect(() => {
		const onSettings = (e: Event) => {
			try { const d = (e as CustomEvent).detail || {}; if (typeof d.useMyAvgs === 'boolean') setUseMyAvgs(d.useMyAvgs); } catch {}
		};
		window.addEventListener("rt-settings", onSettings as EventListener);
		return () => window.removeEventListener("rt-settings", onSettings as EventListener);
	}, []);

	const [alert, setAlert] = useState<Alert>(null);
	// Start unknown; controls stay disabled until session resolves. Use a one-shot
	// hint set just before redirect from Login to suppress the logged-out banner flash.
	// Force UI (especially applied checkbox) disabled until auth probe finishes to avoid enabled->disabled flicker on stale cookies
	// If SSR explicitly verified auth (protected route), skip pending; otherwise require client probe even if cookie suggested logged in.
	const [authPending, setAuthPending] = useState<boolean>(() => {
		if (initialAuthVerified) return false;
		// If SSR indicated logged in (via cookie check), optimistically assume verified to avoid disabled flash
		if (initialLoggedIn === true) return false;
		return true; // force a client check to confirm
	});
	useEffect(() => {
		let mounted = true;
		const seq = { current: 0 };
		// Skip login-restore when we're in the middle of an appliedKey hydrate/navigation to avoid clobbering
		try {
			if (awaitingAppliedHydrateRef.current) {
				if (isRtDebug()) log('LOGIN_RESTORE.SKIP', { reason: 'awaiting_hydrate' });
				return;
			}
			if (typeof window !== 'undefined') {
				const sp = new URLSearchParams(window.location.search);
				if (sp.get('appliedKey')) {
					if (isRtDebug()) log('LOGIN_RESTORE.SKIP', { reason: 'url_appliedKey' });
					return;
				}
			}
		} catch {}
		const check = async () => {
			const id = ++seq.current;
			try {
				const me = await apiClient.get<any>("/users/me");
				if (mounted && seq.current === id) {
					setIsLoggedIn(true);
					if (me && me.id) userIdRef.current = String(me.id);
					// Prompt sidebar to rebroadcast multi-model selection immediately after login
					try { window.dispatchEvent(new CustomEvent('rt-multi-request')); } catch {}
				}
			} catch {
				if (mounted && seq.current === id) setIsLoggedIn(false);
			} finally {
				if (mounted) setAuthPending(false);
			}
		};
		// Run immediately to enable controls quickly for logged-in users
		check();
		const onAuth = (e: Event) => {
			// If explicit logout event, invalidate prior checks and don't recheck immediately
			try {
				const d: any = (e as CustomEvent).detail || {};
				if (String(d?.state || "").toLowerCase() === "logged-out") { seq.current++; return; }
			} catch {}
			check();
			// After auth events, request a multi-model rebroadcast so tooltips align without refresh
			try { window.dispatchEvent(new CustomEvent('rt-multi-request')); } catch {}
		};
		window.addEventListener("rt-auth", onAuth as EventListener);
		return () => { mounted = false; window.removeEventListener("rt-auth", onAuth as EventListener); };
	}, []);

	// Client-side redirect for /resume route (protected workspace)
	const redirectedRef = useRef(false);
	useEffect(() => {
		if (authPending) return; // Wait for auth check to complete
		if (redirectedRef.current) return; // Prevent multiple redirects
		if (isLoggedIn === false && typeof window !== 'undefined' && window.location.pathname === '/resume') {
			console.warn('🔄 [AUTH REDIRECT] Redirecting from /resume to / (not logged in)', {
				pathname: window.location.pathname,
				search: window.location.search,
				isLoggedIn,
				authPending
			});
			redirectedRef.current = true;
			// Use Next.js router for client-side navigation (no hard reload)
			// Go to clean home page URL without any query parameters
			router.replace('/');
			// Also clear the URL immediately to prevent the view param from being added back
			if (typeof window !== 'undefined') {
				window.history.replaceState({}, '', '/');
			}
		}
	}, [authPending, isLoggedIn, router]);

	const running = fitRequested || !!tailorRequested || awaitingJudge || judgeRequested;
	// Disable controls when auth is pending OR when we know the user is NOT logged in.
	// This prevents the enabled->disabled flicker on page load when logged out.
	// When an applied snapshot is in effect, we keep inputs readOnly but not disabled to avoid visual flash.
	const uiDisabled = useMemo(() => authPending || (isLoggedIn !== true), [authPending, isLoggedIn]);

	// (userIdRef now hydrated inside auth probe; removed duplicate /users/me fetch effect)

	// Auth-gated snapshot hydrate; supports either appliedKey (query) or snapshotId (path)
	useEffect(() => {
		if (typeof window === 'undefined') return;
		if (isLoggedIn !== true) return; // only when authenticated
		const params = new URLSearchParams(searchParams?.toString() || window.location.search);
		const directKey = params.get('appliedKey');
		const forceAppliedFlag = params.get('forceApplied') === '1';
		// Detect snapshotId from pathname pattern /resume/s/{id}
		const path = pathname || window.location.pathname;
		const snapMatch = /^\/resume\/s\/([^/?#]+)/.exec(path || '');
		const snapshotId = snapMatch ? decodeURIComponent(snapMatch[1]) : null;
		// If SSR loaded a snapshot but we also have a direct identity in the URL,
		// still run hydrate to reconcile client state accurately.
		if (initialSnapshotLoaded && !(directKey || snapshotId)) return;
		
		// CLIENT-SIDE FALLBACK: If SSR didn't load snapshot (e.g., incognito mode where
		// session cookie wasn't available to SSR), fetch current_snapshot_key from DB
		if (!initialSnapshotLoaded && !directKey && !snapshotId) {
			const controller = new AbortController();
			(async () => {
				try {
					// Fetch user's last viewed snapshot key
					const currentSnapshotRes: any = await apiClient.get('/users/me/current-snapshot', { signal: controller.signal });
					if (controller.signal.aborted || isLoggedIn !== true) return;
					
					const currentSnapshotKey = currentSnapshotRes?.current_snapshot_key;
					if (currentSnapshotKey) {
						// Load the snapshot using the key
						const data: any = await apiClient.get('/applications/by-key', { 
							query: { appliedKey: currentSnapshotKey }, 
							signal: controller.signal 
						});
						
						if (controller.signal.aborted || isLoggedIn !== true) return;
						
						if (data?.found && data?.row) {
							const snap = data.row.snapshot || {};
							const appliedServer = !!data.row?.isApplied;
							
							// Hydrate inputs
							if (typeof snap.resumeInput === 'string' && snap.resumeInput) {
								setResumeText(snap.resumeInput);
							}
							if (typeof snap.jdInput === 'string' && snap.jdInput) {
								setJdText(snap.jdInput);
							}
							
							// Hydrate outputs - ONLY if not currently generating new ones (avoids overwriting stream)
							const runningAny = fitRequestedRef.current || tailorRequestedRef.current || awaitingJudgeRef.current || judgeRequestedRef.current || !!optimisticRunningRef.current;
							if (!runningAny) {
								if (typeof snap.fitOutput === 'string') setFitOutput(snap.fitOutput);
								if (typeof snap.tailoredOutput === 'string') setTailoredOutput(snap.tailoredOutput);
								if (typeof snap.judgeOutput === 'string') setJudgeOutput(snap.judgeOutput);
								if (typeof snap.statsMd === 'string') setStatsMd(snap.statsMd);
							}
							
							// Set applied state and banner
							const hasInputs = !!(snap.resumeInput || snap.jdInput);
							const hasOutputs = !!(snap.fitOutput || snap.tailoredOutput || snap.judgeOutput);
							setAppliedChecked(appliedServer);
							setRestoredFromApplied(Boolean(appliedServer && hasInputs));
							setAppliedBanner(
								appliedServer 
									? (hasInputs ? 'Applied snapshot opened – editing either box will create a new draft' : 'Applied snapshot metadata loaded – inputs missing; editing enabled')
									: 'Previously seen JD – loaded latest results (re-run to refresh)'
							);
							
							// Set snapshot refs
							snapshotOutputsRef.current = { 
								fit: snap.fitOutput || null, 
								tailored: snap.tailoredOutput || null, 
								judge: snap.judgeOutput || null, 
								statsMd: snap.statsMd || null 
							};
							
							const jdNorm = snap.jdInput?.trim() ? normalizeText(snap.jdInput) : '';
							const baseNorm = snap.resumeInput?.trim() ? normalizeText(snap.resumeInput) : '';
							if (jdNorm) {
								snapshotInputsRef.current = { jd: jdNorm, base: baseNorm };
							}
							
							if (appliedServer) { 
								protectAppliedUntilRef.current = Date.now() + 8000; 
							}
							
							if (isRtDebug()) log('CLIENT_FALLBACK.LOADED', { 
								appliedKey: currentSnapshotKey, 
								hasInputs, 
								hasOutputs, 
								appliedServer 
							});
						}
					}
				} catch (err) {
					if (!controller.signal.aborted) {
						console.error('[CLIENT_FALLBACK] Failed to load snapshot:', err);
					}
				}
			})();
			return () => controller.abort();
		}
		
		if (!directKey && !snapshotId) return;
		const controller = new AbortController();
		awaitingAppliedHydrateRef.current = true;
		// Only show loading banner if user hasn't edited since mount (avoid on paste/edits)
		if (!userEditedSinceMountRef.current) setAppliedBanner("Loading snapshot…");
		if (isRtDebug()) log('HYDRATE.BEGIN', { appliedKey: directKey, snapshotId, forceApplied: forceAppliedFlag, navId: getNavId() });
		(async () => {
			try {
				// Fetch by id or by key
				let data: any = null;
				if (snapshotId) {
					if (isRtDebug()) log('LOOKUP.START', { kind: 'by-id', snapshotId });
					data = await apiClient.get('/applications/by-id', { query: { snapshotId }, signal: controller.signal }).catch(() => null as any);
				} else if (directKey) {
					if (isRtDebug()) log('LOOKUP.START', { kind: 'by-key', appliedKey: directKey });
					data = await apiClient.get('/applications/by-key', { query: { appliedKey: directKey }, signal: controller.signal }).catch(() => null as any);
				}
				if (controller.signal.aborted || isLoggedIn !== true) return;
				if (!data || data.found !== true) {
					if (isRtDebug()) log('HYDRATE.END', { found: false, appliedEffective: !!forceAppliedFlag });
					if (forceAppliedFlag) {
						setAppliedChecked(true);
						setRestoredFromApplied(false);
						setAppliedBanner('Applied (from history) – snapshot not found; editing enabled');
						return;
					}
					setAppliedChecked(false);
					setAppliedBanner('');
					// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
					return;
				}
				// Only treat as applied for this exact snapshot. If we opened via appliedKey,
				// require the returned row.appliedKey to match the directKey to avoid sibling bleed.
				const isByKey = !!directKey && !snapshotId;
				const appliedServer = !!data.row?.isApplied && (!isByKey || data.row?.appliedKey === directKey);
				const snap = (data.row && data.row.snapshot) || {};
				if (!snap || typeof snap !== 'object') {
					if (appliedServer) {
						setAppliedChecked(true);
						setRestoredFromApplied(false);
						setAppliedBanner('Applied snapshot metadata loaded, but content unavailable – editing enabled');
					} else {
						setAppliedChecked(false);
						setRestoredFromApplied(false);
						setAppliedBanner('');
						// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
					}
					return;
				}
				const hasInputs = (typeof snap.resumeInput === 'string') && (typeof snap.jdInput === 'string');
				if (hasInputs) {
					if (appliedServer) {
						setResumeText(snap.resumeInput as string);
						setJdText(snap.jdInput as string);
					} else {
						if (!resumeText.trim()) setResumeText(snap.resumeInput as string);
						if (!jdText.trim()) setJdText(snap.jdInput as string);
					}
				}
				// lastAppliedKey only meaningful for by-key
				if (directKey) { lastAppliedKeyRef.current = directKey; }
				// Database is the single source of truth for applied state - ignore URL hints
				const appliedEffective = appliedServer;
				if (hasInputs) {
					snapshotInputsRef.current = { jd: normalizeText(String(snap.jdInput || '')), base: normalizeText(String(snap.resumeInput || '')) };
				} else {
					if (appliedEffective) {
						try {
							snapshotInputsRef.current = { jd: normalizeText(String(jdText || '')), base: normalizeText(String(resumeText || '')) };
							if (isRtDebug()) log('HYDRATE.SYNTH_INPUTS', { reason: 'applied_no_inputs', jdLen: (jdText||'').length, baseLen: (resumeText||'').length });
						} catch { snapshotInputsRef.current = undefined as any; }
					} else {
						snapshotInputsRef.current = undefined as any;
					}
				}
				const hasOutputs = (snap.fitOutput != null) || (snap.tailoredOutput != null) || (snap.judgeOutput != null);
				if (hasOutputs) {
					snapshotOutputsRef.current = { fit: snap.fitOutput || null, tailored: snap.tailoredOutput || null, judge: snap.judgeOutput || null, statsMd: snap.statsMd || null };
				} else {
					snapshotOutputsRef.current = undefined as any;
				}
				if (isRtDebug()) log('HYDRATE.END', { found: true, rowApplied: appliedServer, hasSnap: !!snap, hasInputs, hasOutputs, appliedEffective });
				setAppliedChecked(appliedEffective);
				setRestoredFromApplied(Boolean(appliedEffective && hasInputs));
				setAppliedBanner(appliedEffective ? (hasInputs ? 'Applied snapshot opened – editing either box will create a new draft' : 'Applied snapshot metadata loaded – inputs missing; editing enabled') : 'Previously seen JD – loaded latest results (re-run to refresh)');
				if (appliedEffective) { protectAppliedUntilRef.current = Date.now() + 8000; }
				// Update current_snapshot_key in database so SSR can reload on refresh
				// Always update when we successfully load a snapshot (from History or any other source)
				// Use whatever key we have: appliedKey from response, or the directKey from URL
				const keyToSave = data.row?.appliedKey || directKey;
				if (keyToSave) {
					try {
						await apiClient.put('/users/me/current-snapshot', { 
							current_snapshot_key: keyToSave
						});
						if (isRtDebug()) log('CURRENT_SNAPSHOT.UPDATE', { appliedKey: keyToSave });
					} catch (err) {
						console.error('[HYDRATE] Failed to update current_snapshot_key:', err);
					}
				}
			} catch {
				if (!controller.signal.aborted) { if (isRtDebug()) log('LOOKUP.ERROR', { kind: snapshotId ? 'by-id' : 'by-key' }); setAppliedChecked(false); setAppliedBanner('Failed to load snapshot'); }
			} finally {
				if (controller.signal.aborted) return;
				awaitingAppliedHydrateRef.current = false;
				// If user already edited while we were hydrating, ensure banner is cleared
				if (userEditedSinceMountRef.current && appliedBanner && /Loading snapshot/i.test(appliedBanner)) {
					setAppliedBanner("");
				}
				// If a demotion was deferred during protection, apply it now
				try {
					if (!(Date.now() < (protectAppliedUntilRef.current || 0)) && pendingAutoDemoteRef.current) {
						const p = pendingAutoDemoteRef.current; pendingAutoDemoteRef.current = null;
						if (p.type === 'jd-change') demoteForJDChange(p.cause || 'JD_CHANGED');
						else demoteForInputDiff(p.cause || (p.type === 'output-diff' ? 'OUTPUT_DIFF' : 'INPUT_DIFF'));
					}
				} catch {}
				// Guard end timing log
				try {
					const start = guardStartAtRef.current || 0;
					if (start) {
						const end = (typeof performance !== 'undefined' ? performance.now() : Date.now());
						if (isRtDebug()) log('GUARD.END', { reason: 'hydrate-finalize', appliedKey: directKey, durationMs: Math.round(end - start), navId: getNavId() });
					}
					guardStartAtRef.current = null;
				} catch {}
				// Clean up transient query params
				try {
					const url = new URL(window.location.href);
					let mutated = false;
					if (url.searchParams.has('appliedKey')) { url.searchParams.delete('appliedKey'); mutated = true; }
					if (url.searchParams.has('forceApplied')) { url.searchParams.delete('forceApplied'); mutated = true; }
					if (mutated) {
						const newUrl = url.pathname + (url.searchParams.toString() ? ('?' + url.searchParams.toString()) : '') + url.hash;
						window.history.replaceState({}, '', newUrl);
						if (isRtDebug()) log('URL.CLEANUP', { removed: ['appliedKey','forceApplied'] });
					}
				} catch {}
			}
		})();
		return () => controller.abort();
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [isLoggedIn, initialSnapshotLoaded, pathname, searchParams]);

	// Restore recently applied state on fast back/forward when ?appliedKey is absent
	useEffect(() => {
		if (typeof window === 'undefined') return;
		try {
			const sp = new URLSearchParams(window.location.search);
			if (sp.get('appliedKey')) return; // handled by hydrate flow
			// sessionStorage restore removed - state managed by API only
			// STEAM: No cookie reads - database only
			// If SSR already told us this row is applied, hold a short guard too (covers first cycle after SSR)
			if (!awaitingAppliedHydrateRef.current && initialApplied) {
				awaitingAppliedHydrateRef.current = true;
				// Protection window to avoid early output divergence demotion from SSR-injected content
				protectAppliedUntilRef.current = Date.now() + 8000;
				const t2 = setTimeout(() => { awaitingAppliedHydrateRef.current = false; }, 2500);
				return () => clearTimeout(t2);
			}
		} catch {}
	}, []);

	// DATABASE-DRIVEN: Fetch Applied state from database on mount and when JD changes
	// This ensures checkbox always reflects actual database state, not stale SSR/cache
	useEffect(() => {
		// Skip if not logged in or no content
		if (isLoggedIn !== true || !jdText.trim()) {
			setAppliedLoading(false);
			return;
		}

		// Show loading immediately and fetch without delay
		setAppliedLoading(true);
		let cancelled = false;

		(async () => {
			try {
				const jdHash = await makeJdHash(jdText);
				if (cancelled) return;
				if (isRtDebug()) console.log('[APPLIED STATE] Fetching from database...', { jdHash: jdHash.substring(0, 16) });
				
				const result = await apiClient.get<{ isApplied: boolean; jdHash: string; appliedKey?: string }>(
					'/applications/jd/check-applied',
					{ query: { jdHash } }
				);
				
				if (cancelled) return;
				const dbIsApplied = result?.isApplied ?? false;
				if (isRtDebug()) console.log('[APPLIED STATE] Database returned:', { isApplied: dbIsApplied });
				
				// Update checkbox to match database (single source of truth)
				if (appliedChecked !== dbIsApplied) {
					if (isRtDebug()) console.log(`[APPLIED STATE] Syncing checkbox: ${appliedChecked} → ${dbIsApplied}`);
					setAppliedChecked(dbIsApplied);
				}
			} catch (err) {
				if (!cancelled) {
					// Suppress expected auth errors during page load
					const isAuthError = err instanceof Error && err.message.includes('Auth not established');
					if (!isAuthError) {
						console.error('[APPLIED STATE] Failed to fetch from database:', err);
					}
				}
			} finally {
				if (!cancelled) {
					setAppliedLoading(false);
				}
			}
		})();

		return () => {
			cancelled = true;
			setAppliedLoading(false);
		};
	}, [isLoggedIn, jdText, apiClient, appliedChecked]);

	// Broadcast running state so the sidebar can disable its Fit/Judge controls while jobs run
	useEffect(() => {
		try { window.dispatchEvent(new CustomEvent("rt-run", { detail: { running } })); } catch {}
	}, [running]);

	// Reconcile missing fit output after async snapshot restores (race with LS hydration)
	useEffect(() => {
		// Only run shortly after mount / snapshot load
		const t = setTimeout(() => {
			try {
				// If we're within a suppression window (e.g., user just clicked Fit), do not repopulate
				if (Date.now() < (suppressRefillUntilRef.current || 0)) return;
				if (!fitOutput && snapshotOutputsRef.current?.fit) {
					const snapVal: any = snapshotOutputsRef.current.fit;
					if (typeof snapVal === 'string') setFitOutput(snapVal);
					else {
						try { setFitOutput(JSON.stringify(snapVal, null, 2)); } catch { setFitOutput(String(snapVal)); }
					}
				}
			} catch {}
		}, 250);
		return () => clearTimeout(t);
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [fitOutput, restoredFromApplied]);


	// Adaptive (leading + trailing) debounce for JD snapshot lookup
	const lastLookupAtRef = useRef<number>(0);
	const lastScheduledLookupJdRef = useRef<string | null>(null);
	const idleThresholdMs = 400; // if idle this long, fire immediately on next change
	const trailingDelayMs = 250;
	const initialLookupDoneRef = useRef<boolean>(false);
	useEffect(() => {
		// Abort controller for most recent network lookup; ensures late responses do not overwrite newer state
		const ctrl = new AbortController();
		// If we're awaiting a hydrate/guard for applied state, skip lookups to avoid premature demotion
		if (awaitingAppliedHydrateRef.current) return;
		if (!jdText.trim()) {
			accumulatedTimesRef.current = {};
			phaseTimesRef.current = {};
			pendingAccumResetRef.current = false;
			lastJdSnapshotRef.current = "";
		}
		if (debTimerRef.current) { clearTimeout(debTimerRef.current); debTimerRef.current = null; }
		if (isLoggedIn !== true) return;
		if (!jdText.trim()) return;
		// Reset cumulative on JD content change vs last snapshot
		try {
			const cur = normalizeText(jdText);
			if (lastJdSnapshotRef.current && cur && cur !== lastJdSnapshotRef.current) {
				// Defer clearing so existing totals remain visible until a new run starts
				pendingAccumResetRef.current = true;
			}
		} catch {}
		if (running) return; // don't overwrite while jobs active
		const runLookup = async () => {
			const startedAt = performance.now();
			let found = false;
			try {
				const jdHash = await makeJdHash(jdText);
				if (currentJdHashRef.current === jdHash && restoredFromApplied) { found = true; return; }
				let data: any = await apiClient.get("/applications/jd/apply", { query: { jdHash }, signal: ctrl.signal }).catch(() => null);
				if (ctrl.signal.aborted) return; // ignore aborted lookup
				if (!data || data.found !== true) {
					jdNotFoundRef.current.add(jdHash);
					// During initial guard/protection, avoid clearing checkbox/banner on not-found
					if (awaitingAppliedHydrateRef.current || Date.now() < protectAppliedUntilRef.current) {
						if (isRtDebug()) log('LOOKUP.SKIP', { reason: 'not_found_guard' });
						return;
					}
					return;
				}
				found = true;
				const snap = data.row?.snapshot || {};
				if (snap.fitOutput != null) {
					if (typeof snap.fitOutput === 'string') setFitOutput(snap.fitOutput);
					else { try { setFitOutput(JSON.stringify(snap.fitOutput, null, 2)); } catch { setFitOutput(String(snap.fitOutput)); } }
				}
				if (snap.tailoredOutput != null) {
					if (typeof snap.tailoredOutput === 'string') setTailoredOutput(snap.tailoredOutput);
					else { try { setTailoredOutput(JSON.stringify(snap.tailoredOutput, null, 2)); } catch { setTailoredOutput(String(snap.tailoredOutput)); } }
				}
				if (snap.judgeOutput != null) {
					if (typeof snap.judgeOutput === 'string') setJudgeOutput(snap.judgeOutput);
					else { try { setJudgeOutput(JSON.stringify(snap.judgeOutput, null, 2)); } catch { setJudgeOutput(String(snap.judgeOutput)); } }
				}
				if (typeof snap.statsMd === 'string') { setStatsMd(snap.statsMd); setTimeout(()=>rebuildAccumulatorFromStats(snap.statsMd),0); }
				if (typeof snap.resumeInput === 'string' && !resumeText.trim()) setResumeText(snap.resumeInput);
				if (typeof snap.jdInput === 'string' && !jdText.trim()) setJdText(snap.jdInput);
				currentJdHashRef.current = jdHash;
				// Build a safe baseline for input divergence checks. Never allow undefined -> "undefined".
				const jdSrc = (typeof snap.jdInput === 'string') ? snap.jdInput : (jdText || '');
				const baseSrc = (typeof snap.resumeInput === 'string') ? snap.resumeInput : (resumeText || '');
				snapshotInputsRef.current = { jd: normalizeText(jdSrc), base: normalizeText(baseSrc) };
				// Store outputs snapshot so divergence detection & later reconciliation have a baseline
				snapshotOutputsRef.current = { fit: snap.fitOutput || null, tailored: snap.tailoredOutput || null, judge: snap.judgeOutput || null, statsMd: snap.statsMd || null };
				if (data.row?.isApplied) {
					setAppliedChecked(true);
					setRestoredFromApplied(true);
					setAppliedBanner("Applied snapshot restored – edit JD to unlock request buttons");
					// Protect against immediate demotion from divergence effects on reload
					protectAppliedUntilRef.current = Date.now() + 8000;
				} else {
					// If within protection window after an applied hydrate, avoid flipping the checkbox here.
					if (Date.now() < protectAppliedUntilRef.current && appliedChecked) {
						if (isRtDebug()) log('LOOKUP.SKIP', { reason: 'protected_applied' });
						// Do NOT mark restoredFromApplied from this non-applied lookup result,
						// to avoid triggering divergence-based auto-demote effects.
						setRestoredFromApplied(false);
					} else {
						setAppliedChecked(false);
						setRestoredFromApplied(true);
					}
					// Only show history banner if:
					// (a) we did not previously mark it not-found (i.e. not first creation), AND
					// (b) we are not within the protected window after first creation banner.
					const inProtected = firstCreationBannerRef.current && firstCreationBannerRef.current.hash === jdHash && firstCreationBannerRef.current.until > Date.now();
					if (jdNotFoundRef.current.has(jdHash)) {
						// First creation load: suppress and clear not-found marker (leave 'JD saved' banner or blank)
						jdNotFoundRef.current.delete(jdHash);
						// Do nothing (keep existing banner)
					} else if (!inProtected) {
						setAppliedBanner("Previously seen JD – loaded latest results (re-run to refresh)");
					}
				}
			} finally {
				lastLookupAtRef.current = performance.now();
				// If not found and still looking at same JD (and banner says loading), clear banner
				try {
					if (!found && !ctrl.signal.aborted) {
						const curNorm = jdText.trim() ? normalizeText(jdText) : '';
						// Only clear if no outputs (so we didn't just overwrite with existing snapshot)
						if (!(awaitingAppliedHydrateRef.current || Date.now() < protectAppliedUntilRef.current) && (!curNorm || (!fitOutputRef.current && !tailoredOutputRef.current && !judgeOutputRef.current))) {
							// If user has edited, keep banner blank (no 'Loading snapshot…')
							setAppliedBanner("");
							setAppliedChecked(false);
							setRestoredFromApplied(false);
						}
					}
				} catch {}
			}
		};
		const now = performance.now();
		const idle = now - lastLookupAtRef.current > idleThresholdMs;
				if (!initialLookupDoneRef.current) {
					initialLookupDoneRef.current = true;
					// Only show the loading banner if the user hasn't just pasted/edited a fresh JD
					if (!userEditedSinceMountRef.current) setAppliedBanner(b => b || "Loading snapshot…");
			runLookup();
		} else if (idle) {
			// Only run immediate lookup if JD text actually changed
			if (jdText !== lastScheduledLookupJdRef.current) {
				lastScheduledLookupJdRef.current = jdText;
				runLookup();
			}
		} else {
			// Only schedule debounce if JD text actually changed
			if (jdText !== lastScheduledLookupJdRef.current) {
				lastScheduledLookupJdRef.current = jdText;
				debTimerRef.current = setTimeout(runLookup, trailingDelayMs);
			}
		}
		return () => { if (debTimerRef.current) { clearTimeout(debTimerRef.current); debTimerRef.current = null; } try { ctrl.abort(); } catch {} };
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [jdText, isLoggedIn, running]);

	// (Removed legacy judge-only fallback restore: unified restore path now handled by login restore + JD snapshot lookup.)

	// Login restore: fetch most recent snapshot when user logs in
	const hasRestoredOnLoginRef = useRef<boolean>(false);
	const inputStoreInitializedRef = useRef<boolean>(false);
	
	// Track when inputStore has finished initialization
	useEffect(() => {
		// Short delay to ensure inputStore state is ready
		const timer = setTimeout(() => {
			inputStoreInitializedRef.current = true;
		}, 100); // Brief delay for inputStore initialization
		return () => clearTimeout(timer);
	}, []);
	
	useEffect(() => {
		// Only restore once per session when user logs in
		if (isLoggedIn !== true) return;
		if (hasRestoredOnLoginRef.current) return;
		
		// Wait for inputStore to initialize first
		if (!inputStoreInitializedRef.current) return;
		
		// Skip if we're already in the middle of loading a specific snapshot
		if (awaitingAppliedHydrateRef.current) return;
		if (initialSnapshotLoaded) return;
		
		// Skip if user already has data loaded (e.g., from URL params or server)
		if (jdText.trim() || resumeText.trim()) return;
		
		hasRestoredOnLoginRef.current = true;
		
		(async () => {
			try {
				if (isRtDebug()) log('LOGIN_RESTORE.START');
				const data: any = await apiClient.get('/applications/latest').catch(() => null);
				
				if (!data || !data.found) {
					if (isRtDebug()) log('LOGIN_RESTORE.NONE', { reason: 'no_snapshots' });
					return;
				}
				
				const snap = data.snapshot || {};
				if (isRtDebug()) log('LOGIN_RESTORE.FOUND', { 
					hasJd: !!snap.jdInput, 
					hasResume: !!snap.resumeInput,
					isApplied: data.isApplied 
				});

				// Restore inputs from snapshot
				const resumeToRestore = typeof snap.resumeInput === 'string' ? snap.resumeInput.trim() : '';
				const jdToRestore = typeof snap.jdInput === 'string' ? snap.jdInput.trim() : '';

				// Restore inputs
				if (resumeToRestore) {
					setResumeText(resumeToRestore);
				}
				if (jdToRestore) {
					setJdText(jdToRestore);
				}
				
				// Restore outputs
				if (typeof snap.fitOutput === 'string' && snap.fitOutput.trim()) {
					setFitOutput(snap.fitOutput);
				}
				if (typeof snap.tailoredOutput === 'string' && snap.tailoredOutput.trim()) {
					setTailoredOutput(snap.tailoredOutput);
				}
				if (typeof snap.judgeOutput === 'string' && snap.judgeOutput.trim()) {
					setJudgeOutput(snap.judgeOutput);
				}
				
				// Restore stats
				if (typeof snap.statsMd === 'string' && snap.statsMd.trim()) {
					setStatsMd(snap.statsMd);
				}
				
				// Restore model selections if available
				if (snap.knobs && typeof snap.knobs === 'object') {
					if (typeof snap.knobs.fitModelLabel === 'string') {
						setFitModelLabel(snap.knobs.fitModelLabel);
					}
					if (typeof snap.knobs.tailorModelLabel === 'string') {
						setTailorModelLabel(snap.knobs.tailorModelLabel);
					}
					if (typeof snap.knobs.judgeLabel === 'string') {
						setJudgeLabel(snap.knobs.judgeLabel);
					}
				}
				
				// Set applied state if applicable
				if (data.isApplied) {
					setAppliedChecked(true);
					setAppliedBanner('Previously applied – loaded from history');
				}
				
				if (isRtDebug()) log('LOGIN_RESTORE.COMPLETE');
			} catch (e) {
				if (isRtDebug()) log('LOGIN_RESTORE.ERROR', { error: String(e) });
			}
		})();
	// Re-run when inputStore might be ready
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [isLoggedIn, jdText, resumeText]);

	// STEAM-LIKE: No rt_last_jd_hash cookie - login restore should fetch from database
	// Removed judge hash persistence to keep system fully database-only
	useEffect(() => {
		// Intentionally empty - removed rt_last_jd_hash cookie write
	}, [judgeOutput, jdText]);

	// Detect edits after restore to mark new draft & auto-uncheck
	useEffect(() => {
		if (!restoredFromApplied || !appliedChecked) return;
		if (awaitingAppliedHydrateRef.current) return; // skip while guard is active
		if (Date.now() < protectAppliedUntilRef.current) return; // skip during protection window
		if (!snapshotInputsRef.current) return;
		const curBase = normalizeText(resumeText);
		const curJd = normalizeText(jdText);
		if (curBase !== snapshotInputsRef.current.base || curJd !== snapshotInputsRef.current.jd) {
			if (isRtDebug()) log('APPLIED.DEMOTE', { cause: 'INPUT_DIFF', navId: getNavId() });
				if (Date.now() < protectAppliedUntilRef.current) {
					// Immediate demotion on real user edit even if protected
					setAppliedChecked(false);
					// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
					setRestoredFromApplied(false);
					setAppliedBanner("Edited – this is a new draft (not yet saved)");
				} else {
					setAppliedChecked(false);
					// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
					setRestoredFromApplied(false);
					setAppliedBanner("Edited – this is a new draft (not yet saved)");
				}
		}
	}, [resumeText, jdText, restoredFromApplied, appliedChecked]);

	// Detect output changes (e.g. user ran Tailor/Fit again) and uncheck if outputs diverge
	useEffect(() => {
		if (!restoredFromApplied || !appliedChecked) return;
		if (awaitingAppliedHydrateRef.current) return; // skip while guard is active
		if (Date.now() < protectAppliedUntilRef.current) return; // skip during protection window
		if (!snapshotOutputsRef.current) return;
		const snap = snapshotOutputsRef.current;
		const diverged = (snap.fit || "") !== (fitOutput || "") || (snap.tailored || "") !== (tailoredOutput || "") || (snap.judge || "") !== (judgeOutput || "");
		if (diverged) {
			if (isRtDebug()) log('APPLIED.DEMOTE', { cause: 'OUTPUT_DIFF', navId: getNavId() });
				if (Date.now() < protectAppliedUntilRef.current) {
					// Immediate demotion on user-triggered output divergence
					setAppliedChecked(false);
					// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
					setRestoredFromApplied(false);
					setAppliedBanner("Outputs updated – this is a new draft (not yet saved)");
				} else {
					setAppliedChecked(false);
					// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
					setRestoredFromApplied(false);
					setAppliedBanner("Outputs updated – this is a new draft (not yet saved)");
				}
		}
	}, [fitOutput, tailoredOutput, judgeOutput, restoredFromApplied, appliedChecked]);

	// Save/delete snapshot when checkbox toggled (JD-hash model)
	const onAppliedToggle = useCallback(async (checked: boolean) => {
		if (running) return; // don't allow while jobs running
		if (isLoggedIn !== true) { setAppliedBanner("Login required to save an applied snapshot"); return; }
		
		// PESSIMISTIC: Prevent concurrent mutations
		if (savingRef.current) {
			console.warn('[APPLIED TOGGLE] Blocked - mutation already in progress');
			return;
		}
		savingRef.current = true;
		setAppliedSaving(true); // Disable checkbox during request
		
		// PESSIMISTIC: Show "Saving..." banner but do NOT update checkbox yet (wait for server)
		setAppliedBanner(checked ? "Saving..." : "Removing...");
		
		if (isRtDebug()) log(checked ? 'APPLIED.SET' : 'APPLIED.DEMOTE', { cause: checked ? 'USER_TOGGLE_ON' : 'USER_TOGGLE_OFF', navId: getNavId() });
		
		if (!checked) {
			// UNAPPLY FLOW: Delete applied status
			try {
				let hadHash = currentJdHashRef.current;
				
				// If ref is missing but JD text exists, try to recompute the hash
				if (!hadHash && jdText.trim()) {
					if (isRtDebug()) console.log('[UNAPPLY] Ref missing, recomputing jdHash from current JD text');
					hadHash = await makeJdHash(jdText);
					currentJdHashRef.current = hadHash;
				}
				
				if (!hadHash) {
					console.warn('[UNAPPLY] No jdHash available and no JD text to compute from');
					setAppliedBanner("Nothing to unapply");
					savingRef.current = false;
					setAppliedSaving(false);
					return;
				}
				
				if (isRtDebug()) console.log('[UNAPPLY] DELETE /applications/jd/apply', { jdHash: hadHash });
				const deleteStart = performance.now();
				
				// PESSIMISTIC: Await server response
				const deleteResult = await apiClient.delete<{ ok: boolean; jdHash: string; appliedKey: string; changed: boolean; isApplied: boolean }>(
					"/applications/jd/apply", 
					undefined, 
					{ query: { jdHash: hadHash } }
				);
				
				const deleteEnd = performance.now();
				const dbIsApplied = deleteResult.isApplied;
				
				if (isRtDebug()) console.log('[UNAPPLY] Server responded', { 
					duration: `${(deleteEnd - deleteStart).toFixed(2)}ms`, 
					dbIsApplied,
				});
				
				// PESSIMISTIC: Update UI from server response ONLY
				setAppliedChecked(dbIsApplied);
				
				// Save non-applied snapshot if content exists
				if (resumeText.trim() && jdText.trim()) {
					const snap: any = {
						resumeInput: resumeText,
						jdInput: jdText,
						fitOutput: fitOutput || null,
						tailoredOutput: tailoredOutput || null,
						judgeOutput: judgeOutput || null,
						statsMd: statsMd || null,
						knobs: { fitModelLabel, tailorModelLabel, judgeLabel, showJudge },
						modelInfo: modelMeta ? { provider: modelMeta.provider, model: modelMeta.model } : null,
					};
					if (isRtDebug()) {
						const curJdNorm = normalizeText(jdText);
						const snapshotJdNorm = snapshotInputsRef.current?.jd || '';
						const outputsMatch = snapshotInputsRef.current && curJdNorm === snapshotJdNorm;
						const jdHash = await makeJdHash(jdText);
						console.log('[UNAPPLY] POST /applications/jd/save', {
							jdHash: jdHash.substring(0, 16),
							hasOutputs: !!(fitOutput || tailoredOutput || judgeOutput),
							outputsMatchCurrentJD: outputsMatch,
							snapshotJdHash: snapshotJdNorm ? (await stableHash(snapshotJdNorm)).substring(0, 16) : 'none'
						});
				}
				const saveResponse = await apiClient.post<{ ok: boolean; jdHash: string; appliedKey: string; updatedAt: string; isApplied: boolean }>('/applications/jd/save', { jdText: jdText, baseText: resumeText, snapshot: snap });
				if (isRtDebug()) console.log('[UNAPPLY] History snapshot saved');
				
				// Update current_snapshot_key so refresh loads this snapshot
				if (saveResponse.appliedKey) {
					try {
						await apiClient.put('/users/me/current-snapshot', { 
							current_snapshot_key: saveResponse.appliedKey
						});
						if (isRtDebug()) log('CURRENT_SNAPSHOT.UPDATE', { appliedKey: saveResponse.appliedKey, source: 'unapply' });
					} catch (err) {
						console.error('[UNAPPLY] Failed to update current_snapshot_key:', err);
					}
				}
			}
			
			setAppliedBanner(dbIsApplied ? "Failed to unapply" : "Unapplied – snapshot saved");				// Clear refs on successful unapply
				if (!dbIsApplied) {
					currentJdHashRef.current = null;
					currentAppliedKeyRef.current = null;
					snapshotInputsRef.current = null;
					snapshotOutputsRef.current = null;
				}
				
				// Notify History page to refresh
				if (typeof window !== 'undefined') {
					window.dispatchEvent(new CustomEvent('rt_history_refresh'));
					sessionStorage.setItem('rt_history_needs_refresh', Date.now().toString());
				}
				
			} catch (err: any) {
				console.error('[UNAPPLY] Error', err);
				
				// Extract detailed error info
				const status = err?.status || err?.response?.status || 'unknown';
				const detail = err?.detail || err?.message || 'Unknown error';
				const errorSnippet = typeof detail === 'string' ? detail.substring(0, 100) : JSON.stringify(detail).substring(0, 100);
				
				setAppliedBanner(`Failed to unapply (${status}): ${errorSnippet}`);
				// PESSIMISTIC: Do NOT change checkbox on error - keep current state
			} finally {
				savingRef.current = false;
				setAppliedSaving(false);
			}
			return;
		}
		// APPLY FLOW: Save applied snapshot
		try {
			if (!resumeText.trim() || !jdText.trim()) {
				setAppliedBanner("Add both resume and job description first");
				savingRef.current = false;
				setAppliedSaving(false);
				return;
			}
			
			const jdHash = await makeJdHash(jdText);
			currentJdHashRef.current = jdHash;
			
			// Build snapshot object
			const snapshot: any = {
				resumeInput: resumeText,
				jdInput: jdText,
				fitOutput: fitOutput || null,
				tailoredOutput: tailoredOutput || null,
				judgeOutput: judgeOutput || null,
				statsMd: statsMd || null,
				knobs: { fitModelLabel, tailorModelLabel, judgeLabel, showJudge },
				modelInfo: modelMeta ? { provider: modelMeta.provider, model: modelMeta.model } : null,
			};
			
		if (isRtDebug()) {
			const curJdNorm = normalizeText(jdText);
			const snapshotJdNorm = snapshotInputsRef.current?.jd || '';
			const outputsMatch = snapshotInputsRef.current && curJdNorm === snapshotJdNorm;
			const snapshotHash = snapshotJdNorm ? (await stableHash(snapshotJdNorm)).substring(0, 16) : 'none';
			console.log('[APPLY] POST /applications/jd/apply', { 
				jdHash: jdHash.substring(0, 16), 
				hasOutputs: !!(fitOutput || tailoredOutput || judgeOutput),
				outputsMatchCurrentJD: outputsMatch,
				snapshotJdHash: snapshotHash
			});
		}			// PESSIMISTIC: Await server response
			const applyResponse = await apiClient.post<{ ok: boolean; jdHash: string; appliedKey: string; updatedAt: string; isApplied: boolean }>(
				"/applications/jd/apply",
				{
					jdText: jdText,
					baseText: resumeText,
					snapshot,
					consent: true,
				}
			);
			
			const dbIsApplied = applyResponse.isApplied;
			if (isRtDebug()) console.log('[APPLY] Server responded', { 
				ok: applyResponse.ok, 
				appliedKey: applyResponse.appliedKey,
				dbIsApplied,
			});
			
			// PESSIMISTIC: Update UI from server response ONLY
			setAppliedChecked(dbIsApplied);
			
		// Store appliedKey for future operations
		if (applyResponse.appliedKey) {
			currentAppliedKeyRef.current = applyResponse.appliedKey;
			// Update current_snapshot_key so refresh loads this snapshot
			try {
				await apiClient.put('/users/me/current-snapshot', { 
					current_snapshot_key: applyResponse.appliedKey
				});
				if (isRtDebug()) log('CURRENT_SNAPSHOT.UPDATE', { appliedKey: applyResponse.appliedKey, source: 'apply' });
			} catch (err) {
				console.error('[APPLY] Failed to update current_snapshot_key:', err);
			}
		}
		
		// Store snapshot refs if successfully applied
		if (dbIsApplied) {
			snapshotInputsRef.current = { jd: normalizeText(jdText), base: normalizeText(resumeText) };
			snapshotOutputsRef.current = { 
				fit: snapshot.fitOutput || null, 
				tailored: snapshot.tailoredOutput || null, 
				judge: snapshot.judgeOutput || null, 
				statsMd: snapshot.statsMd || null 
			};
			setRestoredFromApplied(true);
		}
		
		setAppliedBanner(dbIsApplied ? "Applied snapshot saved" : "Failed to apply");			// Notify History page to refresh
			if (typeof window !== 'undefined') {
				window.dispatchEvent(new CustomEvent('rt_history_refresh'));
				sessionStorage.setItem('rt_history_needs_refresh', Date.now().toString());
			}
			
		} catch (e: any) {
			console.error('[APPLY] Error', e);
			
			// Extract detailed error info
			const status = e?.status || e?.response?.status || 'unknown';
			const detail = e?.detail || e?.message || 'Unknown error';
			const errorSnippet = typeof detail === 'string' ? detail.substring(0, 100) : JSON.stringify(detail).substring(0, 100);
			
			setAppliedBanner(`Failed to save (${status}): ${errorSnippet}`);
			// PESSIMISTIC: Do NOT change checkbox on error - keep current state
		} finally {
			savingRef.current = false;
			setAppliedSaving(false);
		}
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [running, isLoggedIn, resumeText, jdText, fitOutput, tailoredOutput, judgeOutput, judgeLabel, showJudge, modelMeta]);

		// Clear results on logout: full clear only for auto/401; manual logout preserves inputs & counts but must still clear outputs even if logout happened on another page
		useEffect(() => {
			const onAuth = (e: Event) => {
				const d: any = (e as CustomEvent).detail || {};
				if (String(d?.state || "").toLowerCase() === "logged-out") {
					const reason = String(d?.reason || "").toLowerCase();
					try { localStorage.removeItem('__rt_judge_cache_ephemeral'); } catch {}
					// Always clear outputs first (manual or auto) so if user logs out on Benchmark page then navigates here, stale outputs aren't shown
					clearOutputs({ preserveResultType: reason !== '401' && reason !== 'auto' });
					// Immediately reflect logged-out locally so controls disable without waiting for network
					// Also invalidate any in-flight /users/me checks so they can't flip state back
					try { (window as any).__rt_auth_seq = ((window as any).__rt_auth_seq || 0) + 1; } catch {}
					setIsLoggedIn(false);
					// Clear any pending post-login expectation to avoid keeping controls enabled
					try { localStorage.removeItem("__rt_auth_expect_true"); } catch {}
					// (expectAuth removed) nothing to clear
					setFitRequested(false);
					setTailorRequested(false);
					setAwaitingJudge(false);
					setJudgeRequested(false);
					setJobId(null);
					setJobToken(null);
					setLastCancelJobId(null);
					// Always clear timing stats and related accumulators (privacy + user expectation)
					try { localStorage.removeItem(RESUME_STATS_KEY); localStorage.removeItem(RESUME_STATS_TS_KEY); } catch {}
					setStatsMd("");
					phaseTimesRef.current = {};
					accumulatedTimesRef.current = {} as any;
					if (reason === '401' || reason === 'auto') {
						// Auto / session-expiry full privacy clear also wipes inputs & snapshots
						setResumeText("");
						setJdText("");
						setAppliedBanner("");
						setAppliedChecked(false);
						setRestoredFromApplied(false);
						lastAppliedKeyRef.current = null as any;
						snapshotInputsRef.current = { jd: null as any, base: null as any };
						snapshotOutputsRef.current = { fit: null, tailored: null, judge: null, statsMd: null };
						// STEAM-LIKE: No cookie writes - HistoryClient owns rt_applied_state
					} else {
						// Manual logout: keep inputs; remove snapshot banner & check state
						setAppliedBanner("");
						setAppliedChecked(false);
					}
					setAlert(null);
					try { window.dispatchEvent(new CustomEvent("rt-run", { detail: { running: false } })); } catch {}
				}
			};
			window.addEventListener("rt-auth", onAuth as EventListener);
			return () => window.removeEventListener("rt-auth", onAuth as EventListener);
		}, []);

	// Prefetch averages AFTER auth resolved to avoid 401 spam & wasted work.
	useEffect(() => {
		console.log('[Tooltip Debug] Pricing fetch effect triggered, isLoggedIn:', isLoggedIn, 'authPending:', authPending);
		if (authPending) return; // wait for auth to actually be confirmed by API
		if (isLoggedIn == null) return; // wait until auth probe finishes
		if (isLoggedIn === false) {
			// Logged-out demo snapshots are public SSR data; keep their timing stats
			// so the result panel does not flicker after hydration.
			const hasPublicSnapshotStats = initialSnapshotLoaded && typeof initialStatsMd === "string" && initialStatsMd.trim().length > 0;
			if (statsMd && !hasPublicSnapshotStats) { setStatsMd(""); }
			return; // skip fetching while logged out (requires auth)
		}
		let disposed = false;
		const controller = new AbortController();
		console.log('[Tooltip Debug] Starting pricing data fetch...');
		(async () => {
			try {
				let sum = await api.get<{ averages_by_model?: Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }> }>("/budget/summary", { query: { model_count: 1 }, signal: controller.signal }).catch((err: any) => {
					if (err?.status === 404) return null;
					throw err;
				});
				if (!sum) {
					sum = await api.get<{ averages_by_model?: Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }> }>("/billing/summary", { query: { model_count: 1 }, signal: controller.signal });
				}
				console.log('[Tooltip Debug] /budget/summary response:', sum);
				if (!disposed) setAvgRowsGlobal(Array.isArray(sum?.averages_by_model) ? sum!.averages_by_model! : []);
			} catch (err: any) {
				if (err.name !== 'AbortError' && err?.status !== 404) {
					console.error('[Tooltip Debug] /budget/summary error:', err);
				}
			}
			try {
				const rows = await api.get<Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }>>("/pricing/averages", { query: { scope: "user", model_count: 1 }, signal: controller.signal });
				console.log('[Tooltip Debug] /pricing/averages response:', rows);
				if (!disposed) setAvgRowsUser(rows);
			} catch (err: any) {
				if (err.name !== 'AbortError') {
					console.error('[Tooltip Debug] /pricing/averages error:', err);
				}
			}
		})();
		return () => { disposed = true; controller.abort(); };
	}, [isLoggedIn, authPending, statsMd, initialSnapshotLoaded, initialStatsMd]);	// Recompute pricing tooltips synchronously from cached rows so they update immediately on UI changes
	useEffect(() => {
		// NOTE: Legacy unified modelLabel is no longer authoritative for per-phase pricing.
		// The previous implementation always used modelLabel for both fit & tailor tooltips,
		// so when users changed only the Fit model (fitModelLabel) the Check Job Fit button
		// tooltip showed "No data yet" despite data existing for that model. We now compute
		// per-phase aliases separately.
		const fitAlias = DISPLAY_OPTIONS.find(o => o.label === fitModelLabel)?.alias || DISPLAY_OPTIONS[0].alias;
		const tailorAlias = DISPLAY_OPTIONS.find(o => o.label === tailorModelLabel)?.alias || DISPLAY_OPTIONS[0].alias;
		const providerFit = MODEL_REGISTRY[fitAlias]?.model;
		const providerTailor = MODEL_REGISTRY[tailorAlias]?.model;
		const judgeAlias = (judgeLabel || "").split(" — ")[0] || "GPT-4.1";
		const providerJudge = judgeMeta?.model_id || null;
		const scope = (useMyAvgs && isLoggedIn === true) ? "user" : "global";
		const rows = (scope === "user" ? (avgRowsUser && avgRowsUser.length ? avgRowsUser : null) : null) || avgRowsGlobal || [];
		
		console.log('[Tooltip Debug] Computing tooltips:', {
			fitModelLabel, fitAlias, providerFit,
			tailorModelLabel, tailorAlias, providerTailor,
			judgeLabel, judgeAlias, providerJudge,
			scope, rowCount: rows.length,
			multiModeActive,
			avgRowsUser: avgRowsUser?.length || 0,
			avgRowsGlobal: avgRowsGlobal?.length || 0,
			allModelsInRows: [...new Set(rows.map(r => r.model))],
			sampleRows: rows.slice(0, 5)
		});
		
		const pack = (aliases: string[]) => {
			const set = new Set(aliases.filter(Boolean));
			const filtered = rows.filter((r) => set.has(String(r.model || "")));
			const agg: Record<string, { avg_price_usd: string | number; n: number }> = {};
			for (const r of filtered) {
				const rt = String(r.request_type || "");
				agg[rt] = { avg_price_usd: r.avg_price_usd ?? "0.00", n: Number(r.n || 0) };
			}
			console.log('[Tooltip Debug] pack() result:', { aliases, filtered: filtered.length, agg });
			return agg;
		};
		const fitDict = pack([fitAlias, providerFit]);
		const tailorDict = pack([tailorAlias, providerTailor]);
		const judgeDict = pack([judgeAlias, providerJudge].filter(Boolean) as string[]);
		const fmt = (d: any, rt: string, phase: string) => {
			try {
				const avg = d?.[rt];
				console.log(`[Tooltip Debug] fmt(${phase}, ${rt}):`, { d, avg, hasAvg: !!avg, dataLoaded: rows.length > 0 });
				// If no data loaded yet (both arrays empty), return empty string to hide tooltip
				if (rows.length === 0) return "";
				// If data loaded but no match for this model/phase, show "No data yet"
				if (!avg) return "No data yet";
				const n = Number(avg.n || 0);
				const nShow = n < 100 ? n : 100;
				const price = String(avg.avg_price_usd || "0.00");
				return `Avg of last ${nShow} requests: $${price}`;
			} catch (err) {
				console.error(`[Tooltip Debug] fmt error:`, err);
				return "";
			}
		};
		setFitTip(fmt(fitDict, "fit", "fit"));
		setTailorTip(fmt(tailorDict, "tailor", "tailor"));
		setJudgeTip(fmt(judgeDict, "judge", "judge"));
	}, [fitModelLabel, tailorModelLabel, judgeLabel, useMyAvgs, isLoggedIn, avgRowsUser, avgRowsGlobal, judgeMeta, multiModeActive]);	// Listen for multi-model sidebar broadcasts to capture active selections (independent of legacy window.__rt_* flags)
	useEffect(() => {
		const handler = (e: Event) => {
			try {
				const d: any = (e as CustomEvent).detail || {};
				if (isRtDebug()) console.log('[ResumeTailorClient] Received rt-multi-models:', d);
				setMultiModeActive(!!d.multiMode);
				setMultiFitAliases(Array.isArray(d.multiFit) ? d.multiFit.slice() : []);
				setMultiTailorAliases(Array.isArray(d.multiTailor) ? d.multiTailor.slice() : []);
				setMultiJudgeAliases(Array.isArray(d.multiJudge) ? d.multiJudge.slice() : []);
				
				// Update single-model selections for tooltip updates (converts alias back to legacy label format)
				if (d.singleFit) {
					const opt = DISPLAY_OPTIONS.find(o => o.alias === d.singleFit);
					if (opt) {
						if (isRtDebug()) console.log('[ResumeTailorClient] Updating fitModelLabel to:', opt.label);
						setFitModelLabel(opt.label);
					}
				}
				if (d.singleTailor) {
					const opt = DISPLAY_OPTIONS.find(o => o.alias === d.singleTailor);
					if (opt) {
						if (isRtDebug()) console.log('[ResumeTailorClient] Updating tailorModelLabel to:', opt.label);
						setTailorModelLabel(opt.label);
					}
				}
				if (d.singleJudge) {
					const opt = JUDGE_OPTIONS.find(o => o.label.startsWith(d.singleJudge + ' —'));
					if (opt) {
						if (isRtDebug()) console.log('[ResumeTailorClient] Updating judgeLabel to:', opt.label);
						setJudgeLabel(opt.label);
					}
				}
			} catch {}
		};
		window.addEventListener('rt-multi-models', handler as EventListener);
		return () => window.removeEventListener('rt-multi-models', handler as EventListener);
	}, []);

	// Aggregate multi-model tooltips (benchmark-style without Judge: header; only Models + per-model lines + Total)
	useEffect(() => {
		if (!multiModeActive) {
			setMultiFitTip(""); setMultiTailorTip(""); setMultiJudgeTip(""); return;
		}
		const rows = ((useMyAvgs && isLoggedIn === true) ? (avgRowsUser && avgRowsUser.length ? avgRowsUser : null) : null) || avgRowsGlobal || [];
		if (isRtDebug()) console.log('[ResumeTailorClient] Building tooltips. multiModeActive:', multiModeActive, 'rows:', rows.length, 'multiFitAliases:', multiFitAliases);
		if (!rows.length) { setMultiFitTip(""); setMultiTailorTip(""); setMultiJudgeTip(""); return; }
		const findAvg = (requestType: string, alias: string): { price: number; n: number } | null => {
			const provider = MODEL_REGISTRY[alias]?.model;
			if (isRtDebug()) console.log('[ResumeTailorClient] findAvg:', requestType, alias, 'provider:', provider);
			for (const r of rows) {
				if (String(r.request_type || '') !== requestType) continue;
				const m = String(r.model || '');
				if (m === alias || (provider && m === provider)) {
					const v = Number(String(r.avg_price_usd ?? '0').replace(/[^0-9.]/g, ''));
					const n = Number(r.n || 0);
					if (isRtDebug()) console.log('[ResumeTailorClient] Found match! model:', m, 'price:', v, 'n:', n);
					return Number.isFinite(v) && v > 0 ? { price: v, n } : null;
				}
			}
			if (isRtDebug()) console.log('[ResumeTailorClient] No match found for', alias);
			return null;
		};
		const build = (aliases: string[], requestType: string): string => {
			if (isRtDebug()) console.log('[ResumeTailorClient] build() aliases:', aliases, 'requestType:', requestType);
			if (!aliases || aliases.length === 0) return multiModeActive ? "Select models in the sidebar" : "Select a model in the sidebar"; // no models selected
			if (aliases.length === 1) {
				// Single model in multi-mode: show same format as single-mode
				const result = findAvg(requestType, aliases[0]);
				if (result === null) return "No data yet";
				const nShow = result.n < 100 ? result.n : 100;
				return `Avg of last ${nShow} requests: $${result.price.toFixed(2)}`;
			}
			// Determine canonical ordering based on sidebar model lists
			const canonical = (requestType === 'judge'
				? JUDGE_OPTIONS.map(o => (o.label.includes(' — ') ? o.label.split(' — ')[0] : o.label))
				: DISPLAY_OPTIONS.map(o => o.alias));
			const ordered = canonical.filter(a => aliases.includes(a));
			const lines: string[] = [];
			let total = 0; let allHave = true;
			for (const a of ordered) {
				const result = findAvg(requestType, a);
				if (result == null) { lines.push(`${a}: (no data)`); allHave = false; }
				else { lines.push(`${a}: $${result.price.toFixed(2)}`); total += result.price; }
			}
			if (allHave) lines.push(`Total: $${total.toFixed(2)}`);
			const finalResult = lines.join('\n');
			if (isRtDebug()) console.log('[ResumeTailorClient] build() result:', finalResult);
			return finalResult;
		};
		setMultiFitTip(build(multiFitAliases, 'fit'));
		setMultiTailorTip(build(multiTailorAliases, 'tailor'));
		setMultiJudgeTip(build(multiJudgeAliases, 'judge'));
	}, [multiModeActive, multiFitAliases, multiTailorAliases, multiJudgeAliases, useMyAvgs, isLoggedIn, avgRowsUser, avgRowsGlobal]);

	// SSE attach when we have jobId
	const streamUrl = useMemo(() => {
		if (!jobId) return "";
		const base = getApiBaseUrl();
		return `${base}/jobs/${jobId}/stream`;
	}, [jobId]);

	// Debug flag for job-related console output
	const DEBUG_JOBS = process.env.NEXT_PUBLIC_RT_DEBUG_JOBS === "1";

	// Refresh cached averages so tooltips reflect latest charge immediately
	const refreshAverages = useCallback(async () => {
		try {
			let sum = await api.get<{ averages_by_model?: Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }> }>("/budget/summary", { query: { model_count: 1 } }).catch((err: any) => {
				if (err?.status === 404) return null;
				throw err;
			});
			if (!sum) {
				sum = await api.get<{ averages_by_model?: Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }> }>("/billing/summary", { query: { model_count: 1 } });
			}
			setAvgRowsGlobal(Array.isArray(sum?.averages_by_model) ? sum!.averages_by_model! : []);
		} catch {}
		if (isLoggedIn === true) {
			try {
				const rows = await api.get<Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }>>("/pricing/averages", { query: { scope: "user", model_count: 1 } });
				setAvgRowsUser(rows);
			} catch {}
		}
	}, [isLoggedIn]);

		// Extracted fallback fetch helper (memoized) to reduce allocations in SSE callback
		const fetchJobResultFallback = useCallback(async (jid: string | null, token: string | null) => {
			if (!jid) return null;
			try {
				const headers: Record<string, string> = { "X-Client-Id": xClient };
				if (token) headers["X-Job-Token"] = token;
				const res = await fetch(`${getApiBaseUrl()}/jobs/${jid}/result`, { method: "GET", headers, credentials: "include" });
				if (res.ok) {
					const js = await res.json().catch(() => null);
					return js?.artifact ?? js?.result ?? null;
				}
				if (res.status === 409) return null; // still running
			} catch (e) {
				if (DEBUG_JOBS) { try { console.warn("job result fallback error", e); } catch {} }
			}
			return null;
		}, [xClient, DEBUG_JOBS]);

		useSSE(
			streamUrl,
			useCallback((ev) => {
				if (!ev?.data) return;
				let data: any = null;
				try { data = JSON.parse(ev.data); } catch { return; }
				const status = data?.status;
				if (status === "failed") {
					const normalizeReason = (s: string | null | undefined) => {
						if (!s) return s;
						let t = String(s).trim();
						if (!t) return t;
						// Capitalize first letter
						t = t.charAt(0).toUpperCase() + t.slice(1);
						// Ensure terminal punctuation (., !, ?)
						if (!/[.!?]$/.test(t)) t += '.';
						return t;
					};
					let msg = "Job failed";
					const failCodeRaw = data?.fail_code || data?.code || data?.error || "";
					const failureReason = data?.failure_reason || data?.failureReason;
					const normCode = typeof failCodeRaw === 'string' ? failCodeRaw.toUpperCase() : '';
					if (failureReason) {
						msg = normalizeReason(failureReason) as string;
					} else if (data?.error && !/^FAILED:/.test(data.error)) {
						msg = normalizeReason(data.error) as string;
					} else if (normCode.startsWith('FAILED:STALL_BEFORE_FIRST')) {
						msg = `Model did not start streaming (possible provider stall). Please retry or try another model.`;
					} else if (normCode.includes('TIMEOUT')) {
						msg = `Model timed out before producing output. Try again or pick a faster model.`;
					} else if (normCode.includes('CANCEL')) {
						msg = 'Job canceled';
					} else if (data?.result) {
						msg = normalizeReason(data.result) as string;
					}
					if (msg === 'Job failed') {
						msg = 'Job failed (no details). Please retry; if persistent, contact support.';
					}
					if (lastCancelJobId && jobId === lastCancelJobId) {
						setLastCancelJobId(null);
					} else {
						setAlert({ kind: "error", text: String(msg) });
					}
					setFitRequested(false);
					setTailorRequested(false);
					setAwaitingJudge(false);
					setJudgeRequested(false);
					setJobId(null);
					setJobToken(null);
					return;
				}
				// Handle partial streaming updates during processing
				if (status === "processing" && (data?.partial || data?.text)) {
					const partialText = String(data?.partial || data?.text || "");
					if (partialText) {
						// Update the appropriate output based on current job type
						if (fitRequested) {
							setFitOutput(partialText);
							fitOutputRef.current = partialText;
						} else if (awaitingJudge || judgeRequested) {
							setJudgeOutput(partialText);
							judgeOutputRef.current = partialText;
						} else {
							setTailoredOutput(partialText);
							tailoredOutputRef.current = partialText;
						}
					}
					return;
				}
				if (status !== "completed") return;
				let producedFit: string | null = null; let producedTailor: string | null = null; let producedJudge: string | null = null;
				const applyText = (txt: string) => {
					const val = String(txt || "");
					if (fitRequested) { setFitOutput(val); producedFit = val; fitOutputRef.current = val; }
					else if (awaitingJudge || judgeRequested) { setJudgeOutput(val); producedJudge = val; judgeOutputRef.current = val; }
					else { setTailoredOutput(val); producedTailor = val; tailoredOutputRef.current = val; }
				};
				let text = data?.result;
				if (text == null) {
					fetchJobResultFallback(jobId, jobToken).then((t) => applyText(String(t || "")));
				} else {
					applyText(String(text || ""));
				}
				// Deterministic single-model intended phase based on stored metadata (ignore batchPhase for single runs).
				let intendedPhase: 'fit'|'tailor'|'judge'|null = null;
				const meta = singleRunMetaRef.current;
				if (meta) {
					intendedPhase = meta.intendedResultType;
					// Temporary debug log removed (single-run completion details)
					if (intendedPhase && !autoSwitchLockedRef.current) {
						try { setResultType(intendedPhase); } catch {}
					}
				}
				if ((intendedPhase === 'fit' || fitRequested) && phaseTimesRef.current.fit && !phaseTimesRef.current.fit.end) phaseTimesRef.current.fit.end = performance.now();
				if ((intendedPhase === 'tailor' || tailorRequested || (!fitRequested && !awaitingJudge && !judgeRequested && !intendedPhase)) && phaseTimesRef.current.tailor && !phaseTimesRef.current.tailor.end) phaseTimesRef.current.tailor.end = performance.now();
				if ((intendedPhase === 'judge' || awaitingJudge || judgeRequested) && phaseTimesRef.current.judge && !phaseTimesRef.current.judge.end) phaseTimesRef.current.judge.end = performance.now();
				// Append alias legend for ranking judge after completion (only once)
				if (rankingJudgeRef.current && producedJudge) {
					const merged = producedJudge + (rankingLegendRef.current || "");
					setJudgeOutput(merged);
					judgeOutputRef.current = merged;
					rankingJudgeRef.current = false; // reset
				}
				setFitRequested(false); setTailorRequested(false); setAwaitingJudge(false); setJudgeRequested(false);
				
				// Update snapshot outputs ref to prevent divergence detection from clearing the new results
				if (snapshotOutputsRef.current) {
					snapshotOutputsRef.current = {
						fit: producedFit ?? snapshotOutputsRef.current.fit,
						tailored: producedTailor ?? snapshotOutputsRef.current.tailored,
						judge: producedJudge ?? snapshotOutputsRef.current.judge,
						statsMd: snapshotOutputsRef.current.statsMd
					};
				}
				
				// Post-tick enforcement (only if user hasn't manually switched during run)
				if (intendedPhase && !autoSwitchLockedRef.current) {
					setTimeout(() => { try { setResultType(intendedPhase!); lastForcedResultRef.current = { type: intendedPhase!, ts: performance.now() }; } catch {}; }, 0);
				}
				// Clear metadata after switch attempts
				singleRunMetaRef.current = null;
				// Aggressive reinforcement: schedule two more attempts to override any late heuristic effect.
				if (intendedPhase) {
					[90, 300].forEach(delay => {
						setTimeout(() => { try { if (!autoSwitchLockedRef.current && resultTypeRef.current !== intendedPhase) { setResultType(intendedPhase as any); lastForcedResultRef.current = { type: intendedPhase!, ts: performance.now() }; } } catch {}; }, delay);
					});
				}
				// Fallback enforcement: if primary + post-tick didn't switch.
				if (intendedPhase && !autoSwitchLockedRef.current) {
					setTimeout(() => { try { if (!autoSwitchLockedRef.current && resultTypeRef.current !== intendedPhase) { setResultType(intendedPhase as any); lastForcedResultRef.current = { type: intendedPhase!, ts: performance.now() }; } } catch {}; }, 180);
				}
				setJobId(null); setJobToken(null); setAlert(null);
				setTimeout(() => {
					const fitSecs = phaseTimesRef.current.fit?.end && phaseTimesRef.current.fit?.start ? (phaseTimesRef.current.fit.end - phaseTimesRef.current.fit.start)/1000 : null;
					const tailorSecs = phaseTimesRef.current.tailor?.end && phaseTimesRef.current.tailor?.start ? (phaseTimesRef.current.tailor.end - phaseTimesRef.current.tailor.start)/1000 : null;
					const judgeSecs = phaseTimesRef.current.judge?.end && phaseTimesRef.current.judge?.start ? (phaseTimesRef.current.judge.end - phaseTimesRef.current.judge.start)/1000 : null;
					if (fitSecs != null) accumulatedTimesRef.current.fit = { secs: fitSecs, model: phaseTimesRef.current.fit?.model || modelAlias || "Fit" };
					if (tailorSecs != null) accumulatedTimesRef.current.tailor = { secs: tailorSecs, model: phaseTimesRef.current.tailor?.model || modelAlias || "Tailor" };
					if (judgeSecs != null) { const judgeAlias = (judgeLabel || "").split(" — ")[0] || judgeLabel || "Judge"; accumulatedTimesRef.current.judge = { secs: judgeSecs, model: phaseTimesRef.current.judge?.model || judgeAlias }; }
					try { lastJdSnapshotRef.current = normalizeText(jdText); } catch {}
					const acc = accumulatedTimesRef.current;
					const total = [acc.fit?.secs, acc.tailor?.secs, acc.judge?.secs].filter(v=>typeof v==='number') as number[];
					const totalSum = total.reduce((a,b)=>a+b,0);
					const lines: string[] = [];
					if (totalSum > 0) lines.push(`**Total time:** ${fmtElapsedWhole(totalSum)}`);
				
					if (acc.fit) lines.push(`Fit time (${acc.fit.model}): ${fmtElapsedWhole(acc.fit.secs)}`);
					if (acc.tailor) lines.push(`Tailor time (${acc.tailor.model}): ${fmtElapsedWhole(acc.tailor.secs)}`);
					if (acc.judge) lines.push(`Judge time (${acc.judge.model}): ${fmtElapsedWhole(acc.judge.secs)}`);
					const newStats = lines.join("  \n");
					setStatsMd(newStats);
					(async () => {
						try {
							if (isLoggedIn !== true) return;
							if (!jdText.trim()) return;
							
							const snap: any = {
								resumeInput: resumeText,
								jdInput: jdText,
								fitOutput: (producedFit ?? fitOutputRef.current) || null,
								tailoredOutput: (producedTailor ?? tailoredOutputRef.current) || null,
								judgeOutput: (producedJudge ?? judgeOutputRef.current) || null,
								statsMd: newStats || null,
								knobs: { fitModelLabel, tailorModelLabel, judgeLabel },
								modelInfo: modelMeta ? { provider: modelMeta.provider, model: modelMeta.model } : null
							};
							
							if (isRtDebug()) {
								const jdHash = await makeJdHash(jdText);
								console.log('[JOB_COMPLETE] POST /applications/jd/save', {
									jdHash: jdHash.substring(0, 16),
									hasOutputs: true,
									source: 'job_completion'
								});
							}
							
						const saveResponse = await apiClient.post<{ ok: boolean; appliedKey?: string }>('/applications/jd/save', {
							jdText: jdText,
							baseText: resumeText,
							snapshot: snap
						});							// Update current_snapshot_key so refresh loads this snapshot
							if (saveResponse?.appliedKey) {
								currentAppliedKeyRef.current = saveResponse.appliedKey;
								try {
									await apiClient.put('/users/me/current-snapshot', {
										current_snapshot_key: saveResponse.appliedKey
									});
									if (isRtDebug()) log('CURRENT_SNAPSHOT.UPDATE', {
										appliedKey: saveResponse.appliedKey,
										source: 'job_complete'
									});
								} catch (err) {
									console.error('[JOB_COMPLETE] Failed to update current_snapshot_key:', err);
								}
							}
						} catch (err) {
							console.error('[JOB_COMPLETE] Save failed:', err);
						}
					})();
					// If this JD hash was previously not found (i.e., first creation), show a one-time banner.
					try { if (jdText.trim()) { makeJdHash(jdText).then(h => { if (jdNotFoundRef.current.has(h)) { setAppliedBanner("JD saved (history created)"); jdNotFoundRef.current.delete(h); firstCreationBannerRef.current = { hash: h, until: Date.now() + 5000 }; } }); } } catch {}
				}, 0);
				refreshAverages();
			}, [awaitingJudge, fetchJobResultFallback, fitRequested, judgeRequested, jobId, jobToken, judgeLabel, jdText, lastCancelJobId, modelAlias, modelMeta, refreshAverages, resumeText, tailorRequested]) ,
			useCallback(() => {}, [])
		);


	const validateInputs = useCallback(() => {
		const errs: string[] = [];
		if (!resumeText.trim()) errs.push("Please paste your base resume.");
		if (!jdText.trim()) errs.push("Please paste the job description.");
		if (errs.length) setAlert({ kind: "warning", text: errs.join(" ") });
		return errs.length === 0;
	}, [resumeText, jdText]);

	/**
	 * Validate that a model is selected for a specific role.
	 * Prevents running operations with no model selected (which would default to Sonnet).
	 */
	const validateModelSelection = useCallback((role: "fit" | "tailor" | "judge") => {
		// In multi-model mode, check the alias arrays instead of single labels
		if (multiModeActive) {
			const aliases = role === "fit" ? multiFitAliases : role === "tailor" ? multiTailorAliases : multiJudgeAliases;
			
			if (isRtDebug()) {
				console.log(`[ResumeTailorClient] validateModelSelection(${role}) [MULTI-MODE]:`, {
					aliases,
					count: aliases.length,
					multiModeActive
				});
			}
			
			if (!aliases || aliases.length === 0) {
				const roleDisplay = role === "fit" ? "Fit" : role === "tailor" ? "Tailor" : "Judge";
				
				if (isRtDebug()) {
					console.error(`[ResumeTailorClient] ❌ Validation FAILED for ${role} [MULTI-MODE]: No models selected`);
				}
				
				const debugInfo = `(aliases=${aliases?.length || 0}, multi=YES)`;
				setAlert({ kind: "error", text: `Please select at least one ${roleDisplay} model in the sidebar before running. ${debugInfo}` });
				return false;
			}
			
			if (isRtDebug()) {
				console.log(`[ResumeTailorClient] ✅ Validation passed for ${role} [MULTI-MODE]`);
			}
			
			return true;
		}
		
		// Single-model mode: check labels and meta
		const label = role === "fit" ? fitModelLabel : role === "tailor" ? tailorModelLabel : judgeLabel;
		const meta = role === "fit" ? fitModelMeta : role === "tailor" ? tailorModelMeta : judgeMeta;
		
		// DEBUG: Comprehensive validation logging
		if (isRtDebug()) {
			console.log(`[ResumeTailorClient] validateModelSelection(${role}):`, {
				label,
				labelType: typeof label,
				labelLength: label?.length,
				meta,
				labelExists: !!label,
				metaExists: !!meta,
				allLabels: { fitModelLabel, tailorModelLabel, judgeLabel },
				allMetas: { 
					fit: fitModelMeta,
					tailor: tailorModelMeta,
					judge: judgeMeta
				},
				availableOptions: DISPLAY_OPTIONS.map(o => ({ alias: o.alias, label: o.label }))
			});
		}
		
		if (!label || !meta) {
			const roleDisplay = role === "fit" ? "Fit" : role === "tailor" ? "Tailor" : "Judge";
			
			const metaStr = meta ? ('model' in meta ? meta.model : meta.model_id) : 'NULL';
			const debugInfo = isRtDebug() 
				? `(label=${label || 'NULL'}, meta=${meta ? `${meta.provider}/${metaStr}` : 'NULL'}, multi=NO) | State: fitModelLabel="${fitModelLabel}", tailorModelLabel="${tailorModelLabel}", judgeLabel="${judgeLabel}" | Meta: fit=${JSON.stringify(fitModelMeta)}, tailor=${JSON.stringify(tailorModelMeta)}, judge=${JSON.stringify(judgeMeta)}`
				: '';
			setAlert({ kind: "error", text: `Please select a ${roleDisplay} model in the sidebar before running.${debugInfo ? ' ' + debugInfo : ''}` });
			return false;
		}
		
		if (isRtDebug()) {
			console.log(`[ResumeTailorClient] ✅ Validation passed for ${role}`);
		}
		
		return true;
	}, [multiModeActive, multiFitAliases, multiTailorAliases, multiJudgeAliases, fitModelLabel, tailorModelLabel, judgeLabel, fitModelMeta, tailorModelMeta, judgeMeta]);

	/**
	 * Compute effective model lists for self-contained job submissions.
	 * Returns explicit resolved lists that make each job reproducible regardless of
	 * client cache state. Uses effectiveSelected() to resolve user preferences.
	 * 
	 * Returns empty lists if settings are still loading to avoid submitting incomplete jobs.
	 */
	const computeJobModelLists = useCallback(() => {
		if (!modelSettings || modelSettingsLoading) {
			// Settings not loaded yet - return empty lists
			// Job submissions should wait for settings to load
			return { fit_models: [], tailor_models: [], judge_models: [] };
		}
		
		return {
			fit_models: effectiveSelected("fit", modelSettings),
			tailor_models: effectiveSelected("tailor", modelSettings),
			judge_models: effectiveSelected("judge", modelSettings),
		};
	}, [modelSettings, modelSettingsLoading]);

	// Helpers
	// Use alias model names for pricing/averages (matches Charge.model in backend),
	// and fall back gracefully if averages are missing.
	const ensureBalance = useCallback(async (requestType: string, modelForPricing: string, providerModelId?: string) => {
		try {
			addRunDebugEvent("balance.check.start", { requestType, modelForPricing, providerModelId });
			// Align with Billing: use /budget/summary (global list) to read averages
			const sum = await api.get<{ averages_by_model?: Array<{ request_type?: string; model?: string; avg_price_usd?: string | number; n?: number }> }>("/budget/summary").catch(() => null as any);
			const rows = Array.isArray(sum?.averages_by_model) ? sum!.averages_by_model! : [];
			addRunDebugEvent("balance.summary.loaded", { rows: rows.length, usedBudgetSummary: Boolean(sum) });
			const cand = new Set([modelForPricing, providerModelId || ""]);
			let need = 0;
			for (const r of rows) {
				const m = String(r.model || "");
				if (!cand.has(m)) continue;
				if (String(r.request_type || "") === requestType) {
					need = Number(String(r.avg_price_usd ?? "0").replace(/[^0-9.]/g, ""));
					break;
				}
			}
			const cents = Math.round(need * 100);
			const bal = await api.get<{ balance_cents: number }>("/users/me/balance");
			addRunDebugEvent("balance.check.result", { needUsd: need, needCents: cents, balanceCents: Number(bal?.balance_cents || 0) });
			if (cents > 0 && Number(bal?.balance_cents || 0) < cents) {
				setAlert({ kind: "error", text: "Insufficient Budget credits. Add Budget credits before running a model." });
				return false;
			}
		} catch (err) {
			addRunDebugEvent("balance.check.error", { status: (err as ApiError)?.status, detail: (err as ApiError)?.detail || String(err) });
		}
		return true;
	}, [addRunDebugEvent]);

	const runtimeSecretForProvider = useCallback(async (provider?: string | null) => {
		if (!provider) return null;
		try {
			addRunDebugEvent("byok.local.lookup.start", { provider });
			const localKey = await getLocalByokKey(provider);
			addRunDebugEvent("byok.local.lookup.result", { provider, foundLocalKey: Boolean(localKey), keyLength: localKey ? localKey.length : 0 });
			if (!localKey) return null;
			const resp = await api.post<{ runtime_secret_id?: string }>("/byok/runtime-secrets", {
				provider,
				key: localKey,
				intended_use: "model_run",
			});
			addRunDebugEvent("byok.runtime_secret.result", { provider, hasRuntimeSecretId: Boolean(resp.runtime_secret_id) });
			return resp.runtime_secret_id || null;
		} catch (err) {
			addRunDebugEvent("byok.runtime_secret.error", { provider, status: (err as ApiError)?.status, detail: (err as ApiError)?.detail || String(err) });
			return null;
		}
	}, [addRunDebugEvent]);

	// Actions
	// Track silent session expiry (background 401s) without forcing logout
	const sessionExpiredRef = useRef<boolean>(false);
	useEffect(() => {
		const onAuth = (e: Event) => {
			const d: any = (e as CustomEvent).detail || {};
			if (String(d?.state || "").toLowerCase() === "logged-out" && d?.reason === "401") {
				// Mark flag but do NOT clear inputs/outputs here; stores handle manual logout only
				sessionExpiredRef.current = true;
			}
		};
		window.addEventListener("rt-auth", onAuth as EventListener);
		return () => window.removeEventListener("rt-auth", onAuth as EventListener);
	}, []);
	const onCheckFit = useCallback(async () => {
		// If initiating a new run (not cancelling) clear manual lock so phase can auto-switch at completion.
		if (!fitRequested) autoSwitchLockedRef.current = false;
		// retain lastSingleRunPhaseRef until new single-model phase assigned (removed prior nulling)
		if (sessionExpiredRef.current) {
			setAlert({ kind: "error", text: "Session expired. Please log in again to run jobs. Your text is preserved." });
			return;
		}
		
		// Multi-model FIT batch path (only when explicit flag + >=1 models). Sidebar logic untouched.
		try {
			// window.__rt_fit_multi = { enabled:boolean, models:string[] }
			// @ts-ignore
			const mm = (typeof window !== 'undefined') ? (window as any).__rt_fit_multi : null;
			const multiEnabled = !!mm?.enabled && Array.isArray(mm?.models) && mm.models.length >= 1;
			
			// DEBUG: Log state before validation
			if (isRtDebug()) {
				console.log('[ResumeTailorClient] onCheckFit entry:', {
					fitRequested,
					multiEnabled,
					windowMultiFlag: mm,
					fitModelLabel,
					fitModelMeta,
					tailorModelLabel,
					judgeLabel
				});
			}
			
			// Validate model selection:
			// - For multi-model: check if models array has items
			// - For single-model: check if fitModelMeta exists
			if (!fitRequested) {
				if (multiEnabled) {
					// Multi-model validation already passed (models.length > 1)
					if (isRtDebug()) {
						console.log('[ResumeTailorClient] onCheckFit: multi-model enabled, skipping validateModelSelection');
					}
				} else {
					// Single-model validation
					if (isRtDebug()) {
						console.log('[ResumeTailorClient] onCheckFit: single-mode, calling validateModelSelection("fit")...');
					}
					if (!validateModelSelection("fit")) {
						return;
					}
				}
			}
			
			if (!fitRequested && multiEnabled) {
				const models: string[] = mm.models.slice();
				// Balance check (first model sentinel)
				const first = models[0];
				const providerFirst = MODEL_REGISTRY[first]?.model;
				const okBal = await ensureBalance("fit", first, providerFirst);
				if (!okBal) return;
				setAlert(null);
				// Use flushSync to render React state synchronously BEFORE clearing output
				flushSync(() => {
					setOptimisticRunning('fit');
				});
				// Immediately switch result view to fit now that we have streaming
				setResultType('fit');
				// Clear only Fit so the visible textbox resets; preserve Tailor and Judge outputs
				clearFitOnly();
				// Suppress reconcile refills for a short window to avoid hydration race
				suppressRefillUntilRef.current = Date.now() + 1200;
				if (pendingAccumResetRef.current) { accumulatedTimesRef.current = {}; pendingAccumResetRef.current = false; }
				// Clear previous fit time so total updates immediately, then recompute
				if (accumulatedTimesRef.current.fit) { accumulatedTimesRef.current.fit = undefined as any; }
				recomputeStatsFromAccum();
				phaseTimesRef.current = { ...phaseTimesRef.current, fit: { start: performance.now(), model: first } };
				setBatchPhase('fit');
				await fitBatchRef.current.startBatch('fit', models, async (alias: string) => {
					const meta = MODEL_REGISTRY[alias];
						if (!meta) {
							const err = `Multi-model fit: MODEL_REGISTRY missing entry for alias "${alias}". Available keys: ${Object.keys(MODEL_REGISTRY).join(', ')}`;
							console.error(err);
							setAlert({ kind: "error", text: err });
							throw new Error(err);
						}
						const runtimeSecretId = await runtimeSecretForProvider(meta.provider);
						const r = await api.post<{ job_id: string; access_token: string }>("/fit", {
							resume_text: resumeText,
							jd_text: jdText,
							provider: meta.provider,
							model_id: meta.model,
							runtime_secret_id: runtimeSecretId,
							source_page: "Resume Tailor Multi",
						}, { headers: { "X-Client-Id": xClient, "Idempotency-Key": crypto.randomUUID() } });
					return { jobId: r.job_id };
				});
				setFitRequested(true); // treat as running for existing UI gating
				setOptimisticRunning(null); // Clear optimistic state once batch is started
				return;
			}
		} catch {}
		if (fitRequested) {
			// Cancellation: preserve current view, block auto-switch heuristic.
			autoSwitchLockedRef.current = true;
			// If multi-batch active, cancel all batch jobs instead of single job API.
			if (fitBatchRef.current?.active && fitBatchRef.current.jobs.length >= 1) {
				try { await fitBatchRef.current.cancelBatch(); } catch {}
				setFitRequested(false);
				setBatchPhase(null);
				// On cancel, keep this phase cleared (do not restore old time)
				phaseTimesRef.current.fit = undefined as any;
				accumulatedTimesRef.current.fit = undefined as any;
				recomputeStatsFromAccum();
				return;
			}
			// Single model cancel path
			if (jobId && jobToken) {
				try {
					setLastCancelJobId(jobId);
					await api.post(`/jobs/${jobId}/cancel`, {}, { headers: { "X-Job-Token": jobToken, "X-Client-Id": xClient } });
				} catch {}
			}
			setFitRequested(false);
			setOptimisticRunning(null);
			setJobId(null);
			setJobToken(null);
			// On cancel, keep this phase cleared (do not restore old time)
			phaseTimesRef.current.fit = undefined as any;
			accumulatedTimesRef.current.fit = undefined as any;
			recomputeStatsFromAccum();
			return;
		}
		if (!validateInputs()) return;
	// Pricing must use alias, not provider model id
	const aliasForPricing = DISPLAY_OPTIONS.find((o) => o.label === fitModelLabel)?.alias || DISPLAY_OPTIONS[0].alias;
	const providerId = MODEL_REGISTRY[aliasForPricing]?.model;
	const ok = await ensureBalance("fit", aliasForPricing, providerId);
		if (!ok) return;
		// Clear and submit
	setAlert(null);
		// Use flushSync to render React state synchronously BEFORE Zustand update
		flushSync(() => {
			setOptimisticRunning('fit');
			if (batchPhase) setBatchPhase(null);
		});
		// Now set Zustand state - React updates already rendered with "Processing..."
		setResultType('fit');
		// Clear fit output so "Processing..." message shows until streaming starts
		setFitOutput("");
		// Suppress reconcile refills for a short window to avoid hydration race
		suppressRefillUntilRef.current = Date.now() + 1200;
		// Unlock auto-switch for new single-model fit run (if user hadn't manually locked after this point)
		autoSwitchLockedRef.current = false;
		// Start timing for new fit run (retain previous statsMd so user sees last totals until new run finishes)
	if (pendingAccumResetRef.current) { accumulatedTimesRef.current = {}; pendingAccumResetRef.current = false; }
	// Clear previous fit time so total updates immediately, then recompute
	if (accumulatedTimesRef.current.fit) { accumulatedTimesRef.current.fit = undefined as any; }
	recomputeStatsFromAccum();
		phaseTimesRef.current = { ...phaseTimesRef.current, fit: { start: performance.now(), model: (DISPLAY_OPTIONS.find(o=>o.label===fitModelLabel)?.alias || fitModelLabel) } };
		globalRunCounterRef.current += 1;
		singleRunMetaRef.current = { runId: globalRunCounterRef.current, intendedResultType: 'fit', manualVersionAtStart: manualChangeVersionRef.current };
			try {
			// Compute explicit model lists for reproducibility
			const modelLists = computeJobModelLists();
			addRunDebugEvent("submit.fit.start", {
				provider: fitModelMeta!.provider,
				modelId: fitModelMeta!.model,
				clientId: xClient,
				resumeLen: resumeText.length,
				jdLen: jdText.length,
				fitModels: modelLists.fit_models,
			});
			const runtimeSecretId = await runtimeSecretForProvider(fitModelMeta!.provider);
			addRunDebugEvent("submit.fit.byok_ready", { hasRuntimeSecretId: Boolean(runtimeSecretId), provider: fitModelMeta!.provider });
			const r = await api.post<{ job_id: string; access_token: string }>("/fit", {
				resume_text: resumeText,
				jd_text: jdText,
				provider: fitModelMeta!.provider,
				model_id: fitModelMeta!.model,
				runtime_secret_id: runtimeSecretId,
				source_page: "Resume Tailor",
				fit_models: modelLists.fit_models, // Explicit model list for reproducibility
				}, { headers: { "X-Client-Id": xClient, "Idempotency-Key": crypto.randomUUID() } });
			addRunDebugEvent("submit.fit.success", { jobId: r.job_id, hasAccessToken: Boolean(r.access_token) });
			setJobId(r.job_id);
			setJobToken(r.access_token);
			setFitRequested(true); // Set after successful job submission
			setOptimisticRunning(null); // Clear optimistic state once job is started
		} catch (e) {
			const err = e as ApiError;
			addRunDebugEvent("submit.fit.error", { status: err.status, detail: err.detail || err.message || String(e) });
			setOptimisticRunning(null); // Clear optimistic state on error
			if (err.status === 401) { sessionExpiredRef.current = true; setAlert({ kind: "error", text: "Session expired. Log in again to continue." }); return; }
			if (err.status === 402) setAlert({ kind: "error", text: submission402Message(err) });
			else {
				const detail = err.detail || err.message || '';
				const errorMsg = detail ? `Failed to submit fit: ${detail}` : "Failed to submit fit. Please try again or contact support if the issue persists.";
				setAlert({ kind: "error", text: errorMsg });
			}
			// On error, clear the fitRequested flag since job didn't start
			setFitRequested(false);
		}
	}, [fitRequested, jobId, jobToken, resumeText, jdText, fitModelMeta, xClient, validateInputs, ensureBalance, fitModelLabel, addRunDebugEvent, runtimeSecretForProvider]);

	const onTailor = useCallback(async () => {
		if (!tailorRequested && !awaitingJudge) autoSwitchLockedRef.current = false;
		if (sessionExpiredRef.current) {
			setAlert({ kind: "error", text: "Session expired. Please log in again to run jobs. Your text is preserved." });
			return;
		}
		if (tailorRequested || awaitingJudge) {
			// Cancellation path
			autoSwitchLockedRef.current = true;
			setOptimisticRunning(null); // Clear optimistic state on cancel
			// Cancel (multi-batch or single)
			if (fitBatchRef.current?.active && batchPhase==='tailor' && fitBatchRef.current.jobs.length >= 1) {
				try { await fitBatchRef.current.cancelBatch(); } catch {}
				setTailorRequested(false);
				setAwaitingJudge(false);
				setBatchPhase(null);
				// On cancel, clear tailor time and recompute
				phaseTimesRef.current.tailor = undefined as any;
				accumulatedTimesRef.current.tailor = undefined as any;
				recomputeStatsFromAccum();
				return;
			}
			// Single job cancel fallback
			if (jobId) {
				try {
					setLastCancelJobId(jobId);
					await api.post(`/jobs/${jobId}/cancel`, {}, { headers: { "X-Client-Id": xClient, ...(jobToken ? { "X-Job-Token": jobToken } : {}) } });
				} catch {}
			}
			setTailorRequested(false);
			setAwaitingJudge(false);
			setJobId(null);
			setJobToken(null);
			// On cancel, clear tailor time and recompute
			phaseTimesRef.current.tailor = undefined as any;
			accumulatedTimesRef.current.tailor = undefined as any;
			recomputeStatsFromAccum();
			return;
		}
		if (!validateInputs()) return;
		
		// Multi-model TAILOR batch path
		try {
			// window.__rt_tailor_multi = { enabled:boolean, models:string[] }
			// @ts-ignore
			const mm = (typeof window !== 'undefined') ? (window as any).__rt_tailor_multi : null;
			const multiEnabled = !!mm?.enabled && Array.isArray(mm?.models) && mm.models.length >= 1;
			
			// Validate model selection:
			// - For multi-model: check if models array has items
			// - For single-model: check if tailorModelMeta exists
			if (multiEnabled) {
				// Multi-model validation already passed (models.length > 1)
			} else {
				// Single-model validation
				if (!validateModelSelection("tailor")) {
					return;
				}
			}
			
			if (!tailorRequested && multiEnabled) {
				if (!requestGroupRef.current) requestGroupRef.current = makeGroupId();
				const models: string[] = mm.models.slice();
				lastTailorBatchSizeRef.current = models.length;
				// Balance check (first model sentinel)
				const first = models[0];
				const providerFirst = MODEL_REGISTRY[first]?.model;
				const okBal = await ensureBalance("tailor", first, providerFirst);
				if (!okBal) return;
				setAlert(null);
				// Use flushSync to render React state synchronously BEFORE Zustand update
				flushSync(() => {
					setOptimisticRunning('tailor');
				});
				// Now set Zustand state - React updates already rendered with "Processing..."
				setResultType('tailor');
				setTailoredOutput("");
				if (pendingAccumResetRef.current) { accumulatedTimesRef.current = {}; pendingAccumResetRef.current = false; }
				// Clear previous tailor time so total updates immediately, then recompute
				if (accumulatedTimesRef.current.tailor) { accumulatedTimesRef.current.tailor = undefined as any; }
				recomputeStatsFromAccum();
				phaseTimesRef.current = { ...phaseTimesRef.current, tailor: { start: performance.now(), model: first } };
				setBatchPhase('tailor');
				await fitBatchRef.current.startBatch('tailor', models, async (alias: string) => {
					const meta = MODEL_REGISTRY[alias];
						if (!meta) {
							console.warn("tailor multi: missing MODEL_REGISTRY entry for alias", alias);
							throw new Error("Unknown model alias: " + alias);
						}
						const runtimeSecretId = await runtimeSecretForProvider(meta.provider);
						const r = await api.post<{ job_id: string; access_token: string }>("/jobs", {
							resume_text: resumeText,
							jd_text: jdText,
							provider: meta.provider,
							model_id: meta.model,
							runtime_secret_id: runtimeSecretId,
							source_page: "Resume Tailor Multi",
							total_models_selected: models.length,
						request_group_id: requestGroupRef.current,
					}, { headers: { "X-Client-Id": xClient, "Idempotency-Key": crypto.randomUUID() } });
					return { jobId: r.job_id };
				});
				setTailorRequested(true);
				setOptimisticRunning(null); // Clear optimistic state once batch is started
				return;
			}
		} catch {}
		// Clear prior
		setAlert(null);
		
		// Use flushSync to render React state synchronously BEFORE Zustand update
		flushSync(() => {
			setOptimisticRunning('tailor');
		});
		// Now set Zustand state - React updates already rendered with "Processing..."
		setResultType('tailor');
		setTailoredOutput("");
		setJudgeOutput("");
		
		// Single-model path: check balance
		const rt = "tailor";
		const aliasForPricing = DISPLAY_OPTIONS.find((o) => o.label === tailorModelLabel)?.alias;
		if (!aliasForPricing) {
			setAlert({ kind: "error", text: "Invalid model selection. Please select a model in the sidebar." });
			return;
		}
		const providerId = MODEL_REGISTRY[aliasForPricing]?.model;
		const ok = await ensureBalance(rt, aliasForPricing, providerId);
		if (!ok) return;
		
		// Start timing for tailor (+optional judge) run; keep existing statsMd visible until completion
	if (pendingAccumResetRef.current) { accumulatedTimesRef.current = {}; pendingAccumResetRef.current = false; }
	// Clear previous tailor time so total updates immediately, then recompute
	if (accumulatedTimesRef.current.tailor) { accumulatedTimesRef.current.tailor = undefined as any; }
	recomputeStatsFromAccum();
		phaseTimesRef.current = { ...phaseTimesRef.current, tailor: { start: performance.now(), model: (DISPLAY_OPTIONS.find(o=>o.label===tailorModelLabel)?.alias || tailorModelLabel) } };
		globalRunCounterRef.current += 1;
		singleRunMetaRef.current = { runId: globalRunCounterRef.current, intendedResultType: 'tailor', manualVersionAtStart: manualChangeVersionRef.current };
			try {
			// Try synchronous submit to surface 402 first
			addRunDebugEvent("submit.tailor.start", {
				provider: tailorModelMeta!.provider,
				modelId: tailorModelMeta!.model,
				clientId: xClient,
				resumeLen: resumeText.length,
				jdLen: jdText.length,
			});
			const runtimeSecretId = await runtimeSecretForProvider(tailorModelMeta!.provider);
			addRunDebugEvent("submit.tailor.byok_ready", { hasRuntimeSecretId: Boolean(runtimeSecretId), provider: tailorModelMeta!.provider });
			const r = await api.post<{ job_id: string; access_token: string }>("/jobs", {
				resume_text: resumeText,
				jd_text: jdText,
				provider: tailorModelMeta!.provider,
				model_id: tailorModelMeta!.model,
				runtime_secret_id: runtimeSecretId,
				source_page: "Resume Tailor",
				total_models_selected: 1,
				request_group_id: requestGroupRef.current,
			}, { headers: { "X-Client-Id": xClient, "Idempotency-Key": crypto.randomUUID() } });
			addRunDebugEvent("submit.tailor.success", { jobId: r.job_id, hasAccessToken: Boolean(r.access_token) });
			setJobId(r.job_id);
			setJobToken(r.access_token);
				setTailorRequested(true);
				setOptimisticRunning(null); // Clear optimistic state once job is started
		} catch (e) {
			const err = e as ApiError;
			addRunDebugEvent("submit.tailor.error", { status: err.status, detail: err.detail || err.message || String(e) });
			setOptimisticRunning(null); // Clear optimistic state on error
			if (err.status === 401) { sessionExpiredRef.current = true; setAlert({ kind: "error", text: "Session expired. Log in again to continue." }); return; }
			if (err.status === 402) setAlert({ kind: "error", text: submission402Message(err) });
			else {
				const detail = err.detail || err.message || '';
				const errorMsg = detail ? `Failed to submit tailor job: ${detail}` : "Failed to submit tailor job. Please try again or contact support if the issue persists.";
				setAlert({ kind: "error", text: errorMsg });
			}
		}
	}, [tailorRequested, awaitingJudge, jobId, jobToken, resumeText, jdText, tailorModelMeta, judgeMeta, xClient, validateInputs, ensureBalance, tailorModelLabel, batchPhase, addRunDebugEvent, runtimeSecretForProvider]);

	const onJudge = useCallback(async () => {
		if (!judgeRequested) autoSwitchLockedRef.current = false;
		if (sessionExpiredRef.current) { setAlert({ kind: "error", text: "Session expired. Please log in again to run jobs." }); return; }
		if (judgeRequested) {
			// Cancellation
			autoSwitchLockedRef.current = true;
			setOptimisticRunning(null); // Clear optimistic state on cancel
			// Multi-batch judge cancel
			if (fitBatchRef.current?.active && batchPhase==='judge' && fitBatchRef.current.jobs.length >= 1) {
				try { await fitBatchRef.current.cancelBatch(); } catch {}
				setJudgeRequested(false); setBatchPhase(null); return;
			}
			if (jobId && jobToken) {
				try {
					setLastCancelJobId(jobId);
					await api.post(`/jobs/${jobId}/cancel`, {}, { headers: { "X-Job-Token": jobToken, "X-Client-Id": xClient } });
				} catch {}
			}
			setJudgeRequested(false);
			if (batchPhase === 'judge') setBatchPhase(null);
			setJobId(null); setJobToken(null);
			// On cancel, clear judge time and recompute
			phaseTimesRef.current.judge = undefined as any;
			accumulatedTimesRef.current.judge = undefined as any;
			recomputeStatsFromAccum();
			return;
		}
		if (!validateInputs()) return;
		
		setAlert(null);
		
		// Use flushSync to render React state synchronously BEFORE Zustand update
		flushSync(() => {
			setOptimisticRunning('judge');
		});
		// Now set Zustand state - React updates already rendered with "Processing..."
		setResultType('judge');
		setJudgeOutput("");
		
		// Derive number of upstream tailored outputs once (used in both multi- and single-model judge requests)
		const inputModels = lastTailorBatchSizeRef.current || 1;
		// Multi-model JUDGE path now routes to /benchmark/rank for unified HMAC aliasing + ranking.
		try {
			// @ts-ignore
			const mm = (typeof window !== 'undefined') ? (window as any).__rt_judge_multi : null;
			// @ts-ignore
			const tm = (typeof window !== 'undefined') ? (window as any).__rt_tailor_multi : null;
			// We consider multi-variant judging enabled if either: (a) >=1 judge models selected OR (b) >=1 tailor variants exist (even single judge model).
			const judgeCheckboxCount = (Array.isArray(mm?.models) ? mm.models.length : 0);
			const judgeMultiActive = !!mm?.enabled && judgeCheckboxCount >= 1;
			const tailorMultiActive = !!tm?.enabled && Array.isArray(tm?.models) && tm.models.length >= 1;
			const multiEnabled = judgeMultiActive || tailorMultiActive;
			
			// Validate model selection:
			// - For multi-model: check if models array has items (already checked above)
			// - For single-model: check if judgeMeta exists
			if (!multiEnabled) {
				// Single-model validation only when NOT in multi-model mode
				if (!validateModelSelection("judge")) {
					return;
				}
			}
			
			// If exactly one judge checkbox is selected, prefer it over radio selection
			const singleJudgeCheckbox = (judgeCheckboxCount === 1) ? mm?.models?.[0] : null;
			if (!judgeRequested && multiEnabled) {
				if (!requestGroupRef.current) requestGroupRef.current = makeGroupId();
				if (tailorMultiActive && judgeMultiActive) {
					// Case: multiple tailored variants AND multiple judge models -> run one ranking job per judge model.
					const candidateAliases: string[] = tm.models.slice();
					// Build candidates map once
					const buildCandidates = (): Record<string,string> => {
						const candidates: Record<string,string> = {};
						try {
							const md = (tailoredOutput || "");
							const lines = md.split(/\r?\n/);
							let current: string | null = null; let buf: string[] = [];
							const flush = () => { if (current && !candidates[current]) { candidates[current] = buf.join("\n").trim(); } buf = []; };
							for (const line of lines) {
								const m = /^###\s+(.+)\s*$/.exec(line);
								if (m) { const heading = m[1].trim(); const matched = candidateAliases.find(a => heading.toLowerCase().startsWith(a.toLowerCase())); if (matched) { flush(); current = matched; continue; } }
								if (current) buf.push(line);
							}
							flush();
						} catch {}
						return candidates;
					};
					const judgeAliases: string[] = mm.models.slice();
					const firstJudge = judgeAliases[0];
					const firstMeta = MODEL_REGISTRY[firstJudge];
					const okBal = await ensureBalance("judge", firstJudge, firstMeta?.model);
					if (!okBal) return;
					setAlert(null);
					// Use flushSync to render React state synchronously BEFORE Zustand update
					flushSync(() => {
						setOptimisticRunning('judge');
					});
					// Now set Zustand state - React updates already rendered with "Processing..."
					setResultType('judge');
					setJudgeOutput("");
					// Clear previous judge time so total updates immediately, then recompute
					if (accumulatedTimesRef.current.judge) { accumulatedTimesRef.current.judge = undefined as any; }
					recomputeStatsFromAccum();
					if (pendingAccumResetRef.current) { accumulatedTimesRef.current = {}; pendingAccumResetRef.current = false; }
					phaseTimesRef.current = { ...phaseTimesRef.current, judge: { start: performance.now(), model: firstJudge } };
					setBatchPhase('judge');
					const baseCandidates = buildCandidates();
					// Dedupe by normalized text; if < 2 unique, pivot to per-model /judge jobs
					const nonEmptyBase = Object.fromEntries(Object.entries(baseCandidates).filter(([_, v]) => typeof v === 'string' && v.trim()));
					const norm = (s: string) => s.replace(/\s+/g, ' ').trim();
					const uniqSet = new Set<string>(Object.values(nonEmptyBase).map(v => norm(v as string)));
					if (uniqSet.size < 2) {
						const singleText = (Object.values(nonEmptyBase)[0] as string | undefined) || (tailoredOutput || '').trim();
						try { console.debug('[judge->multi-pivot-judge]', { judgeAliases, textLen: singleText.length }); } catch {}
							await fitBatchRef.current.startBatch('judge', judgeAliases, async (alias: string) => {
								const meta = MODEL_REGISTRY[alias];
								if (!meta) { console.warn('judge multi: missing MODEL_REGISTRY entry', alias); throw new Error('Unknown judge alias: ' + alias); }
								const runtimeSecretId = await runtimeSecretForProvider(meta.provider);
								const r = await api.post<{ job_id: string; access_token: string }>("/judge", {
									resume_text: resumeText,
									jd_text: jdText,
									candidate_text: singleText,
									judge_provider: meta.provider,
									judge_model_id: meta.model,
									runtime_secret_id: runtimeSecretId,
									source_page: 'Resume Tailor Multi',
								total_models_selected: judgeAliases.length,
								input_models: inputModels,
								request_group_id: requestGroupRef.current,
							}, { headers: { 'X-Client-Id': `${xClient}:${alias}`, 'Idempotency-Key': crypto.randomUUID() } });
							return { jobId: r.job_id };
						});
						setJudgeRequested(true);
						setOptimisticRunning(null); // Clear optimistic state once batch is started
						return;
					}
					try { console.debug('[judge->multi-rank] candidates extracted', Object.fromEntries(Object.entries(baseCandidates).map(([k,v])=>[k, v.length]))); } catch {}
						await fitBatchRef.current.startBatch('judge', judgeAliases, async (alias: string) => {
							const meta = MODEL_REGISTRY[alias];
							if (!meta) { console.warn('judge multi: missing MODEL_REGISTRY entry', alias); throw new Error('Unknown judge alias: ' + alias); }
							const runtimeSecretId = await runtimeSecretForProvider(meta.provider);
							const rankResp = await api.post<{ job_id: string; access_token: string }>("/benchmark/rank", {
								base_resume: resumeText,
								jd_text: jdText,
								candidates: baseCandidates,
								judge_provider: meta.provider,
								judge_model_id: meta.model,
								runtime_secret_id: runtimeSecretId,
								source_page: 'Resume Tailor Multi',
						}, { headers: { 'X-Client-Id': `${xClient}:${alias}`, 'Idempotency-Key': crypto.randomUUID() } });
						return { jobId: rankResp.job_id };
					});
					setJudgeRequested(true);
					setOptimisticRunning(null); // Clear optimistic state once batch is started
					return;
				}
				if (tailorMultiActive) {
					// Multi-tailor variants: use ranking path (single judge model over multiple candidate resumes)
					const modelAliases: string[] = tm.models.slice();
					const firstAlias = modelAliases[0];
					// Use checkbox-selected judge model if exactly one is checked; otherwise fall back to radio's judgeMeta
					const judgeAliasEffective = singleJudgeCheckbox || firstAlias; // firstAlias name here is just used for timing label; meta derives from judge model
					const judgeMetaEffective = singleJudgeCheckbox ? MODEL_REGISTRY[singleJudgeCheckbox] : MODEL_REGISTRY[firstAlias];
					const okBal = await ensureBalance("judge", judgeAliasEffective, judgeMetaEffective?.model);
					if (!okBal) return;
					const candidates: Record<string,string> = {};
					try {
						const md = (tailoredOutput || "");
						const lines = md.split(/\r?\n/);
						let current: string | null = null; let buf: string[] = [];
						const flush = () => { if (current && !candidates[current]) { candidates[current] = buf.join("\n").trim(); } buf = []; };
						for (const line of lines) {
							const m = /^###\s+(.+)\s*$/.exec(line);
							if (m) { const heading = m[1].trim(); const matched = modelAliases.find(a => heading.toLowerCase().startsWith(a.toLowerCase())); if (matched) { flush(); current = matched; continue; } }
							if (current) buf.push(line);
						}
						flush();
					} catch {}
					// Dedupe by normalized text; if < 2 unique, skip ranking and let single-model path handle below
					const nonEmpty = Object.fromEntries(Object.entries(candidates).filter(([_, v]) => typeof v === 'string' && v.trim()));
					const norm2 = (s: string) => s.replace(/\s+/g, ' ').trim();
					const uniq2 = new Set<string>(Object.values(nonEmpty).map(v => norm2(v as string)));
					if (uniq2.size < 2) {
						try { console.debug('[judge->rank pivot skipped: single unique candidate]'); } catch {}
						// Fall through to existing single-model path below (no returns/state changes here)
					} else {
						setAlert(null);
						// Use flushSync to render React state synchronously BEFORE clearing output
						flushSync(() => {
							setOptimisticRunning('judge');
						});
						setResultType('judge');
						setJudgeOutput("");
						// Clear previous judge time so total updates immediately, then recompute
						if (accumulatedTimesRef.current.judge) { accumulatedTimesRef.current.judge = undefined as any; }
						recomputeStatsFromAccum();
						if (pendingAccumResetRef.current) { accumulatedTimesRef.current = {}; pendingAccumResetRef.current = false; }
						phaseTimesRef.current = { ...phaseTimesRef.current, judge: { start: performance.now(), model: firstAlias } };
						setBatchPhase('judge');
					try { console.debug('[judge->rank] candidates extracted', Object.fromEntries(Object.entries(candidates).map(([k,v])=>[k, v.length]))); } catch {}
						const runtimeSecretId = await runtimeSecretForProvider((singleJudgeCheckbox ? judgeMetaEffective?.provider : judgeMeta!.provider));
						const rankResp = await api.post<{ job_id: string; access_token: string }>("/benchmark/rank", {
						base_resume: resumeText,
						jd_text: jdText,
						candidates,
							judge_provider: (singleJudgeCheckbox ? judgeMetaEffective?.provider : judgeMeta!.provider),
							judge_model_id: (singleJudgeCheckbox ? judgeMetaEffective?.model : judgeMeta!.model_id),
						runtime_secret_id: runtimeSecretId,
						source_page: "Resume Tailor Multi",
					}, { headers: { "X-Client-Id": xClient, "Idempotency-Key": crypto.randomUUID() } });
					setJobId(rankResp.job_id); setJobToken(rankResp.access_token); setJudgeRequested(true);
					setOptimisticRunning(null); // Clear optimistic state once job is started
					return;
					}
				}
				if (judgeMultiActive) {
					// Multi judge models only (single tailored candidate): revert to per-model /judge jobs
					const judgeAliases: string[] = mm.models.slice();
					const first = judgeAliases[0];
					const providerFirst = MODEL_REGISTRY[first]?.model;
					const okBal = await ensureBalance("judge", first, providerFirst);
					if (!okBal) return;
					setAlert(null);
					// Use flushSync to render React state synchronously BEFORE Zustand update
					flushSync(() => {
						setOptimisticRunning('judge');
					});
					// Now set Zustand state - React updates already rendered with "Processing..."
					setResultType('judge');
					setJudgeOutput("");
					// Clear previous judge time so total updates immediately, then recompute
					if (accumulatedTimesRef.current.judge) { accumulatedTimesRef.current.judge = undefined as any; }
					recomputeStatsFromAccum();
					if (pendingAccumResetRef.current) { accumulatedTimesRef.current = {}; pendingAccumResetRef.current = false; }
					phaseTimesRef.current = { ...phaseTimesRef.current, judge: { start: performance.now(), model: first } };
					setBatchPhase('judge');
					await fitBatchRef.current.startBatch('judge', judgeAliases, async (alias: string) => {
						const meta = MODEL_REGISTRY[alias];
						if (!meta) { console.warn('judge multi: missing MODEL_REGISTRY entry', alias); throw new Error('Unknown judge alias: ' + alias); }
						const runtimeSecretId = await runtimeSecretForProvider(meta.provider);
						const r = await api.post<{ job_id: string; access_token: string }>("/judge", {
							resume_text: resumeText,
							jd_text: jdText,
							candidate_text: (tailoredOutput || ''),
							judge_provider: meta.provider,
							judge_model_id: meta.model,
							runtime_secret_id: runtimeSecretId,
							source_page: 'Resume Tailor Multi',
							total_models_selected: judgeAliases.length,
							input_models: inputModels,
							request_group_id: requestGroupRef.current,
						}, { headers: { 'X-Client-Id': `${xClient}:${alias}`, 'Idempotency-Key': crypto.randomUUID() } });
						return { jobId: r.job_id };
					});
					setJudgeRequested(true);
					setOptimisticRunning(null); // Clear optimistic state once batch is started
					return;
				}
			}
		} catch {}
		// --- existing single-model path below unchanged ---
		const cand = (tailoredOutput || "").trim();
		if (!cand) { setAlert({ kind: "error", text: "No tailored resume found. Run Tailor first." }); return; }
		// Prefer single checkbox selection over radio when exactly one judge model is checked
		// @ts-ignore
		const __mmSingle = (typeof window !== 'undefined') ? (window as any).__rt_judge_multi : null;
		const __single = (Array.isArray(__mmSingle?.models) && __mmSingle.models.length === 1) ? __mmSingle.models[0] : null;
		const judgeAliasForPricing = (__single || (judgeLabel || "").split(" — ")[0] || judgeLabel || "Judge");
		const judgeModelForPricing = __single ? MODEL_REGISTRY[__single]?.model : (judgeMeta ? judgeMeta.model_id : null);
		
		// If we still don't have a valid model, show error
		if (!judgeModelForPricing) {
			setAlert({ kind: "error", text: "Please select a Judge model in the sidebar before running." });
			return;
		}
		
		const ok = await ensureBalance("judge", judgeAliasForPricing, judgeModelForPricing);
		if (!ok) return;
		setJudgeOutput("");
		// Clear previous judge time so total updates immediately, then recompute
		if (accumulatedTimesRef.current.judge) { accumulatedTimesRef.current.judge = undefined as any; }
		recomputeStatsFromAccum();
		if (pendingAccumResetRef.current) { accumulatedTimesRef.current = {}; pendingAccumResetRef.current = false; }
		phaseTimesRef.current = { ...phaseTimesRef.current, judge: { start: performance.now(), model: judgeAliasForPricing } };
		globalRunCounterRef.current += 1;
		singleRunMetaRef.current = { runId: globalRunCounterRef.current, intendedResultType: 'judge', manualVersionAtStart: manualChangeVersionRef.current };
		try {
			const providerForJudge = __single ? MODEL_REGISTRY[__single]?.provider : judgeMeta?.provider;
			const modelIdForJudge = __single ? MODEL_REGISTRY[__single]?.model : judgeMeta?.model_id;
			const runtimeSecretId = await runtimeSecretForProvider(providerForJudge);
			
			try { console.debug('[judge] single dispatch', { judgeLabel: judgeAliasForPricing, provider: providerForJudge, model_id: modelIdForJudge }); } catch {}
			const r = await api.post<{ job_id: string; access_token: string }>("/judge", {
				resume_text: resumeText,
				jd_text: jdText,
				candidate_text: cand,
						judge_provider: providerForJudge,
						judge_model_id: modelIdForJudge,
				runtime_secret_id: runtimeSecretId,
				source_page: "Resume Tailor",
				total_models_selected: 1,
				input_models: inputModels,
				request_group_id: requestGroupRef.current,
			}, { headers: { "X-Client-Id": xClient, "Idempotency-Key": crypto.randomUUID() } });
			setJobId(r.job_id); setJobToken(r.access_token); setJudgeRequested(true);
			setOptimisticRunning(null); // Clear optimistic state once job is started
		} catch (e) {
			const err = e as ApiError;
			setOptimisticRunning(null); // Clear optimistic state on error
			if (err.status === 401) { sessionExpiredRef.current = true; setAlert({ kind: "error", text: "Session expired. Log in again to continue." }); return; }
			if (err.status === 402) { setAlert({ kind: "error", text: submission402Message(err) }); return; }
			// Attempt to extract informative backend detail (FastAPI error JSON {detail})
			let detail: string | undefined;
			try {
				// @ts-ignore shape from ApiError implementation
				detail = (err?.data?.detail || err?.message || "").toString();
			} catch {}
			const fallback = "Judge submission failed. Ensure you have at least one completed tailored resume and sufficient balance.";
			// Normalize known precondition keys
			if (detail && /precondition_failed|no tailored resumes|tailor first/i.test(detail)) {
				setAlert({ kind: "error", text: detail });
			} else if (detail) {
				setAlert({ kind: "error", text: detail });
			} else {
				setAlert({ kind: "error", text: fallback });
			}
		}
	}, [judgeRequested, jobId, jobToken, resumeText, jdText, tailoredOutput, judgeMeta, xClient, validateInputs, ensureBalance, judgeLabel, batchPhase]);

	// Cancel any in-flight job if user navigates away (component unmounts)
	// Use refs to avoid cleanup firing when state changes (only on actual unmount)
	const activeJobRef = useRef<{ jobId: string; jobToken: string | null } | null>(null);
	useEffect(() => {
		if ((fitRequested || tailorRequested || awaitingJudge || judgeRequested) && jobId) {
			activeJobRef.current = { jobId, jobToken };
		} else {
			activeJobRef.current = null;
		}
	}, [fitRequested, tailorRequested, awaitingJudge, judgeRequested, jobId, jobToken]);

	useEffect(() => {
		return () => {
			try {
				const active = activeJobRef.current;
				if (active) {
					const headers: Record<string, string> = { "X-Client-Id": xClient };
					if (active.jobToken) headers["X-Job-Token"] = active.jobToken;
					// Fire-and-forget cancellation; ignore result
					fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/jobs/${active.jobId}/cancel`, { method: "POST", headers, credentials: "include" }).catch(() => {});
				}
			} catch {}
		};
	}, [xClient]); // Only xClient in deps - cleanup only runs on unmount or xClient change

	// Hydration guard to avoid SSR/client text mismatch (e.g. Tailor My Resume vs Tailor and Judge)
	const [hydrated, setHydrated] = useState(false);
	useEffect(() => { setHydrated(true); }, []);

	// ---------------- Multi-Model FIT Batch (Prompt 3) ----------------
	// Single hook reused for all phases (fit/tailor/judge) batch management.
	const fitBatch = useBatchPhase();
	// When a multi-model tailor run starts, record total expected models so Judge button stays disabled until all complete.
	const multiTailorExpectedRef = useRef<number | null>(null);
	// (Simplified) We will parse tailoredOutput at judge time; frozen map retained but no longer authoritative
	const tailoredSectionsRef = useRef<Record<string,string>>({});
	// Keep a stable ref so callbacks can access latest
	const fitBatchRef = useRef(fitBatch);
	useEffect(()=>{ fitBatchRef.current = fitBatch; }, [fitBatch]);
	// Cleanup batch streams on unmount (safety)
	useEffect(() => {
		return () => { try { if (fitBatchRef.current?.active) { fitBatchRef.current.cancelBatch().catch(()=>{}); } } catch {} };
	}, []);

	// Group + analytics helpers
	function makeGroupId(): string { try { return crypto.randomUUID(); } catch { return Math.random().toString(36).slice(2); } }
	const requestGroupRef = useRef<string | null>(null);
	const lastTailorBatchSizeRef = useRef<number>(0);

	// Bridge: listen for sidebar multi-model broadcast and project into window.__rt_* flags expected by batch code.
	useEffect(() => {
		const handler = (e: Event) => {
			try {
				const det: any = (e as CustomEvent).detail;
				if (!det) return;
				if (!det.multiMode) {
					try { delete (window as any).__rt_fit_multi; delete (window as any).__rt_tailor_multi; delete (window as any).__rt_judge_multi; } catch {}
					return;
				}
				const assign = (key: string, arr: string[]) => {
					if (Array.isArray(arr) && arr.length >= 1) { (window as any)[key] = { enabled: true, models: arr.slice() }; }
					else { try { delete (window as any)[key]; } catch {} }
				};
				assign('__rt_fit_multi', det.multiFit);
				assign('__rt_tailor_multi', det.multiTailor);
				assign('__rt_judge_multi', det.multiJudge);
			} catch {}
		};
		try { window.addEventListener('rt-multi-models', handler as any); } catch {}
		return () => { try { window.removeEventListener('rt-multi-models', handler as any); } catch {} };
	}, []);
	// Reflect aggregated markdown into existing fitOutput string so existing markdown memo works.
	useEffect(() => {
		if (!fitBatch.jobs.length) return;
		const markdown = fitBatch.batchMarkdown || "";
		if (batchPhase === 'fit') {
			setFitOutput(markdown);
			// Update snapshot ref to prevent divergence detection
			if (snapshotOutputsRef.current && markdown) {
				snapshotOutputsRef.current = { ...snapshotOutputsRef.current, fit: markdown };
			}
		} else if (batchPhase === 'tailor') {
			setTailoredOutput(markdown);
			// Update snapshot ref to prevent divergence detection
			if (snapshotOutputsRef.current && markdown) {
				snapshotOutputsRef.current = { ...snapshotOutputsRef.current, tailored: markdown };
			}
		} else if (batchPhase === 'judge') {
			setJudgeOutput(markdown);
			// Update snapshot ref to prevent divergence detection
			if (snapshotOutputsRef.current && markdown) {
				snapshotOutputsRef.current = { ...snapshotOutputsRef.current, judge: markdown };
			}
		}
	}, [fitBatch.batchMarkdown, fitBatch.jobs, batchPhase, setFitOutput, setTailoredOutput, setJudgeOutput]);

	// Persist a single snapshot (latest only) after a batch finishes (no per-alias history rows).
	// Mirrors single-model snapshot logic: overwrite existing snapshot once with aggregated output.
	// BUG FIX: Capture JD/resume at batch start to prevent saving stale outputs when user pastes new JD
	const batchInputsRef = useRef<{jd: string; resume: string} | null>(null);
	useEffect(() => {
		// Capture inputs when batch starts
		if (batchPhase && fitBatch.active && fitBatch.jobs.length > 0) {
			batchInputsRef.current = { jd: jdText, resume: resumeText };
		}
	}, [batchPhase, fitBatch.active, fitBatch.jobs.length, jdText, resumeText]);
	
	useEffect(() => {
		if (!batchPhase) return;
		if (!fitBatch.jobs.length) return;
		// Only act when batch no longer active and at least one job succeeded.
		if (fitBatch.active) return;
		const anySucceeded = fitBatch.jobs.some(j => j.status === 'succeeded');
		if (!anySucceeded) return; // nothing to persist
		
		// BUG FIX: Only save if inputs haven't changed since batch started
		if (!batchInputsRef.current) return;
		if (batchInputsRef.current.jd !== jdText || batchInputsRef.current.resume !== resumeText) {
			if (isRtDebug()) console.log('[BATCH_COMPLETE] Skipping save - inputs changed since batch started');
			return;
		}
		// If just finished a multi-model tailor batch, freeze per-alias sections for later judge ranking.
		// No longer freezing sections here; parsing happens at judge click for freshest content
		// Choose aggregated output based on phase
		let producedFit: string | null = null; let producedTailor: string | null = null; let producedJudge: string | null = null;
		if (batchPhase === 'fit') producedFit = fitBatch.batchMarkdown || '';
		else if (batchPhase === 'tailor') producedTailor = fitBatch.batchMarkdown || '';
		else if (batchPhase === 'judge') {
			producedJudge = fitBatch.batchMarkdown || '';
			if (rankingJudgeRef.current && producedJudge) {
				producedJudge = producedJudge + (rankingLegendRef.current || '');
				setJudgeOutput(producedJudge);
				rankingJudgeRef.current = false;
			}
		}
		// Stats: accumulate per-model per-phase timings for multi-model flow.
		try {
			// Ref to store cross-phase timings
			if (!(window as any).__rt_multi_times) (window as any).__rt_multi_times = {} as Record<string,{fit?:number;tailor?:number;judge?:number}>;
			const store: Record<string,{fit?:number;tailor?:number;judge?:number}> = (window as any).__rt_multi_times;
			// Record this phase's per-model seconds
			Object.entries(fitBatch.totals.perJobSeconds).forEach(([alias, secs]) => {
				if (!store[alias]) store[alias] = {};
				(store[alias] as any)[batchPhase] = secs;
			});
			// Compute total as sum of phase maxima (parallel models per phase): max(fit) + max(tailor) + max(judge)
			function phaseMax(key: 'fit'|'tailor'|'judge'): number {
				let m = 0; let any = false;
				for (const rec of Object.values(store)) { const v = (rec as any)[key]; if (typeof v === 'number') { any = true; if (v > m) m = v; } }
				return any ? m : 0;
			}
			const grandTotal = phaseMax('fit') + phaseMax('tailor') + phaseMax('judge');
			// Determine canonical ordering using DISPLAY_OPTIONS order (fallback alphabetical)
			const order = DISPLAY_OPTIONS.map(o => o.alias);
			const aliases = Object.keys(store).sort((a,b) => {
				const ia = order.indexOf(a); const ib = order.indexOf(b);
				if (ia !== -1 && ib !== -1) return ia - ib;
				if (ia !== -1) return -1; if (ib !== -1) return 1; return a.localeCompare(b);
			});
			const lines: string[] = [];
			if (grandTotal > 0) lines.push(`**Total time:** ${fmtElapsedWhole(grandTotal)}`);
			// Helper to map alias -> display name (same as sidebar)
			const nameMap: Record<string,string> = {};
			DISPLAY_OPTIONS.forEach(o => { nameMap[o.alias] = o.alias; });
			aliases.forEach(alias => {
				const rec = store[alias];
				const disp = nameMap[alias] || alias;
				if (typeof rec.fit === 'number') lines.push(`Fit time (${disp}): ${fmtElapsedWhole(rec.fit)}`);
				if (typeof rec.tailor === 'number') lines.push(`Tailor time (${disp}): ${fmtElapsedWhole(rec.tailor)}`);
				if (typeof rec.judge === 'number') lines.push(`Judge time (${disp}): ${fmtElapsedWhole(rec.judge)}`);
			});
			const newStats = lines.join('  \n');
			setStatsMd(newStats);
			
			// Update snapshot outputs ref to prevent divergence detection from clearing the new batch results
			if (snapshotOutputsRef.current) {
				snapshotOutputsRef.current = {
					fit: producedFit ?? snapshotOutputsRef.current.fit,
					tailored: producedTailor ?? snapshotOutputsRef.current.tailored,
					judge: producedJudge ?? snapshotOutputsRef.current.judge,
					statsMd: newStats ?? snapshotOutputsRef.current.statsMd
				};
			}
			
		(async () => { try {
			if (isLoggedIn !== true) return; if (!jdText.trim()) return;
			const snap: any = { resumeInput: resumeText, jdInput: jdText, fitOutput: (producedFit ?? fitOutputRef.current) || null, tailoredOutput: (producedTailor ?? tailoredOutputRef.current) || null, judgeOutput: (producedJudge ?? judgeOutputRef.current) || null, statsMd: newStats || null, knobs: { fitModelLabel, tailorModelLabel, judgeLabel }, modelInfo: modelMeta ? { provider: modelMeta.provider, model: modelMeta.model } : null };
			if (isRtDebug()) {
				const jdHash = await makeJdHash(jdText);
				const curJdNorm = normalizeText(jdText);
				const snapshotJdNorm = snapshotInputsRef.current?.jd || '';
				const outputsMatch = snapshotInputsRef.current && curJdNorm === snapshotJdNorm;
				const snapshotHash = snapshotJdNorm ? (await stableHash(snapshotJdNorm)).substring(0, 16) : 'none';
				console.log('[BATCH_COMPLETE] POST /applications/jd/save', {
					jdHash: jdHash.substring(0, 16),
					hasOutputs: !!(snap.fitOutput || snap.tailoredOutput || snap.judgeOutput),
					outputsMatchCurrentJD: outputsMatch,
					snapshotJdHash: snapshotHash,
					batchPhase,
					producedFit: !!producedFit,
					producedTailor: !!producedTailor,
					producedJudge: !!producedJudge
				});
			}
			await apiClient.post('/applications/jd/save', { jdText: jdText, baseText: resumeText, snapshot: snap }).catch(()=>null);
		} catch {} })();
	} catch {}
}, [batchPhase, fitBatch.active, fitBatch.jobs, fitBatch.batchMarkdown, fitBatch.totals, isLoggedIn, jdText, resumeText, modelMeta, fitModelLabel, tailorModelLabel, judgeLabel]);	// Labels and disabled
	const tailorRunning = Boolean(tailorRequested);
	const judgeRunning = judgeRequested;
	const fitLabel = (fitRequested || (batchPhase==='fit' && fitBatch.active)) ? "Cancel" : "Check Job Fit";
	// Only enable judge-combined label after hydration so server/client markup matches
	const uiShowJudge = false;
	// Button labels now reflect multi-model cancellation when batch active
	const multiActive = fitBatch.jobs.length >= 1 && fitBatch.active;
	const tailorLabel = (tailorRunning || (batchPhase==='tailor' && multiActive)) ? "Cancel" : "Tailor My Resume";
	const judgeLabelBtn = judgeRunning ? "Cancel" : "Judge Tailored Resume"; // manual judge still allowed
	// Derived: whether a tailored resume exists (non-empty)
	const hasTailored = useMemo(() => Boolean((tailoredOutput || "").trim()), [tailoredOutput]);
	// Button disabled logic: while any run active, only the active phase's Cancel button stays enabled.
	// Additionally: Judge requires an existing tailored resume; if absent, keep disabled (unless cancelling an active judge run).
	const fitDisabled = authPending || (isLoggedIn !== true) || appliedChecked || ((fitRequested || (batchPhase==='fit' && fitBatch.active)) ? false : (tailorRunning || judgeRunning));
	const tailorDisabled = authPending || (isLoggedIn !== true) || appliedChecked || (((tailorRequested || (batchPhase==='tailor' && fitBatch.active)) ? false : (fitRequested || judgeRunning)) );
	// Additional gating: if a multi-model tailor batch ran, require all models to complete before enabling Judge
	let multiTailorIncomplete = false;
	if (multiTailorExpectedRef.current && batchPhase !== 'tailor') {
		// After tailor batch ended: count succeeded jobs from last batch run (those still in jobs array with status succeeded while inactive)
		const done = fitBatch.jobs.filter(j => j.status === 'succeeded').length;
		if (done < multiTailorExpectedRef.current) multiTailorIncomplete = true;
		// If no jobs are active and all succeeded/failed, keep expected until all succeeded or user re-runs tailor.
		if (!tailorRunning && fitBatch.active === false && done >= multiTailorExpectedRef.current) {
			multiTailorExpectedRef.current = null; // release gating once all expected succeeded
		}
	}
	const judgeDisabled = authPending || (isLoggedIn !== true) || appliedChecked || multiTailorIncomplete || (!hasTailored && !(judgeRunning || (batchPhase==='judge' && fitBatch.active))) || (((judgeRunning || (batchPhase==='judge' && fitBatch.active)) ? false : (fitRequested || tailorRunning)) );

	// Reset single-run gating flags after a multi-model batch finishes so buttons relabel from Cancel -> action.
	useEffect(() => {
		// Reset gating flags only after a completed multi-batch AND only if a new single-job run is not already active.
		// Previous logic always fired while fitBatch.jobs.length>1, clobbering fitRequested for subsequent single runs.
		if (!fitBatch.active && fitBatch.jobs.length >= 1 && !jobId) {
			if (fitRequested) setFitRequested(false);
			if (tailorRequested) { setTailorRequested(false); setAwaitingJudge(false); }
			if (judgeRequested) setJudgeRequested(false);
			// If tailor batch just ended, clear expected count for judge gating
			if (batchPhase === 'tailor') multiTailorExpectedRef.current = null;
		}
	}, [fitBatch.active, fitBatch.jobs.length, fitRequested, tailorRequested, judgeRequested, jobId]);
	// Persist resultType cookie for SSR flicker-free radio
	useEffect(() => { if (!resultType) return; try { const secure = (typeof location !== 'undefined' && location.protocol === 'https:') ? '; Secure' : ''; document.cookie = `rt_result_type=${encodeURIComponent(resultType)}; Path=/; SameSite=Lax${secure}; Max-Age=${300}`; } catch {} }, [resultType]);

	// Auto-switch result view ONLY after the last batch job completes (all jobs terminal),
	// or for single-job runs after output appears. Skips if user manually locked selection (after cancel).
	useEffect(() => {
		const phase = batchPhase; // 'fit' | 'tailor' | 'judge' | null
		const jobs = fitBatch.jobs;
		// If no active jobs and user manually changed view, do not auto-switch.
		const anyRunning = jobs.some(j => j.status === 'running' || j.status === 'queued');
		if (!anyRunning && autoSwitchLockedRef.current) return;
		// Prevent single-model switching here entirely; completion handler now owns it.
		if (!phase) return;
		if (phase && jobs.length) {
			// Determine if all jobs are terminal (succeeded|failed|cancelled) and at least one succeeded.
			const terminalStatuses = new Set(['succeeded','failed','cancelled']);
			const allTerminal = jobs.every(j => terminalStatuses.has(j.status));
			const anySuccess = jobs.some(j => j.status === 'succeeded');
			if (allTerminal && anySuccess) {
				const desired = phase;
				if (resultType !== desired) { try { setResultType(desired); } catch {} }
			}
			return; // batch handled
		}
	}, [batchPhase, fitBatch.jobs, resultType, fitRequested, tailorRequested, judgeRequested]);
	// STEAM-LIKE: No cookie clearing logic needed - HistoryClient owns rt_applied_state
	// This useEffect has been intentionally disabled as part of the database-only refactor
	useEffect(() => {
		// Intentionally empty - removed rt_applied_jd cookie clearing
	}, [appliedChecked]);

	// Layout freeze while running
		const layoutShowJudge = true; // single pane layout
		// Do not forcibly override the user's selected view during a Fit run; only use the special fit-only view if the user is already on Fit.
		const forceFitView = fitRequested && effectiveResultType === 'fit';

	// Limit Ctrl/Cmd+A to the result boxes only (Streamlit parity)
	const fitBoxRef = useRef<HTMLDivElement | null>(null);
	const singleResultRef = useRef<HTMLDivElement | null>(null);
	// Deprecated split refs retained for potential future re-introduction but unused now
	const tailoredRef = useRef<HTMLDivElement | null>(null);
	const judgeRef = useRef<HTMLDivElement | null>(null);
	const onKeySelectAll = useCallback((e: React.KeyboardEvent, ref: React.RefObject<HTMLDivElement | null>) => {
		if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
			e.preventDefault();
			e.stopPropagation();
			const el = ref.current;
			if (!el) return;
			try {
				const sel = window.getSelection();
				if (!sel) return;
				const range = document.createRange();
				range.selectNodeContents(el);
				sel.removeAllRanges();
				sel.addRange(range);
			} catch {}
		}
	}, []);

	// Bottom counters: free-requests hint, total processed, and dynamic trial amount (avoid hydration mismatch: seed with SSR props)
	const [freeReqHint, setFreeReqHint] = useState<number | null>(() => (typeof initialFreeReqHint === 'number' ? initialFreeReqHint : null));
	const [totalProcessed, setTotalProcessed] = useState<number | null>(null);
	const [trialUsd, setTrialUsd] = useState<string | null>(() => (initialTrialUsd ? initialTrialUsd : null));
	const [trialAvailable, setTrialAvailable] = useState<number | null>(null);
	const [trialTotal, setTrialTotal] = useState<number | null>(null);
	const [trialDurationDays, setTrialDurationDays] = useState<number | null>(null);
	const [trialEndDate, setTrialEndDate] = useState<string | null>(null);
	// No width reservation for banner counters – allow natural flow
	useEffect(() => {
		// Hydrate from localStorage first for logged-out users to avoid a blank between mount and fetch
	if (isLoggedIn !== true) {
			try { const v = Number(localStorage.getItem("__rt_free_req_hint") || ""); if (Number.isFinite(v) && v > 0) setFreeReqHint(prev => prev == null ? v : prev); } catch {}
			try { const v2 = Number(localStorage.getItem("__rt_total_processed") || ""); if (Number.isFinite(v2) && v2 >= 0) setTotalProcessed(prev => prev == null ? v2 : prev); } catch {}
			try { const t = String(localStorage.getItem("__rt_trial_usd") || ""); if (t) setTrialUsd(prev => prev == null ? t : prev); } catch {}
		}
		let cancelled = false;
		const controller = new AbortController();
		(async () => {
			try {
				const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/pricing/average?trim=0.10`, { credentials: 'include', signal: controller.signal });
				if (r.ok) {
					const data = await r.json().catch(() => null);
					if (!cancelled && data && typeof data?.free_hint === 'number') setFreeReqHint(data.free_hint);
					if (!cancelled && data && typeof data?.total_processed === 'number') setTotalProcessed(data.total_processed);
					if (!cancelled && data && (typeof data?.trial_usd === 'string' || typeof data?.trial_cents === 'number')) {
						const val = (typeof data.trial_usd === 'string' && data.trial_usd) ? data.trial_usd : String((Number(data.trial_cents||0)/100).toFixed(2));
						setTrialUsd(val);
					}
				}
			} catch {}
		})();
		return () => { cancelled = true; try { controller.abort(); } catch {} };
	}, [isLoggedIn]);

	// Fetch trial availability for logged-out users
	useEffect(() => {
		if (isLoggedIn === true) return; // Only fetch for logged-out users
		let cancelled = false;
		const controller = new AbortController();
		(async () => {
			try {
				const r = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/public/trial-availability`, { signal: controller.signal });
				if (r.ok) {
					const data = await r.json().catch(() => null);
					if (!cancelled && data) {
						if (typeof data.available === 'number') setTrialAvailable(data.available);
						if (typeof data.total === 'number' || data.total === null) setTrialTotal(data.total);
						if (typeof data.trial_duration_days === 'number') setTrialDurationDays(data.trial_duration_days);
						if (typeof data.trial_end_date === 'string') setTrialEndDate(data.trial_end_date);
					}
				}
			} catch {}
		})();
		return () => { cancelled = true; try { controller.abort(); } catch {} };
	}, [isLoggedIn]);

	// Persist numbers when available
	useEffect(() => {
		if (typeof freeReqHint === 'number' && freeReqHint > 0) {
			try { localStorage.setItem("__rt_free_req_hint", String(freeReqHint)); } catch {}
		}
	}, [freeReqHint]);
	useEffect(() => {
		if (typeof totalProcessed === 'number') {
			try { localStorage.setItem("__rt_total_processed", String(totalProcessed)); } catch {}
		}
	}, [totalProcessed]);
	useEffect(() => {
		if (typeof trialUsd === 'string' && trialUsd) {
			try { localStorage.setItem("__rt_trial_usd", trialUsd); } catch {}
		}
	}, [trialUsd]);

	// Memoized markdown renderers to avoid re-parsing large outputs every tick
	const trialUsdDisplay = useMemo(() => {
		try {
			let t = (trialUsd || "").trim();
			if (!t) return "";
			if (!t.startsWith("$")) t = "$" + t;
			if (t.endsWith(".00")) t = t.slice(0, -3);
			return t;
		} catch { return trialUsd || ""; }
	}, [trialUsd]);
	const fitMarkdown = useMemo(() => (fitOutput ? <Markdown>{fitOutput}</Markdown> : null), [fitOutput]);
	const tailoredMarkdown = useMemo(() => (tailoredOutput ? <Markdown>{tailoredOutput}</Markdown> : null), [tailoredOutput]);
	const judgeMarkdown = useMemo(() => (judgeOutput ? <Markdown>{judgeOutput}</Markdown> : null), [judgeOutput]);
	const statsMarkdown = useMemo(() => (isLoggedIn === true && statsMd ? <Markdown>{statsMd}</Markdown> : null), [isLoggedIn, statsMd]);

	return (
		<div className="grid grid-cols-1 gap-4 pb-28 md:pb-0 md:grid-cols-2 text-slate-200 xl:gap-[18px] 2xl:gap-[18px] 2xl:grid-cols-[660px_660px] 2xl:max-w-[1338px] 2xl:mx-auto">
			{rtDebugEnabled && <ResumeRunDebugOverlay events={runDebugEvents} setEvents={setRunDebugEvents} />}
			{/* 🔍 DOUBLE LOAD DIAGNOSTIC BANNER */}
			{reloadDiagnostic?.showWarning && (
				<div className="col-span-full p-4 border-2 border-red-500 bg-red-950/30 rounded-lg">
					<div className="flex items-start gap-3">
						<div className="text-3xl">🚨</div>
						<div className="flex-1">
							<h2 className="text-xl font-bold text-red-400 mb-2">
								Double Page Load Detected!
							</h2>
							<p className="text-red-300 mb-3">
								This page has loaded <strong>{reloadDiagnostic.loadCount} times</strong> in rapid succession (within {Math.round((reloadDiagnostic.loadTimestamps[reloadDiagnostic.loadTimestamps.length - 1] - reloadDiagnostic.loadTimestamps[0]))}ms of initial load). 
								This may indicate a redirect loop, authentication issue, or React mounting problem.
							</p>
							<details className="mt-3">
								<summary className="cursor-pointer text-red-300 hover:text-red-200 font-semibold">
									📋 View Full Diagnostic Report
								</summary>
								<div className="mt-3 p-3 bg-slate-900/80 rounded border border-red-700/50 font-mono text-xs space-y-1">
									{reloadDiagnostic.diagnostics.map((msg, i) => (
										<div key={i} className="text-slate-300">{msg}</div>
									))}
									<div className="mt-3 pt-3 border-t border-slate-700">
										<div className="text-amber-400 font-semibold mb-1">Load Timestamps:</div>
										{reloadDiagnostic.loadTimestamps.map((ts, i) => (
											<div key={i} className="text-slate-400">
												Load #{i + 1}: {new Date(ts).toISOString()} 
												{i > 0 && ` (+${ts - reloadDiagnostic.loadTimestamps[i-1]}ms)`}
											</div>
										))}
									</div>
									<div className="mt-3 pt-3 border-t border-slate-700">
										<div className="text-amber-400 font-semibold mb-1">Props Received:</div>
										<div className="text-slate-400">initialLoggedIn: {String(initialLoggedIn)}</div>
										<div className="text-slate-400">initialAuthVerified: {String(initialAuthVerified)}</div>
										<div className="text-slate-400">initialSnapshotLoaded: {String(initialSnapshotLoaded)}</div>
										<div className="text-slate-400">URL: {typeof window !== 'undefined' ? window.location.href : 'N/A'}</div>
									</div>
								</div>
							</details>
							<div className="mt-3 flex gap-2">
								<button
									onClick={() => {
										// Clear tracking and reload once
										sessionStorage.removeItem('__rt_reload_tracking');
										sessionStorage.removeItem('__rt_session_start');
										window.location.reload();
									}}
									className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-sm font-medium"
								>
									Clear & Reload
								</button>
								<button
									onClick={() => setReloadDiagnostic(null)}
									className="px-3 py-1 bg-slate-700 hover:bg-slate-600 text-white rounded text-sm font-medium"
								>
									Dismiss Warning
								</button>
							</div>
						</div>
					</div>
				</div>
			)}
			
			{/* Your Information - left column on desktop, first in DOM */}
			<div className="space-y-0 2xl:w-[660px]">
				<h1 className="text-2xl font-semibold mt-1 mb-2 2xl:mb-3">Your Information</h1>
				{/* Inputs group with gap equal to column gap (18px) at XL/2XL */}
				<div className="space-y-3 xl:space-y-[18px] 2xl:space-y-[18px] mt-0 md:pl-1">
					<textarea
						placeholder="Paste your base resume here..."
						className="w-full min-h-[400px] rounded-md border border-slate-700/60 bg-[#131820] p-3 placeholder:text-muted-foreground hover-thin-scrollbar xl:h-[496px] xl:min-h-[496px] xl:max-h-[496px] 2xl:h-[496px] 2xl:min-h-[496px] 2xl:max-h-[496px]"
						value={resumeText}
						onChange={(e) => setResumeText(e.target.value)}
						// Keep normal styling; prevent editing via readOnly when applied
						readOnly={appliedChecked && !uiDisabled}
						disabled={uiDisabled}
					/>
					<textarea placeholder="Paste the target job description here..." className="w-full min-h-[400px] rounded-md border border-slate-700/60 bg-[#131820] p-3 placeholder:text-muted-foreground hover-thin-scrollbar xl:h-[496px] xl:min-h-[496px] xl:max-h-[496px] 2xl:h-[496px] 2xl:min-h-[496px] 2xl:max-h-[496px]" value={jdText} onChange={(e) => setJdText(e.target.value)} disabled={uiDisabled} />
				</div>				{/* Compact block: checkbox, buttons, alerts, and hints */}
				<div className="space-y-3 mt-[15px] md:pl-1">
					{/* Applied snapshot toggle */}
					<div className="flex items-center gap-3 mt-1 mb-1 flex-wrap">
						<div className="flex items-center gap-2">
							<div className="relative">
								<input
									id="applied_snapshot"
									type="checkbox"
									className={`accent-amber-500 ${(running || appliedSaving) ? 'cursor-not-allowed opacity-70' : ''}`}
									aria-disabled={authPending || running || appliedSaving || (isLoggedIn !== true)}
									aria-busy={appliedSaving}
									checked={appliedChecked}
									onChange={(e) => { if (running || appliedSaving) return; onAppliedToggle(e.target.checked); }}
									disabled={authPending || (isLoggedIn !== true) || running || appliedSaving}
								/>
								{appliedSaving && (
									<div className="absolute -right-6 top-0 h-4 w-4 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" title="Saving..." />
								)}
							</div>
							<label htmlFor="applied_snapshot" className={`text-slate-300 ${uiDisabled ? 'opacity-50' : ''}`}>I applied with this version</label>
							{appliedSaving && (
								<span className="sr-only" aria-live="polite">Saving applied status...</span>
							)}
						</div>
						{(appliedLoading || appliedBanner) && (
							<div className="text-xs text-slate-400 whitespace-pre-wrap max-w-[420px]" role="status" aria-live="polite">
								{appliedLoading ? "Loading..." : appliedBanner}
							</div>
						)}
					</div>
					{/* Result view selector (radio buttons) */}
					<div className="flex items-center gap-4 flex-wrap" role="radiogroup" aria-label="Result view selector">
						{["fit","tailor","judge"].map(opt => (
							<label key={opt} className="flex items-center gap-1 text-slate-300 cursor-pointer">
								<input
									type="radio"
									name="result_view"
									value={opt}
												checked={resultType === opt}
									onChange={() => { autoSwitchLockedRef.current = true; setResultType(opt as any); }}
									className="accent-amber-500"
								/>
								<span className="capitalize">{opt === "fit" ? "Show Fit" : opt === "tailor" ? "Show Tailor" : "Show Judge"}</span>
							</label>
						))}
					</div>
					
					{/* Action Buttons */}
					{/* Desktop: Inline grid layout */}
					<div className="hidden md:grid md:grid-cols-3 md:gap-2">
						{/* Buttons simplified to avoid per-render IIFE allocations */}
						<Tooltip content={!fitDisabled && isLoggedIn === true ? (multiModeActive ? (multiFitAliases.length === 0 ? "Select models in the sidebar" : multiFitTip || null) : (fitTip || null)) : null}>
							<button onClick={onCheckFit} className="rounded bg-slate-700 hover:bg-slate-600 active:bg-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 px-3 py-2 disabled:opacity-50 min-w-[132px] transition-colors" disabled={fitDisabled}>{fitLabel}</button>
						</Tooltip>
						<Tooltip content={!tailorDisabled && isLoggedIn === true ? (multiModeActive ? (multiTailorAliases.length === 0 ? "Select models in the sidebar" : multiTailorTip || null) : (tailorTip || null)) : null}>
							<button onClick={onTailor} className="rounded bg-slate-700 hover:bg-slate-600 active:bg-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 px-3 py-2 disabled:opacity-50 min-w-[132px] transition-colors" disabled={tailorDisabled}>{tailorLabel}</button>
						</Tooltip>
						{layoutShowJudge ? (
							<Tooltip content={!judgeDisabled && isLoggedIn === true ? (multiModeActive ? (multiJudgeAliases.length === 0 ? "Select models in the sidebar" : multiJudgeTip || null) : (judgeTip || null)) : null}>
								<button onClick={onJudge} className="rounded bg-slate-700 hover:bg-slate-600 active:bg-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 px-3 py-2 disabled:opacity-50 min-w-[132px] transition-colors" disabled={judgeDisabled}>{judgeLabelBtn}</button>
							</Tooltip>
						) : <div />}
					</div>
					
					{/* Mobile: Fixed bottom bar (rendered via portal at end of component) */}
					
					{alert && (
						<div className={{ info: "text-blue-400", success: "text-green-400", warning: "text-yellow-400", error: "text-red-400" }[alert.kind]}>{alert.text}</div>
					)}
					
					{/* Loading state - Mobile: Progress bar, Desktop: Status line with spinner */}
					{running && (
						<>
							{/* Mobile: Simple progress bar */}
							<div className="md:hidden">
								<div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
									<div className="bg-amber-500 h-full rounded-full animate-pulse" style={{ width: '70%' }} />
								</div>
								<p className="text-xs text-slate-400 mt-2 text-center">
									{fitRequested ? 'Checking fit...' : tailorRequested ? 'Tailoring...' : 'Judging...'}
								</p>
							</div>
							
							{/* Desktop: Detailed status lines */}
							<div className="hidden md:block space-y-2">
					{/* Phase banners with spinner + elapsed timers (single or multi) - Desktop only */}
					{fitRequested && (
						<>
							{(batchPhase==='fit' && fitBatch.active && fitBatch.jobs.length>=1) ? (
								// Multi-model: grouped to reduce inter-line spacing
								<div className="space-y-1">
									{fitBatch.jobs.filter(j=>!['succeeded','failed','cancelled'].includes(j.status)).slice(0,12).map(j => (
										<div key={j.alias} className="text-slate-400 flex items-center gap-2">
											<div className="h-4 w-4 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
											<span>
												{`Checking job fit with ${j.alias}…`}
												{j.startedAt ? ` ${fmtElapsedWhole(((j.endedAt||Date.now()) - j.startedAt)/1000)}` : ''}
											</span>
										</div>
									))}
								</div>
							) : (
								<div className="text-slate-400 flex items-center gap-2">
									<div className="h-4 w-4 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
									<span>
										{`Checking job fit with ${
											(batchPhase === 'fit' && fitBatch.jobs.length > 0) 
												? fitBatch.jobs[0].alias 
												: ((DISPLAY_OPTIONS.find(o=>o.label===fitModelLabel)?.alias)||'model')
										}…`}
										{phaseTimesRef.current.fit ? ` ${fmtElapsedWhole(((phaseTimesRef.current.fit.end || performance.now()) - phaseTimesRef.current.fit.start)/1000)}` : ""}
									</span>
								</div>
							)}
						</>
					)}
					{tailorRequested && !awaitingJudge && (
						<>
							{(batchPhase==='tailor' && fitBatch.active && fitBatch.jobs.length>=1) ? (
								<div className="space-y-1">
									{fitBatch.jobs.filter(j=>!['succeeded','failed','cancelled'].includes(j.status)).slice(0,12).map(j => (
										<div key={j.alias} className="text-slate-400 flex items-center gap-2">
											<div className="h-4 w-4 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
											<span>
												{`Tailoring with ${j.alias}…`}
												{j.startedAt ? ` ${fmtElapsedWhole(((j.endedAt||Date.now()) - j.startedAt)/1000)}` : ''}
											</span>
										</div>
									))}
								</div>
							) : (
								<div className="text-slate-400 flex items-center gap-2">
									<div className="h-4 w-4 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
									<span>
										{`Tailoring with ${
											(batchPhase === 'tailor' && fitBatch.jobs.length > 0) 
												? fitBatch.jobs[0].alias 
												: ((DISPLAY_OPTIONS.find(o=>o.label===tailorModelLabel)?.alias)||'model')
										}…`}
										{phaseTimesRef.current.tailor ? ` ${fmtElapsedWhole(((phaseTimesRef.current.tailor.end || performance.now()) - phaseTimesRef.current.tailor.start)/1000)}` : ""}
									</span>
								</div>
							)}
						</>
					)}
					{(awaitingJudge || judgeRequested) && (
						<>
							{(batchPhase==='judge' && fitBatch.active && fitBatch.jobs.length>=1) ? (
								<div className="space-y-1">
									{fitBatch.jobs.filter(j=>!['succeeded','failed','cancelled'].includes(j.status)).slice(0,12).map(j => (
										<div key={j.alias} className="text-slate-400 flex items-center gap-2">
											<div className="h-4 w-4 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
											<span>
												{`Judging with ${j.alias}…`}
												{j.startedAt ? ` ${fmtElapsedWhole(((j.endedAt||Date.now()) - j.startedAt)/1000)}` : ''}
											</span>
										</div>
									))}
								</div>
							) : (
								<div className="text-slate-400 flex items-center gap-2">
									<div className="h-4 w-4 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
									<span>
										{`Judging with ${
											(batchPhase === 'judge' && fitBatch.jobs.length > 0) 
												? fitBatch.jobs[0].alias 
												: ((judgeLabel.includes(' — ') ? judgeLabel.split(' — ')[0] : judgeLabel) || 'model')
										}…`}
										{phaseTimesRef.current.judge ? ` ${fmtElapsedWhole(((phaseTimesRef.current.judge.end || performance.now()) - phaseTimesRef.current.judge.start)/1000)}` : ""}
									</span>
								</div>
							)}
						</>
					)}
							</div>
						</>
					)}
				{/* stats moved below result boxes */}
				{/* Bottom hints: render full text immediately; only numbers swap in to avoid pop-in */}
				{isLoggedIn !== true && (
				  <div className="text-white">
				    <div>
				      Use the sidebar to Login/Register
				    </div>
				  <div className="mt-1">
				    Total requests processed: {" "}
				    <span
				      aria-live="polite"
				      className="tabular-nums inline-block align-baseline"
				    >
				      {typeof totalProcessed === "number" ? totalProcessed.toLocaleString() : ""}
				    </span>
				  </div>
				</div>
				)}
			</div>
		</div>			{/* Your Result - right column on desktop, second in DOM */}
			<div className="space-y-3 2xl:space-y-6 md:pr-1">
				{forceFitView ? (
					<div className="mt-1 xl:mt-1 2xl:mt-1">
						{/* FIT & TAILOR Batch Status Banners (multi-mode). Tailor shown only for tailor batch phase. */}
						{/* Multi-model batch progress: reuse single-model spinner rows below; banner removed */}
						<div className="text-2xl font-semibold mb-2 2xl:mb-3">Your Result</div>
						<div
							ref={fitBoxRef}
							data-debug-result-panel="fit-forced"
							tabIndex={0}
							role="region"
							aria-label="Result content. Press Ctrl+A to select all."
							onMouseDown={(e) => (e.currentTarget as HTMLDivElement).focus()}
							onKeyDown={(e) => onKeySelectAll(e, fitBoxRef)}
							className="rounded-md border border-slate-700/60 p-3 h-[852px] min-h-[852px] max-h-[852px] md:h-[818px] md:min-h-[818px] md:max-h-[818px] overflow-auto hover-thin-scrollbar bg-[#0f141d] xl:h-[1016px] xl:min-h-[1016px] xl:max-h-[1016px] 2xl:h-[1016px] 2xl:min-h-[1016px] 2xl:max-h-[1016px]"
						>
							{fitMarkdown ? (
								fitMarkdown
							) : (batchPhase === 'fit' || fitRequested || optimisticRunning === 'fit') ? (
								<div className="text-muted-foreground italic">
									Processing Fit...
								</div>
							) : (
								<div className="text-muted-foreground italic">Click Fit, Tailor, or Judge to see results here.</div>
							)}
						</div>
						{statsMarkdown && <div data-debug-stats-block="true" className="mt-2 text-sm text-slate-300">{statsMarkdown}</div>}
					</div>
				) : (
					<div className="mt-1 xl:mt-1 2xl:mt-1">
						{/* Multi-model batch progress: banner removed */}
						<div className="text-2xl font-semibold mb-2 2xl:mb-3">Your Result</div>
						<div
							ref={singleResultRef}
							data-debug-result-panel={effectiveResultType || "fit"}
							tabIndex={0}
							role="region"
							aria-label="Result content. Press Ctrl+A to select all."
							onMouseDown={(e) => (e.currentTarget as HTMLDivElement).focus()}
							onKeyDown={(e) => onKeySelectAll(e, singleResultRef)}
							className="rounded-md border border-slate-700/60 p-3 h-[852px] min-h-[852px] max-h-[852px] md:h-[818px] md:min-h-[818px] md:max-h-[818px] overflow-auto hover-thin-scrollbar bg-[#0f141d] xl:h-[1016px] xl:min-h-[1016px] xl:max-h-[1016px] 2xl:h-[1016px] 2xl:min-h-[1016px] 2xl:max-h-[1016px]"
						>
							{(effectiveResultType === "fit" ? fitMarkdown : effectiveResultType === "tailor" ? tailoredMarkdown : effectiveResultType === "judge" ? judgeMarkdown : null) ? (
								(effectiveResultType === "fit" ? fitMarkdown : effectiveResultType === "tailor" ? tailoredMarkdown : effectiveResultType === "judge" ? judgeMarkdown : null)
							) : optimisticRunning ? (
								<div className="text-muted-foreground italic">
									{optimisticRunning === 'fit'
										? 'Processing Fit...'
										: optimisticRunning === 'tailor'
										? 'Processing Tailor...'
										: optimisticRunning === 'judge'
										? 'Processing Judge...'
										: 'Processing...'}
								</div>
							) : running ? (
								<div className="text-muted-foreground italic">
									{batchPhase === 'fit' || effectiveResultType === 'fit'
										? 'Processing Fit...'
										: batchPhase === 'tailor' || effectiveResultType === 'tailor'
										? 'Processing Tailor...'
										: batchPhase === 'judge' || effectiveResultType === 'judge'
										? 'Processing Judge...'
										: 'Processing...'}
								</div>
							) : (
								<div className="text-muted-foreground italic">Click Fit, Tailor, or Judge to see results here.</div>
							)}
						</div>
						{statsMarkdown && <div data-debug-stats-block="true" className="mt-3 md:mt-4 text-sm md:text-base text-slate-300 break-words">{statsMarkdown}</div>}
					</div>
				)}
			</div>
			
			{/* Mobile Fixed Bottom Action Bar */}
			<div className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-800 bg-[#0b0e14]/95 backdrop-blur p-3 md:hidden">
				<div className="flex flex-col gap-2 max-w-screen-xl mx-auto">
					{/* Progress indicator when running */}
					{running && (
						<div className="w-full bg-slate-800 rounded-full h-1 overflow-hidden mb-1">
							<div className="bg-amber-500 h-full rounded-full animate-pulse" style={{ width: '70%' }} />
						</div>
					)}
					
					{/* DEBUG PANEL - Visible on page */}
					{rtDebugEnabled && (
						<div className="mb-2 p-4 bg-slate-800 border border-amber-500 rounded text-xs font-mono">
							<div className="text-amber-500 font-bold mb-2">🔍 DEBUG: Model Selection State</div>
							<div className="space-y-1 text-slate-300">
								<div><strong className="text-amber-400">Fit Label:</strong> {fitModelLabel || 'NULL'}</div>
								<div><strong className="text-amber-400">Fit Alias:</strong> {fitModelAlias || 'NULL'}</div>
								<div><strong className="text-amber-400">Fit Meta:</strong> {fitModelMeta ? `${fitModelMeta.provider}/${fitModelMeta.model}` : 'NULL'}</div>
								<div className="mt-2"><strong className="text-amber-400">Tailor Label:</strong> {tailorModelLabel || 'NULL'}</div>
								<div><strong className="text-amber-400">Judge Label:</strong> {judgeLabel || 'NULL'}</div>
								<div className="mt-2"><strong className="text-amber-400">Multi-Mode:</strong> {multiModeActive ? 'YES' : 'NO'}</div>
								{multiModeActive && (
									<>
										<div><strong className="text-amber-400">Multi Fit:</strong> {multiFitAliases.join(', ') || 'NONE'}</div>
										<div><strong className="text-amber-400">Multi Tailor:</strong> {multiTailorAliases.join(', ') || 'NONE'}</div>
									</>
								)}
								<div className="mt-2"><strong className="text-amber-400">Window.__rt_fit_multi:</strong> {JSON.stringify((window as any).__rt_fit_multi || null)}</div>
								<div className="mt-2 text-red-400"><strong>❌ Validation will fail if:</strong> No label OR no meta (single) OR no multi flag</div>
							</div>
						</div>
					)}
					
					{/* Action buttons */}
					<div className="grid grid-cols-3 gap-2">
						<button 
							onClick={onCheckFit} 
							className="w-full min-h-11 rounded bg-slate-700 hover:bg-slate-600 active:bg-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 px-3 py-2 disabled:opacity-50 transition-colors text-base font-medium" 
							disabled={fitDisabled}
						>
							{running && fitRequested ? (
								<span className="flex items-center justify-center gap-2">
									<span className="h-4 w-4 border-2 border-slate-400 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
									<span className="sr-only">Checking...</span>
								</span>
							) : fitLabel}
						</button>
						<button 
							onClick={onTailor} 
							className="w-full min-h-11 rounded bg-slate-700 hover:bg-slate-600 active:bg-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 px-3 py-2 disabled:opacity-50 transition-colors text-base font-medium" 
							disabled={tailorDisabled}
						>
							{running && tailorRequested ? (
								<span className="flex items-center justify-center gap-2">
									<span className="h-4 w-4 border-2 border-slate-400 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
									<span className="sr-only">Tailoring...</span>
								</span>
							) : tailorLabel}
						</button>
						{layoutShowJudge ? (
							<button 
								onClick={onJudge} 
								className="w-full min-h-11 rounded bg-slate-700 hover:bg-slate-600 active:bg-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 px-3 py-2 disabled:opacity-50 transition-colors text-base font-medium" 
								disabled={judgeDisabled}
							>
								{running && (awaitingJudge || judgeRequested) ? (
									<span className="flex items-center justify-center gap-2">
										<span className="h-4 w-4 border-2 border-slate-400 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
										<span className="sr-only">Judging...</span>
									</span>
								) : judgeLabelBtn}
							</button>
						) : <div />}
					</div>
				</div>
			</div>
		</div>
	);
}
