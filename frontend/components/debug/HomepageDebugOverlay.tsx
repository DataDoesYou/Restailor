"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type DebugSeed = {
	hasAuth: boolean;
	initialApplied: boolean;
	initialSnapshotLoaded: boolean;
	hasInitialResume: boolean;
	hasInitialJd: boolean;
	hasFitOutput: boolean;
	hasTailoredOutput: boolean;
	hasJudgeOutput: boolean;
	resultTypeInitial: string;
	hasAppliedKey: boolean;
	hasCurrentSnapshotLookup: boolean;
	debugLoggedOutEnabled: boolean;
	initialTrialUsd?: string;
	initialFreeReqHint?: number;
};

type DebugEvent = {
	iso: string;
	relMs: number;
	name: string;
	data?: Record<string, unknown>;
};

const RELOAD_SNAPSHOT_KEY = "__rt_homepage_debug_reload_snapshot";

function summarizeDom() {
	try {
		const bodyRect = document.body.getBoundingClientRect();
		const main = document.querySelector("main") || document.body;
		const mainRect = main.getBoundingClientRect();
		return {
			readyState: document.readyState,
			body: { w: Math.round(bodyRect.width), h: Math.round(bodyRect.height) },
			main: { w: Math.round(mainRect.width), h: Math.round(mainRect.height) },
			textareas: document.querySelectorAll("textarea").length,
			buttons: document.querySelectorAll("button").length,
			outputPanels: document.querySelectorAll("[data-result-type], [data-testid*='output'], [class*='output']").length,
		};
	} catch {
		return {};
	}
}

function summarizeDocumentTree() {
	try {
		const bodyText = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
		return {
			readyState: document.readyState,
			visibilityState: document.visibilityState,
			location: { pathname: window.location.pathname, search: window.location.search },
			htmlClass: document.documentElement.className || "",
			bodyClass: document.body?.className || "",
			headChildren: document.head?.childElementCount || 0,
			bodyChildren: document.body?.childElementCount || 0,
			bodyTextLen: bodyText.length,
			bodyTextHash: bodyText ? shortHash(bodyText) : null,
			activeElement: describeNode(document.activeElement),
			scroll: { x: Math.round(window.scrollX), y: Math.round(window.scrollY) },
			dom: summarizeDom(),
		};
	} catch {
		return { error: true };
	}
}

function shortHash(text: string): string {
	let hash = 5381;
	for (let i = 0; i < text.length; i += 1) {
		hash = ((hash << 5) + hash) ^ text.charCodeAt(i);
	}
	return (hash >>> 0).toString(16);
}

function readStoredReloadSnapshot() {
	try {
		const raw = sessionStorage.getItem(RELOAD_SNAPSHOT_KEY);
		if (!raw) return null;
		sessionStorage.removeItem(RELOAD_SNAPSHOT_KEY);
		return JSON.parse(raw);
	} catch {
		return { error: true };
	}
}

function storeReloadSnapshot(reason: string) {
	try {
		const snapshot = {
			reason,
			iso: new Date().toISOString(),
			dateNow: Date.now(),
			timeOrigin: performance.timeOrigin,
			now: performance.now(),
			nav: summarizeNavigation(),
			document: summarizeDocumentTree(),
			result: summarizeResultSurface(),
			sidebar: summarizeSidebarSurface(),
		};
		sessionStorage.setItem(RELOAD_SNAPSHOT_KEY, JSON.stringify(snapshot));
	} catch {}
}

function rectFor(element: Element | null) {
	try {
		if (!element) return null;
		const rect = element.getBoundingClientRect();
		return {
			x: Math.round(rect.x),
			y: Math.round(rect.y),
			w: Math.round(rect.width),
			h: Math.round(rect.height),
			top: Math.round(rect.top),
			bottom: Math.round(rect.bottom),
		};
	} catch {
		return null;
	}
}

function summarizeResultSurface() {
	try {
		const panel = document.querySelector("[data-debug-result-panel]");
		const stats = document.querySelector("[data-debug-stats-block]");
		const statsText = (stats?.textContent || "").replace(/\s+/g, " ").trim();
		const panelText = (panel?.textContent || "").replace(/\s+/g, " ").trim();
		return {
			resultPanel: {
				present: Boolean(panel),
				mode: panel?.getAttribute("data-debug-result-panel") || null,
				rect: rectFor(panel),
				textLen: panelText.length,
				textHash: panelText ? shortHash(panelText) : null,
				placeholder: /Click Fit, Tailor, or Judge|Processing/.test(panelText),
			},
			statsBlock: {
				present: Boolean(stats),
				rect: rectFor(stats),
				textLen: statsText.length,
				textHash: statsText ? shortHash(statsText) : null,
				hasTotalTime: /Total time:/i.test(statsText),
				preview: statsText.slice(0, 180),
			},
		};
	} catch {
		return { error: true };
	}
}

function describeNode(node: Node | null) {
	try {
		if (!node) return null;
		if (node.nodeType === Node.TEXT_NODE) {
			const text = (node.textContent || "").replace(/\s+/g, " ").trim();
			return text ? `#text:${text.slice(0, 80)}` : "#text";
		}
		if (!(node instanceof Element)) return `node:${node.nodeType}`;
		const id = node.id ? `#${node.id}` : "";
		const classes = node.className ? `.${String(node.className).split(/\s+/).slice(0, 4).join(".")}` : "";
		const debug = node.getAttribute("data-debug-result-panel")
			? `[data-debug-result-panel=${node.getAttribute("data-debug-result-panel")}]`
			: node.getAttribute("data-debug-stats-block")
				? "[data-debug-stats-block]"
				: "";
		return `${node.tagName.toLowerCase()}${id}${debug}${classes}`;
	} catch {
		return "unknown";
	}
}

function summarizeSidebarSurface() {
	try {
		const sidebar = document.querySelector(".hidden.md\\:block");
		const captchaBox = document.querySelector(".cf-turnstile");
		const cloudflareFrames = Array.from(document.querySelectorAll("iframe")).filter((frame) => /turnstile|cloudflare/i.test((frame as HTMLIFrameElement).src || ""));
		const labels = sidebar ? Array.from(sidebar.querySelectorAll("label")).map((label) => {
			const input = label.querySelector("input");
			const rect = label.getBoundingClientRect();
			return {
				text: (label.textContent || "").replace(/\s+/g, " ").trim().slice(0, 60),
				y: Math.round(rect.y),
				h: Math.round(rect.height),
				type: input?.type || null,
				checked: input ? input.checked : null,
			};
		}).filter((label) => label.y >= 0 && label.y <= window.innerHeight).slice(0, 28) : [];
		return {
			sidebar: sidebar ? { rect: rectFor(sidebar), textLen: (sidebar.textContent || "").length } : null,
			captchaBox: captchaBox ? { rect: rectFor(captchaBox), children: captchaBox.childElementCount } : null,
			cloudflareFrames: cloudflareFrames.length,
			labels,
		};
	} catch {
		return { error: true };
	}
}

function summarizeNavigation() {
	try {
		const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
		if (!nav) return {};
		return {
			type: nav.type,
			redirectCount: nav.redirectCount,
			domContentLoadedMs: Math.round(nav.domContentLoadedEventEnd),
			loadMs: Math.round(nav.loadEventEnd),
			transferSize: nav.transferSize,
		};
	} catch {
		return {};
	}
}

function summarizePaintTimings() {
	try {
		return performance.getEntriesByType("paint").map((entry) => ({
			name: entry.name,
			startMs: Math.round(entry.startTime),
		}));
	} catch {
		return [];
	}
}

function summarizeEarlyResources() {
	try {
		return performance.getEntriesByType("resource")
			.filter((entry) => /\.(css|js)(?:\?|$)/.test(entry.name) || /font|woff|turnstile|challenges\.cloudflare/i.test(entry.name))
			.slice(0, 12)
			.map((entry) => {
				const timing = entry as PerformanceResourceTiming;
				return {
					name: entry.name.replace(window.location.origin, ""),
					type: timing.initiatorType || "resource",
					startMs: Math.round(entry.startTime),
					durationMs: Math.round(entry.duration),
					transferSize: timing.transferSize,
				};
			});
	} catch {
		return [];
	}
}

function clipData(data: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
	if (!data) return undefined;
	try {
		return JSON.parse(JSON.stringify(data, (_key, value) => {
			if (typeof value === "string" && value.length > 240) return `${value.slice(0, 240)}...`;
			return value;
		}));
	} catch {
		return { unserializable: true };
	}
}

export default function HomepageDebugOverlay({ seed }: { seed: DebugSeed }) {
	const startedAtRef = useRef<number>(0);
	const mutationCountRef = useRef(0);
	const mutationSamplesRef = useRef<Array<Record<string, unknown>>>([]);
	const [events, setEvents] = useState<DebugEvent[]>([]);
	const [minimized, setMinimized] = useState(true);

	const addEvent = (name: string, data?: Record<string, unknown>) => {
		const now = performance.now();
		const startedAt = startedAtRef.current || now;
		const event: DebugEvent = {
			iso: new Date().toISOString(),
			relMs: Math.round(now - startedAt),
			name,
			data: clipData(data),
		};
		setEvents((prev) => [...prev.slice(-249), event]);
	};

	useEffect(() => {
		startedAtRef.current = performance.now();
		const previousReloadSnapshot = readStoredReloadSnapshot();
		const earlyReload = (window as any).__rtEarlyReload || null;
		addEvent("overlay.mounted", {
			pathname: window.location.pathname,
			search: window.location.search,
			seed,
			nav: summarizeNavigation(),
			paint: summarizePaintTimings(),
			dom: summarizeDom(),
		});
		if (previousReloadSnapshot) {
			addEvent("previous_document.unloaded", {
				previous: previousReloadSnapshot,
				currentHead: earlyReload,
				gapMs: typeof previousReloadSnapshot.dateNow === "number" && earlyReload?.dateNow ? earlyReload.dateNow - previousReloadSnapshot.dateNow : null,
			});
		}
		if (earlyReload) {
			addEvent("current_document.head_script", {
				early: earlyReload,
				overlayDelayMs: typeof earlyReload.now === "number" ? Math.round(performance.now() - earlyReload.now) : null,
				document: summarizeDocumentTree(),
			});
		}

		const onDomReady = () => addEvent("document.dom_content_loaded", { dom: summarizeDom(), document: summarizeDocumentTree() });
		const onLoad = () => addEvent("window.load", { nav: summarizeNavigation(), paint: summarizePaintTimings(), resources: summarizeEarlyResources(), dom: summarizeDom(), document: summarizeDocumentTree() });
		const onVisibility = () => addEvent("document.visibility", { state: document.visibilityState });
		const onResize = () => addEvent("window.resize", { width: window.innerWidth, height: window.innerHeight, dom: summarizeDom() });
		const onPageHide = (event: PageTransitionEvent) => {
			storeReloadSnapshot(event.persisted ? "pagehide.persisted" : "pagehide");
			addEvent("current_document.pagehide", { persisted: event.persisted, document: summarizeDocumentTree() });
		};
		const onBeforeUnload = () => {
			storeReloadSnapshot("beforeunload");
		};
		const onRtAuth = (event: Event) => addEvent("rt-auth", { detail: (event as CustomEvent).detail || null });
		const onRtInputs = (event: Event) => {
			const detail = ((event as CustomEvent).detail || {}) as Record<string, unknown>;
			addEvent("rt-inputs", {
				resumeLength: typeof detail.resumeText === "string" ? detail.resumeText.length : undefined,
				jdLength: typeof detail.jdText === "string" ? detail.jdText.length : undefined,
				resumeTs: detail.rTs,
				jdTs: detail.jTs,
			});
		};
			const onRtOutputs = (event: Event) => {
			const detail = ((event as CustomEvent).detail || {}) as Record<string, unknown>;
			addEvent("rt-outputs", {
				resultType: detail.resultType,
				fitLength: typeof detail.fitOutput === "string" ? detail.fitOutput.length : undefined,
				tailoredLength: typeof detail.tailoredOutput === "string" ? detail.tailoredOutput.length : undefined,
				judgeLength: typeof detail.judgeOutput === "string" ? detail.judgeOutput.length : undefined,
				fitTs: detail.fitTs,
				tailorTs: detail.tailorTs,
				judgeTs: detail.judgeTs,
				rtypeTs: detail.rtypeTs,
			});
			};
			const addResultSnapshot = (name: string) => addEvent(name, { surface: summarizeResultSurface() });
			const addSidebarSnapshot = (name: string) => addEvent(name, { surface: summarizeSidebarSurface() });

		if (document.readyState === "loading") {
			document.addEventListener("DOMContentLoaded", onDomReady, { once: true });
		} else {
			addEvent("document.already_ready", { readyState: document.readyState, dom: summarizeDom() });
		}
		if (document.readyState !== "complete") {
			window.addEventListener("load", onLoad, { once: true });
		} else {
			addEvent("window.already_loaded", { nav: summarizeNavigation(), paint: summarizePaintTimings(), resources: summarizeEarlyResources(), dom: summarizeDom(), document: summarizeDocumentTree() });
		}
		document.addEventListener("visibilitychange", onVisibility);
		window.addEventListener("resize", onResize);
		window.addEventListener("pagehide", onPageHide);
		window.addEventListener("beforeunload", onBeforeUnload);
		window.addEventListener("rt-auth", onRtAuth as EventListener);
		window.addEventListener("rt-inputs", onRtInputs as EventListener);
		window.addEventListener("rt-outputs", onRtOutputs as EventListener);

		let layoutShiftObserver: PerformanceObserver | null = null;
		let longTaskObserver: PerformanceObserver | null = null;
		try {
			layoutShiftObserver = new PerformanceObserver((list) => {
				for (const entry of list.getEntries() as any[]) {
					if (entry.hadRecentInput) continue;
					addEvent("layout.shift", {
						value: Number(entry.value || 0).toFixed(4),
						startMs: Math.round(entry.startTime || 0),
						sources: Array.isArray(entry.sources) ? entry.sources.slice(0, 3).map((source: any) => {
							const node = source?.node as Element | undefined;
							return node ? `${node.tagName.toLowerCase()}${node.id ? `#${node.id}` : ""}${node.className ? `.${String(node.className).split(/\s+/).slice(0, 2).join(".")}` : ""}` : "unknown";
						}) : [],
					});
				}
			});
			layoutShiftObserver.observe({ type: "layout-shift", buffered: true } as PerformanceObserverInit);
		} catch {
			addEvent("observer.layout_shift.unavailable");
		}
		try {
			longTaskObserver = new PerformanceObserver((list) => {
				for (const entry of list.getEntries()) {
					addEvent("main_thread.long_task", {
						startMs: Math.round(entry.startTime),
						durationMs: Math.round(entry.duration),
					});
				}
			});
			longTaskObserver.observe({ type: "longtask", buffered: true } as PerformanceObserverInit);
		} catch {
			addEvent("observer.long_task.unavailable");
		}

		let resultMutationObserver: MutationObserver | null = null;
		let resultResizeObserver: ResizeObserver | null = null;
		const attachResultObservers = () => {
			try {
				const targets = Array.from(document.querySelectorAll("[data-debug-result-panel], [data-debug-stats-block]"));
				if (targets.length === 0) return;
				resultMutationObserver?.disconnect();
				resultMutationObserver = new MutationObserver((mutations) => {
					addEvent("result_surface.mutations", {
						count: mutations.length,
						surface: summarizeResultSurface(),
					});
				});
				for (const target of targets) {
					resultMutationObserver.observe(target, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["class", "style", "data-debug-result-panel"] });
				}
				if (typeof ResizeObserver !== "undefined") {
					resultResizeObserver?.disconnect();
					resultResizeObserver = new ResizeObserver((entries) => {
						addEvent("result_surface.resize", {
							count: entries.length,
							surface: summarizeResultSurface(),
						});
					});
					for (const target of targets) resultResizeObserver.observe(target);
				}
				addResultSnapshot("result_surface.observers_attached");
			} catch {
				addEvent("result_surface.observers_unavailable");
			}
		};

			const mutationObserver = new MutationObserver((mutations) => {
				mutationCountRef.current += mutations.length;
				for (const mutation of mutations) {
					if (mutationSamplesRef.current.length >= 24) break;
					mutationSamplesRef.current.push({
						type: mutation.type,
						target: describeNode(mutation.target),
						attr: mutation.attributeName,
						added: Array.from(mutation.addedNodes).slice(0, 3).map(describeNode),
						removed: Array.from(mutation.removedNodes).slice(0, 3).map(describeNode),
					});
				}
				if (mutations.some((mutation) => Array.from(mutation.addedNodes).some((node) => node instanceof Element && (node.matches("[data-debug-result-panel], [data-debug-stats-block]") || node.querySelector("[data-debug-result-panel], [data-debug-stats-block]"))))) {
					attachResultObservers();
				}
			});
		try {
			mutationObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class", "style", "hidden", "aria-hidden"] });
		} catch {}
		const mutationFlush = window.setInterval(() => {
				if (!mutationCountRef.current) return;
				const count = mutationCountRef.current;
				const samples = mutationSamplesRef.current;
				mutationCountRef.current = 0;
				mutationSamplesRef.current = [];
				addEvent("dom.mutations", { count, samples, dom: summarizeDom(), sidebar: summarizeSidebarSurface() });
			}, 500);
		const raf = window.requestAnimationFrame(() => addEvent("paint.next_frame", { dom: summarizeDom() }));
			attachResultObservers();
			addResultSnapshot("result_surface.mounted");
			addSidebarSnapshot("sidebar_surface.mounted");
			const resultTimers = [100, 250, 500, 1000, 3000].map((delay) => (
				window.setTimeout(() => {
					addResultSnapshot(`result_surface.t_${delay}ms`);
					addSidebarSnapshot(`sidebar_surface.t_${delay}ms`);
				}, delay)
			));
			const settleTimer = window.setTimeout(() => addEvent("page.settled_3s", { nav: summarizeNavigation(), paint: summarizePaintTimings(), resources: summarizeEarlyResources(), dom: summarizeDom() }), 3000);

		return () => {
			document.removeEventListener("DOMContentLoaded", onDomReady);
				window.removeEventListener("load", onLoad);
				document.removeEventListener("visibilitychange", onVisibility);
				window.removeEventListener("resize", onResize);
				window.removeEventListener("pagehide", onPageHide);
				window.removeEventListener("beforeunload", onBeforeUnload);
				window.removeEventListener("rt-auth", onRtAuth as EventListener);
			window.removeEventListener("rt-inputs", onRtInputs as EventListener);
			window.removeEventListener("rt-outputs", onRtOutputs as EventListener);
			layoutShiftObserver?.disconnect();
			longTaskObserver?.disconnect();
			resultMutationObserver?.disconnect();
			resultResizeObserver?.disconnect();
			mutationObserver.disconnect();
			window.clearInterval(mutationFlush);
			window.cancelAnimationFrame(raf);
			for (const timer of resultTimers) window.clearTimeout(timer);
			window.clearTimeout(settleTimer);
		};
	// Run once so the earliest client-side events stay ordered from mount.
	// eslint-disable-next-line react-hooks/exhaustive-deps
	}, []);

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
				width: minimized ? 230 : "min(720px, calc(100vw - 24px))",
				maxHeight: minimized ? 44 : "min(520px, calc(100vh - 24px))",
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
				<strong style={{ color: "#93c5fd", marginRight: "auto" }}>Homepage Load Debug</strong>
				<button
					type="button"
					onClick={() => navigator.clipboard?.writeText(copyText).catch(() => {})}
					style={{ color: "#bfdbfe", background: "rgba(30, 41, 59, 0.9)", border: "1px solid rgba(148, 163, 184, 0.4)", borderRadius: 6, padding: "3px 8px" }}
				>
					copy
				</button>
				<button
					type="button"
					onClick={() => setEvents([])}
					style={{ color: "#bfdbfe", background: "transparent", border: "1px solid rgba(148, 163, 184, 0.35)", borderRadius: 6, padding: "3px 8px" }}
				>
					clear
				</button>
				<button
					type="button"
					onClick={() => setMinimized((value) => !value)}
					style={{ color: "#bfdbfe", background: "transparent", border: "1px solid rgba(148, 163, 184, 0.35)", borderRadius: 6, padding: "3px 8px" }}
				>
					{minimized ? "unhide" : "hide"}
				</button>
			</div>
			{!minimized ? (
				<div style={{ maxHeight: 470, overflow: "auto", padding: 10 }}>
					{events.length === 0 ? (
						<div style={{ color: "#94a3b8" }}>Waiting for events...</div>
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
