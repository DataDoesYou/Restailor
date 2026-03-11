/**
 * IOH Button Analytics Helper
 * 
 * Use these utilities in the browser console to debug flaky IOH button behavior.
 * 
 * Available commands (DEV ONLY):
 * - window.__getStageAnalytics() - Get all analytics events
 * - window.__clearStageAnalytics() - Clear analytics buffer
 * - window.__analyzeStageIssues() - Get analysis of potential issues
 * - window.__exportStageAnalytics() - Export as JSON file
 * 
 * NOTE: These helpers are stripped from production builds.
 */

declare global {
  interface Window {
    __getStageAnalytics?: () => any[];
    __clearStageAnalytics?: () => void;
    __analyzeStageIssues?: () => any;
    __exportStageAnalytics?: () => void;
  }
}

export function setupAnalyticsHelpers() {
  if (typeof window === 'undefined') return;
  
  // Production guard: these debug helpers are for development only
  if (process.env.NODE_ENV === 'production') {
    return;
  }

  /**
   * Analyze analytics for common issues
   */
  window.__analyzeStageIssues = () => {
    const events = window.__getStageAnalytics?.() || [];
    
    const analysis = {
      summary: {
        totalEvents: events.length,
        eventTypes: {} as Record<string, number>,
        instances: new Set<string>(),
      },
      issues: [] as any[],
      timeline: [] as any[],
    };

    // Count event types
    events.forEach((e: any) => {
      analysis.summary.eventTypes[e.event] = (analysis.summary.eventTypes[e.event] || 0) + 1;
      if (e.data.instanceId) {
        analysis.summary.instances.add(e.data.instanceId);
      }
    });

    // Find issues
    
    // Issue 1: Prop changes while optimistic update active
    const blockedSyncs = events.filter((e: any) => 
      e.event === 'sync_blocked_optimistic_flags' || e.event === 'sync_blocked_optimistic_applied'
    );
    if (blockedSyncs.length > 0) {
      analysis.issues.push({
        type: 'blocked_sync_during_optimistic',
        severity: 'warning',
        count: blockedSyncs.length,
        message: 'Props tried to update during optimistic mutation (this is OK if infrequent)',
        events: blockedSyncs,
      });
    }

    // Issue 2: Multiple rapid renders
    const renderEvents = events.filter((e: any) => e.event === 'render');
    const instanceRenders = new Map<string, number>();
    renderEvents.forEach((e: any) => {
      const id = e.data.instanceId;
      instanceRenders.set(id, (instanceRenders.get(id) || 0) + 1);
    });
    
    instanceRenders.forEach((count, instanceId) => {
      if (count > 10) {
        analysis.issues.push({
          type: 'excessive_renders',
          severity: 'error',
          count,
          instanceId,
          message: `Component ${instanceId} rendered ${count} times (possible render loop)`,
        });
      }
    });

    // Issue 3: Mutation errors
    const mutationErrors = events.filter((e: any) => 
      e.event === 'mutation_flag_error' || e.event === 'mutation_applied_error'
    );
    if (mutationErrors.length > 0) {
      analysis.issues.push({
        type: 'mutation_errors',
        severity: 'error',
        count: mutationErrors.length,
        message: 'Mutations failed (network issues or validation errors)',
        events: mutationErrors,
      });
    }

    // Issue 4: State mismatches (prop vs local)
    const renderEventsWithMismatch = renderEvents.filter((e: any) => {
      const { propsFlags, localFlags } = e.data;
      if (!propsFlags || !localFlags) return false;
      return (
        propsFlags.interviewing !== localFlags.interviewing ||
        propsFlags.offer !== localFlags.offer ||
        propsFlags.hired !== localFlags.hired
      );
    });
    
    if (renderEventsWithMismatch.length > 2) {
      analysis.issues.push({
        type: 'state_mismatch',
        severity: 'warning',
        count: renderEventsWithMismatch.length,
        message: 'Props and local state frequently out of sync',
        events: renderEventsWithMismatch,
      });
    }

    // Issue 5: Slow mutations
    const successEvents = events.filter((e: any) => 
      e.event === 'mutation_flag_success' || e.event === 'mutation_applied_success'
    );
    const slowMutations = successEvents.filter((e: any) => e.data.durationMs > 2000);
    if (slowMutations.length > 0) {
      analysis.issues.push({
        type: 'slow_mutations',
        severity: 'warning',
        count: slowMutations.length,
        message: 'Some mutations took >2s to complete',
        events: slowMutations,
      });
    }

    // Build timeline
    analysis.timeline = events.map((e: any, idx: number) => ({
      index: idx,
      relativeTime: idx > 0 ? e.timestamp - events[0].timestamp : 0,
      event: e.event,
      instanceId: e.data.instanceId,
      key: e.data.key,
      value: e.data.value,
      duration: e.data.durationMs,
    }));

    return analysis;
  };

  /**
   * Export analytics as downloadable JSON
   */
  window.__exportStageAnalytics = () => {
    const events = window.__getStageAnalytics?.() || [];
    const analysis = window.__analyzeStageIssues?.() || {};
    
    const exportData = {
      exportedAt: new Date().toISOString(),
      url: window.location.href,
      userAgent: navigator.userAgent,
      events,
      analysis,
    };
    
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `stage-analytics-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    console.log('✅ Analytics exported successfully');
  };

  console.log(`
🔍 IOH Button Analytics Helpers Loaded

Available commands:
  window.__getStageAnalytics()      - View all events
  window.__analyzeStageIssues()     - Analyze for issues
  window.__exportStageAnalytics()   - Export as JSON
  window.__clearStageAnalytics()    - Clear buffer

Example usage:
  const analysis = window.__analyzeStageIssues();
  console.table(analysis.issues);
  `);
}

// Auto-setup in development
if (typeof window !== 'undefined' && process.env.NODE_ENV !== 'production') {
  setupAnalyticsHelpers();
}

export {};
