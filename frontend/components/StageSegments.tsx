"use client";

import React from "react";
import Tooltip from "./ui/Tooltip";
import { applyStageToggle, normalizeStageFlags, StageFlagState } from "@/lib/stageFlags";

// Analytics tracking for debugging flaky hydration
type StageAnalyticsEvent = {
  timestamp: number;
  event: string;
  data: Record<string, unknown>;
};

const analyticsBuffer: StageAnalyticsEvent[] = [];
const MAX_ANALYTICS_BUFFER = 100;

function trackStageEvent(event: string, data: Record<string, unknown> = {}) {
  if (typeof window === "undefined") return;
  
  const entry: StageAnalyticsEvent = {
    timestamp: Date.now(),
    event,
    data: {
      ...data,
      url: window.location.href,
      userAgent: navigator.userAgent.substring(0, 50),
    },
  };
  
  analyticsBuffer.push(entry);
  if (analyticsBuffer.length > MAX_ANALYTICS_BUFFER) {
    analyticsBuffer.shift();
  }
  
  // TEMPORARILY DISABLED FOR DEBUGGING
  // Log to console in development
  // if (process.env.NODE_ENV !== "production") {
  //   console.debug(`[StageSegments::${event}]`, data);
  // }
  
  // Store in sessionStorage for later retrieval
  try {
    window.sessionStorage.setItem(
      "rt_stage_analytics",
      JSON.stringify(analyticsBuffer.slice(-50))
    );
  } catch {}
}

// Expose analytics retrieval globally
if (typeof window !== "undefined") {
  (window as any).__getStageAnalytics = () => analyticsBuffer;
  (window as any).__clearStageAnalytics = () => {
    analyticsBuffer.length = 0;
    try {
      window.sessionStorage.removeItem("rt_stage_analytics");
    } catch {}
  };
}

export type StageFlags = StageFlagState;

export type StageSegmentsProps = {
  flags?: StageFlags;
  appliedActive?: boolean;
  disabled?: boolean;
  pendingStages?: Set<'applied' | 'interviewing' | 'offer' | 'hired'>; // Tracks which buttons are loading
  onToggleApplied?: (next: boolean) => void | Promise<void>;
  onToggleFlag?: (k: keyof StageFlags, next: boolean) => void | Promise<void>;
  testId?: string; // For e2e testing
};

type SegmentKey = "applied" | "interviewing" | "offer" | "hired";

const STAGES: { key: SegmentKey; label: string; short: string }[] = [
  { key: "applied", label: "Applied", short: "A" },
  { key: "interviewing", label: "Interviewing", short: "I" },
  { key: "offer", label: "Offer", short: "O" },
  { key: "hired", label: "Hired", short: "H" },
];

function classNames(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}

export default function StageSegments({ flags, appliedActive, disabled, pendingStages, onToggleApplied, onToggleFlag, testId }: StageSegmentsProps) {
  // PESSIMISTIC: Render directly from props - no local state, no optimistic updates
  const normalizedFlags = normalizeStageFlags(flags);
  const appliedChecked = !!appliedActive;

  // Simple click handlers - just call the callbacks
  const handleAppliedClick = React.useCallback(async () => {
    try {
      const next = !appliedChecked;
      if (onToggleApplied) {
        await onToggleApplied(next);
      }
    } catch (error) {
      console.error('[StageSegments] Applied click error:', error);
      throw error; // Re-throw to surface to user
    }
  }, [appliedChecked, onToggleApplied]);

  const handleFlagClick = React.useCallback(
    async (key: keyof StageFlags) => {
      try {
        if (disabled) {
          return;
        }
        const next = !normalizedFlags[key];
        if (onToggleFlag) {
          await onToggleFlag(key, next);
        }
      } catch (error) {
        console.error('[StageSegments] Flag click error:', { key, error });
        throw error; // Re-throw to surface to user
      }
    },
    [disabled, normalizedFlags, onToggleFlag]
  );

  return (
    <div className="inline-flex items-center gap-x-1" data-testid={testId}>
      {STAGES.map((stage) => {
        const isAppliedButton = stage.key === "applied";
        const isPending = pendingStages?.has(stage.key) ?? false;
        const perButtonDisabled = (disabled && stage.key !== "applied") || isPending;
        
        const base = "h-8 w-8 rounded flex items-center justify-center border text-sm font-medium transition-colors select-none relative";
        const neutral = perButtonDisabled
          ? "bg-transparent text-slate-300 border-slate-500/60 opacity-60"
          : "bg-transparent text-slate-300 border-slate-500/60 hover:text-white hover:border-white";
        const iohActive = "bg-transparent text-white border-white";
        const aOrange = "bg-transparent text-amber-500 border-amber-500";
        
        // PESSIMISTIC: Read directly from props
        const isSelected = isAppliedButton ? appliedChecked : !!normalizedFlags[stage.key as keyof StageFlags];
        const cls = classNames(base, isAppliedButton ? (appliedChecked ? aOrange : neutral) : isSelected ? iohActive : neutral);
        const onClick = isAppliedButton ? handleAppliedClick : () => handleFlagClick(stage.key as keyof StageFlags);
        
        return (
          <Tooltip key={stage.key} content={stage.label}>
            <button
              type="button"
              aria-label={stage.label}
              aria-busy={isPending}
              className={cls}
              onClick={onClick}
              disabled={perButtonDisabled}
              title={stage.label}
            >
              {isPending ? (
                <div className="h-3 w-3 border-2 border-slate-500 border-t-amber-500 rounded-full animate-spin" aria-hidden="true" />
              ) : (
                stage.short
              )}
              {isPending && <span className="sr-only" aria-live="polite">Updating {stage.label}...</span>}
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
