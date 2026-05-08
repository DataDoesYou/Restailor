# Architecture

This document describes the public, self-hosted architecture of Restailor.

## System Components

- Frontend: Next.js application in `frontend/` serving the browser UI and proxying selected API requests.
- API layer: FastAPI application in `main.py` exposing authentication, job orchestration, application tracking, analytics, and admin endpoints.
- Worker layer: ARQ worker in `worker.py` consuming queued background jobs from Redis.
- Data layer: PostgreSQL stores users, jobs, job outputs, applications, balances, charges, and audit data. Redis is used for queueing, coordination, and selected ephemeral state.

## API Layer

The API handles:

- Authentication and session-related flows
- Resume tailoring and fit-analysis requests
- Streaming output to the frontend via Server-Sent Events
- Application history and analytics endpoints
- Admin and maintenance endpoints protected by auth and step-up checks

The API depends on environment configuration loaded from `.env`, runtime environment variables, and `config/app.toml` defaults.

## Data Layer

- PostgreSQL is the system of record.
- SQLAlchemy models live in `restailor/models.py` and migrations live in `alembic/versions/`.
- Sensitive user content is designed to be encrypted at rest through `PII_ENCRYPTION_KEY`.
- Redis is used by ARQ and for selected transient coordination tasks such as queueing and rate-limit support.

## LLM and Processing Pipeline

Typical request flow:

1. The frontend submits a tailoring or fit request to the API.
2. The API validates input, records job state, and enqueues background work.
3. The worker processes the job, calls an enabled provider through `services/llm.py`, and writes progress and results back to storage.
4. The frontend polls or subscribes to SSE updates until the job completes.

The provider layer is optional but at least one provider key is required for live tailoring behavior.

## External Integrations

Optional integrations include:

- OpenAI, Anthropic, Gemini, and Grok for model execution
- SMTP for verification, login, and notification emails
- Stripe is inert for normal user flows; Budget tracks BYOK provider-cost-equivalent usage
- WebAuthn-compatible authenticators for passkeys
- A secret manager such as Doppler for production secret injection

## Deployment Model

Local development is supported with:

- Python and Poetry for backend dependencies
- Node.js for frontend dependencies
- Docker Compose for PostgreSQL, Redis, and optionally the full stack

Production deployment assumes:

- A managed or self-hosted PostgreSQL database
- A Redis instance
- Separate API, worker, and frontend processes or containers
- Environment variables injected by the hosting platform or a secret manager

The repository includes Dockerfiles for the API, worker, and frontend. A sanitized example Render blueprint is provided in `render.example.yaml` for self-hosters.

### Auth Flow
- **POST /signup** → create user account
- **POST /token** → issue JWT access token (bearer)
- **Step-up for sensitive actions:** POST /auth/stepup/start (TOTP/recovery/email OTP) or WebAuthn options/verify

### Job Flow
- **POST /jobs | /tailor/submit | /fit | /judge** → enqueue work, return job_id (role inferred from path for shortcuts)
- Input gating (sanitization, caps, URL policy, idempotency) precedes enqueue
- **GET /jobs/{id}/status** → poll; POST /jobs/{id}/cancel → cancel; GET /jobs/{id}/result → fetch
- **GET /jobs/{id}/stream** → server-sent events streaming progress/output
- **Benchmark** (admin start → rank → optional judge): /benchmark/start creates container, /benchmark/rank executes multi-model candidates (job_flow=benchmark_rank), /benchmark/await_and_judge convenience to block until ranking then judge

### Admin/Credits (Scoped)
- Admin-only endpoints read from pricing/credits config and ledger tables

---

## Data at Rest

- **PII payloads** are encrypted using pgcrypto via app-supplied symmetric key (PII_ENCRYPTION_KEY)
- **Access tokens** per job act as capability tokens for user-owned polling
- **Opt-out flag** `dont_save_future_data` prevents persistence of new resume/JD/output blobs

---

## History & Analytics Data Flow (Single Source of Truth)

### Applications Table as Primary Source
- The `applications` table is the **canonical source** for all job application stage flags: `is_applied`, `is_interviewing`, `is_offer`, `is_hired`
- When a job's stage changes (e.g., marking as hired), the change cascades to all linked applications via `UPDATE applications SET is_hired=TRUE WHERE job_id = ...`
- Unique constraint on `(user_id, jd_hash)` ensures one canonical application per job description
- JSONB `job_input_hashes` column stores deterministic hash hints for efficient history hydration without redundant PII decrypts

### Analytics Snapshot State
- `analytics_job_snapshot_state` table provides a denormalized view for analytics queries
- `is_active` flag filters out archived/deleted/test jobs for clean funnel metrics
- Stage resolution uses shared helpers in `restailor.stage_utils` ensuring consistency across:
  - History endpoint (`/applications/list`)
  - Analytics endpoints (`/analytics/*`)
  - Job lifecycle updates
  - Frontend stage toggles

### Data Consistency
- Migration `20251008_applications_job_hash_hints` backfills hash hints for existing rows
- Migration `20251007_applications_stage_cleanup` established stage flag columns
- Migration `20251006_add_job_stage_columns` added corresponding job-level flags
- All mutations call `_derive_jd_projection` and `_derive_job_input_hashes` to maintain consistency
- Snapshot rebuilds via `services/analytics_job_snapshot.py` run automatically or on-demand

---

## State Management: Database-Only Architecture

### Core Principles

**All state in PostgreSQL:**
- ✅ Applied checkbox state → `applications.is_applied`
- ✅ IOH button states → `applications.is_interviewing/is_offer/is_hired`
- ✅ Model settings → `user_preferences` table
- ✅ Job stage history → `applications` table with timestamps
- ❌ NO cookies for application state
- ❌ NO sessionStorage for application state
- ❌ NO localStorage for application state (React Query handles in-memory caching only)

**Database is single source of truth:**
- Database commits are immediate (< 50ms typical response time)
- All pages query database on load
- UI reflects database state exactly (no optimistic updates)

---

## Pessimistic UI Pattern

### Pattern Overview

**Replaced optimistic pattern (October 2025)** with pessimistic pattern for better reliability and simpler debugging.

#### Before: Optimistic Pattern (REMOVED)
```typescript
// ❌ REMOVED: Immediate UI update
setIsApplied(!isApplied);
document.cookie = `rt_history_dirty=1; Path=/`;

// API call in background
await updateApplicationStage(...);

// If error, rollback
if (error) setIsApplied(!isApplied);
```

**Problems:**
- Complex rollback logic
- State/database divergence possible
- Race conditions across tabs
- Coordination cookies needed

#### After: Pessimistic Pattern (CURRENT)
```typescript
// ✅ CURRENT: Loading state first
setIsSaving(true);

try {
  // API call blocks UI
  const response = await updateApplicationStage(...);
  
  // Update UI to match server response
  setIsApplied(response.is_applied);
  
  // React Query automatically invalidates related queries
  queryClient.invalidateQueries(['applications']);
} catch (error) {
  // Show error, keep previous state
  showError(error);
} finally {
  setIsSaving(false);
}
```

**Benefits:**
- Single source of truth (database always correct)
- No stale data or race conditions
- Simple debugging (just check database)
- Multi-tab support via visibility events
- No optimistic rollback complexity
- Explicit loading states improve perceived performance

---

### Implementation Details

#### 1. Applied Checkbox (Resume Tailor Page)

**Component:** `frontend/components/pages/ResumeTailorClient.tsx`

**Features:**
- Spinner indicator next to checkbox during save
- `aria-busy` attribute for screen readers
- `aria-live="polite"` announcements
- Disabled during request (prevents double-clicks)
- Banner shows "Saving..." message

**Code:**
```tsx
<div className="relative">
  <input
    type="checkbox"
    aria-busy={appliedSaving}
    disabled={isLoggedIn === false || running || appliedSaving}
    checked={checkedState}
    onChange={handleAppliedCheckboxChange}
  />
  {appliedSaving && (
    <div className="absolute -right-6 top-0 h-4 w-4 
                    border-2 border-slate-500 border-t-amber-500 
                    rounded-full animate-spin" 
         aria-hidden="true" 
         title="Saving..." />
  )}
</div>
{appliedSaving && (
  <span className="sr-only" aria-live="polite">
    Saving applied status...
  </span>
)}
```

**Error Handling:**
```tsx
catch (err: any) {
  const status = err?.status || err?.response?.status || 'unknown';
  const bodyPreview = err?.body?.slice(0, 100) || '';
  setAppliedError(
    `Failed to save Applied status (${status}): ${err.message}. ${bodyPreview}`
  );
  // UI keeps previous state - no rollback needed
}
```

---

#### 2. IOH Buttons (History Page)

**Component:** `frontend/components/history/HistoryClient.tsx`

**Features:**
- Individual spinners inside each button
- Row-level AbortController for cancellation
- Concurrent request prevention
- Optimistic locking via `expectedUpdatedAt`

**Loading States:**
```tsx
<button
  aria-busy={stagePending.has(`${appliedKey}:interviewing`)}
  disabled={isPending || stagePending.has(`${appliedKey}:interviewing`)}
  onClick={() => handleSetStage(appliedKey, 'interviewing', !row.is_interviewing)}
>
  {stagePending.has(`${appliedKey}:interviewing`) ? (
    <div className="h-4 w-4 border-2 border-white border-t-transparent 
                    rounded-full animate-spin" 
         aria-hidden="true" />
  ) : (
    'I'
  )}
  <span className="sr-only">
    {row.is_interviewing ? 'Unmark' : 'Mark'} as interviewing
  </span>
</button>
```

**Abort Control:**
```typescript
const abortControllersRef = useRef<Map<string, AbortController>>(new Map());

const handleSetStage = useCallback(async (appliedKey, stage, value) => {
  const pendingKey = `${appliedKey}:${stage}`;
  
  // GUARD 1: Prevent double-submit
  if (stagePending.has(pendingKey)) {
    return; // Already in flight
  }
  
  // GUARD 2: Abort previous request for this row
  const existingController = abortControllersRef.current.get(appliedKey);
  if (existingController) {
    existingController.abort('New request started');
  }
  
  // GUARD 3: Create new AbortController
  const controller = new AbortController();
  abortControllersRef.current.set(appliedKey, controller);
  
  // Add to pending set
  setStagePending(prev => new Set(prev).add(pendingKey));
  
  try {
    await updateStage(appliedKey, stage, value, {
      signal: controller.signal,
      expectedUpdatedAt: row.updated_at
    });
    
    // Success: React Query invalidates automatically
    queryClient.invalidateQueries(['applications']);
  } catch (err: any) {
    if (err.name === 'AbortError') {
      return; // Silently ignore aborted requests
    }
    // Show error
    showError(err);
  } finally {
    // Cleanup
    setStagePending(prev => {
      const next = new Set(prev);
      next.delete(pendingKey);
      return next;
    });
    abortControllersRef.current.delete(appliedKey);
  }
}, [stagePending, queryClient]);
```

**Benefits:**
- **Double-submit prevention:** Checking `stagePending` set before request
- **Stale request cancellation:** AbortController cancels previous request when clicking different stage
- **Clean unmount:** All controllers aborted on component unmount
- **Optimistic locking:** `expectedUpdatedAt` prevents concurrent update conflicts

---

### 3. Concurrency Safety

**Optimistic Locking Pattern:**

```typescript
// Client sends expected timestamp
const response = await apiClient.updateStage({
  appliedKey,
  stage: 'interviewing',
  value: true,
  expectedUpdatedAt: '2025-10-15T10:00:00Z' // Current row timestamp
});
```

**Backend validation:**
```python
@router.patch("/applications/{applied_key}/stage")
async def update_stage(
    applied_key: str,
    stage: str,
    value: bool,
    expected_updated_at: Optional[str] = None,
    db: Session = Depends(get_db)
):
    # Fetch current row
    app = db.query(Application).filter_by(applied_key=applied_key).first()
    
    # Optimistic lock check
    if expected_updated_at and app.updated_at != expected_updated_at:
        raise HTTPException(
            status_code=409,
            detail=f"Concurrent update detected. Expected {expected_updated_at}, "
                   f"but database has {app.updated_at}. Please refresh and retry."
        )
    
    # Apply update
    setattr(app, f'is_{stage}', value)
    app.updated_at = datetime.utcnow()
    db.commit()
    
    return {"success": True, "updated_at": app.updated_at}
```

**User Experience:**
- Tab A updates → succeeds with new timestamp
- Tab B tries to update with stale timestamp → gets 409 Conflict
- Tab B shows error: "Page was updated in another tab. Please refresh."
- User refreshes Tab B → sees latest state from Tab A

---

### 4. Page Coordination (No Cookies)

**Coordination Methods:**

1. **React Query Automatic Invalidation**
   ```typescript
   // After successful mutation
   await queryClient.invalidateQueries(['applications']);
   ```

2. **Visibility Event Listeners**
   ```typescript
   useEffect(() => {
     const handleVisibilityChange = () => {
       if (document.visibilityState === 'visible') {
         queryClient.invalidateQueries(['applications']);
       }
     };
     
     document.addEventListener('visibilitychange', handleVisibilityChange);
     return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
   }, [queryClient]);
   ```

3. **Route Change Detection**
   ```typescript
   useEffect(() => {
     const handleRouteChange = () => {
       queryClient.invalidateQueries(['applications']);
     };
     
     router.events.on('routeChangeComplete', handleRouteChange);
     return () => router.events.off('routeChangeComplete', handleRouteChange);
   }, [router, queryClient]);
   ```

4. **Manual Refresh Triggers**
   ```typescript
   <button onClick={() => queryClient.invalidateQueries(['applications'])}>
     Refresh
   </button>
   ```

**Benefits:**
- No `rt_history_dirty` coordination cookie needed
- Works across tabs via visibility events
- Automatic on navigation
- Simple manual refresh option

---

## Model Settings (Database-Backed)

**Storage:** `user_preferences` table

**Schema:**
```sql
CREATE TABLE user_preferences (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    multi_model_enabled BOOLEAN DEFAULT FALSE,
    fit_models TEXT[] DEFAULT '{}',
    tailor_models TEXT[] DEFAULT '{}',
    judge_models TEXT[] DEFAULT '{}',
    last_single_fit TEXT,
    last_single_tailor TEXT,
    last_single_judge TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    version INTEGER DEFAULT 1
);
```

**API Endpoints:**
- **GET /users/me/model-settings** → Fetch current settings
- **PUT /users/me/model-settings** → Update settings with optimistic locking

**Frontend Hook:**
```typescript
const { settings, save, isLoading, isSaving } = useModelSettings();

// Save partial update
await save({ multi_model_enabled: true });

// Optimistic locking prevents conflicts
await save({ 
  fit_models: ['gpt-4'],
  expected_updated_at: settings.updated_at 
});
```

**Benefits:**
- Settings persist across devices
- Optimistic locking prevents conflicts
- Fast response times (< 50ms)
- No localStorage needed (React Query caches in memory)

---

## Job Submission Pattern

**Flow:**
1. User submits job via POST /tailor/submit
2. API validates input (sanitization, size limits, URL policy)
3. Job enqueued to Redis with unique job_id
4. API returns job_id + job_token immediately (< 200ms)
5. Frontend polls GET /jobs/{id}/status or streams via SSE
6. Worker processes job asynchronously
7. Worker commits results to database
8. Frontend fetches results via GET /jobs/{id}/result

**Input Gating:**
- Resume: max 100KB
- Job description: max 50KB
- URL validation for external links
- Sanitization of HTML/special characters
- Idempotency checks (duplicate job detection)

**Concurrency Control:**
- Max concurrent jobs per user (configurable)
- Redis-based job queue with priority levels
- Graceful degradation under load

---

## Scalability & Performance

### Horizontal Scaling
- API is stateless; scale behind a load balancer (nginx/Render/Cloudflare)
- Redis centralizes job queue and ephemeral metadata (cancel flags, progress)
- Postgres handles transactional state with indexes on hot paths
- Benchmark multi-model ranking leverages parallel ARQ tasks

### Performance Optimizations
- **Explicit loading states** with spinners for immediate visual feedback
- **Server-Sent Events (SSE)** for real-time streaming (no polling overhead)
- **Database query optimization:**
  - Composite indexes on `(user_id, jd_hash)` and `(user_id, created_at)`
  - Hash hints avoid redundant PII decryption
  - Analytics snapshot denormalization for complex aggregations
- **Connection pooling** (SQLAlchemy + pgbouncer compatible)
- **Redis caching** for frequently accessed data
- **Lazy loading and pagination** on history page
- **Frontend code splitting** and tree shaking

### Monitoring & Observability
- Structured logging with correlation IDs
- Database query timing in logs
- Provider API latency tracking
- Job processing duration logging

### Typical Response Times
- Auth endpoints: < 100ms
- Stage toggle mutations: < 50ms (database-only)
- History page load: < 300ms (10 items)
- Job submission: < 200ms (enqueue only)
- Streaming output: First token < 2s

---

## Back-Pressure and Limits

- **SlowAPI rate limits** on auth, step-up, and WebAuthn flows
- **IP / ASN signup-grant gating** ladder (see `[abuse.ip_asn]` in `config/app.toml`) deciding when seeded Budget access requires 2FA or a hard block
- **Concurrency per client_id** for jobs
- **Provider timeouts** and abort registry for streaming
- **Request size limits** (resume 100KB, JD 50KB, candidate 10KB)
- **Job queue backpressure** via Redis maxmemory policy

---

## Multi-Model Benchmarking

### Architecture
- **Container job** (job_flow=benchmark) holds metadata
- **Ranking job** (job_flow=benchmark_rank) executes N candidate models in parallel
- **Optional judge phase** for quality assessment
- `charges.model_count` tracks distinct model inferences for pricing

### Pricing Transparency
- Each candidate model bills independently
- Judge phase adds separate token usage
- Container job has no token cost (model_count=0)
- Detailed breakdown in charges table

### Security
- `/benchmark/start` restricted to admins
- Capability tokens (X-Job-Token) for snapshot saves
- Rate limits mirror core job endpoints

---

## Migration History (October 2025)

### Pessimistic Pattern Migration

**Completed:** October 15, 2025

**What Changed:**
1. ✅ Applied checkbox uses pessimistic pattern (loading states, no optimistic updates)
2. ✅ IOH buttons use pessimistic pattern with abort control
3. ✅ Removed `rt_history_dirty` coordination cookie
4. ✅ Added optimistic locking via `expectedUpdatedAt`
5. ✅ Explicit loading states (spinners, aria-busy, aria-live)
6. ✅ Enhanced error messages with HTTP status codes
7. ✅ AbortController for request cancellation
8. ✅ Double-submit prevention
9. ✅ Multi-tab coordination via visibility events
10. ✅ 23 comprehensive E2E tests

**Files Modified:**
- `frontend/lib/apiClient.ts` - Added AbortSignal + expectedUpdatedAt support
- `frontend/lib/historyOverrides.ts` - Removed all optimistic override logic
- `frontend/hooks/useHistoryData.ts` - Removed optimistic state management
- `frontend/components/pages/ResumeTailorClient.tsx` - Pessimistic Applied checkbox
- `frontend/components/history/HistoryClient.tsx` - Pessimistic IOH buttons with AbortController
- `frontend/components/StageSegments.tsx` - Simplified from 369 to 145 lines

**Test Cleanup:**
- Removed 20 obsolete tests (~1,033 lines)
- Achieved 100% test pass rate (71/71 tests)
- Added 23 E2E tests for pessimistic pattern

**Key Metrics:**
- Code reduction: ~1,500 lines removed (optimistic logic)
- Response times unchanged: < 50ms for stage updates
- User experience improved: explicit feedback, no unexpected reverts
- Debugging simplified: database is always correct

---

## CHANGELOG

- **2025-10-15:** Major consolidation: Added Pessimistic Pattern Migration details, Model Settings architecture, Job Submission Pattern, and complete UI implementation details from 7 migration docs.
- **2025-10-14:** Added Performance & Scalability section with metrics, response times, and multi-model benchmarking details.
- **2025-10-03:** Single Source of Truth architecture with applications table as primary stage source, analytics snapshot state consolidation.
