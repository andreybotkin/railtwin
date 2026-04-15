# Thailand Railway Digital Twin Development Plan

## 1) Current Technical Review

### What has been fixed already (startup-critical)
- Fixed incorrect generic types in `useTrainSchedule` and `useStationSchedule` that caused `tsc --noEmit` to fail and blocked frontend build.
- Refactored the WebSocket client to remove listener leaks, added unsubscribe callbacks, and disabled auto-reconnect after intentional `disconnect()`.

### Architecture risks identified
- The frontend has tight coupling between UI logic and API transport contracts, increasing regression risk.
- A singleton WebSocket client without explicit subscription lifecycle management can accumulate listeners over time.
- The frontend lint configuration is currently invalid in this environment (`@typescript-eslint/no-unused-vars` rule is configured but plugin support is not available).

## 2) Target Architecture (iterative)

### Backend
1. Introduce a consistent Unit-of-Work transaction strategy:
   - Commit only in write use-cases.
   - Avoid implicit commits for read-only paths.
2. Split application orchestration from domain logic:
   - API layer handles coordination only.
   - Train simulation logic is isolated and testable as a dedicated domain module.
3. Define stable DTO contracts between repository outputs and API schemas to reduce ORM leakage.

### Frontend
1. Separate transport models from view models.
2. Strengthen real-time infrastructure:
   - centralized WebSocket lifecycle,
   - explicit `subscribe/unsubscribe` API,
   - fallback policy: WebSocket -> polling.
3. Add standardized API/WS error handling and error boundaries.

## 3) Phased Execution Plan

### Phase A (1–2 weeks): Stabilization
- Eliminate all TypeScript errors and keep `type-check` green in CI.
- Fix ESLint setup (`@typescript-eslint/eslint-plugin` + `.eslintrc` alignment).
- Add simulation/frontend startup smoke tests to CI.

### Phase B (2–4 weeks): Reliability and Observability
- Add metrics (latency, error rate, reconnect rate).
- Add structured tracing for REST and WebSocket paths.
- Add tests for reconnect and heartbeat behavior.

### Phase C (4–8 weeks): Scalability and Data Quality
- Move heavy simulation workloads to a dedicated worker or stream pipeline.
- Add Redis-backed caching for frequently requested aggregates.
- Add data-quality validation for route geometry and schedules.

## 4) Quality KPIs
- Frontend build/type-check success in main: 100%.
- API 5xx error rate: < 0.5%.
- Mean response time for `/api/v1/trains/positions`: < 300ms.
- WebSocket update delivery success: > 99.5%.
