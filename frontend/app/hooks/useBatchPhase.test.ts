import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import useBatchPhase from '@/hooks/useBatchPhase';

// Minimal polyfill for EventSource used inside the hook.
class MockEventSource {
  url: string; withCredentials?: boolean; readyState = 0; onmessage: ((ev: MessageEvent)=>void)|null=null; onerror: (()=>void)|null=null;
  constructor(url: string, opts: any){ this.url = url; this.withCredentials = opts?.withCredentials; MockEventSource.instances.push(this); }
  close(){ this.readyState = 2; }
  // helper to emit a message
  emit(data: any){ this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent); }
  fail(){ this.onerror?.(); }
  static instances: MockEventSource[] = [];
}

// @ts-ignore override global
global.EventSource = MockEventSource as any;

// Mock fetch for result + cancel fallback
const fetchMock = vi.fn(async (url: string) => ({ ok: false }));
// @ts-ignore
global.fetch = fetchMock;

// Helper to flush promises
const flush = () => new Promise(res => setTimeout(res, 0));

describe('useBatchPhase', () => {
  it('maintains submission order in markdown, marks failures, and cancels remaining', async () => {
    const { result } = renderHook(() => useBatchPhase());

    // Submit three aliases
    const submitFn = vi.fn(async (alias: string) => ({ jobId: alias.toUpperCase()+"_ID" }));

    await act(async () => {
      await result.current.startBatch('fit', ['alpha','beta','gamma'], submitFn);
    });

    // Instances correspond in submission order to alpha,beta,gamma
    const [esAlpha, esBeta, esGamma] = MockEventSource.instances;

    // Finish out of order: beta succeeds, alpha fails, gamma still running
    act(() => { esBeta.emit({ status: 'completed', text: 'B DONE'}); });
    act(() => { esAlpha.emit({ status: 'failed', error: 'Boom'}); });

    await flush();
    // Cancel remaining (gamma)
    await act(async () => { await result.current.cancelBatch(); });

    const md = result.current.batchMarkdown.trim();
    const lines = md.split(/\n+/);
    // Order block headers should follow alpha, beta, gamma (submission order) even though completion order differed
    const headers = lines.filter(l => l.startsWith('### '));
    expect(headers).toEqual(['### alpha','### beta','### gamma']);

    // Failed job shows marker
    expect(md).toMatch(/### alpha[\s\S]*\*Failed: /);
    // Beta succeeded text present
    expect(md).toMatch(/### beta\nB DONE/);
    // Gamma cancelled
    expect(md).toMatch(/### gamma\n\*Cancelled\*/);
  });
});
