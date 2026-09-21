# ISUCON14 Improvement Approach

Last updated: 2026-09-21

This document captures the application-aware strategy for improving ISURIDE. Update it whenever the scoring interpretation, matching strategy, notification strategy, or benchmark evidence changes.

## What The Score Rewards

The score is the sum of:

- Distance from matched chair position to pickup position multiplied by `0.1`
- Distance from pickup position to destination position
- Completed ride count multiplied by `5`

This means pure request throughput is not the final objective. The application must complete more rides and keep chairs moving through valuable rides. Matching quality matters, but the destination leg dominates the matched-to-pickup leg by a factor of 10.

## Behavioral Constraints

- A user can request another ride only after their current ride is `COMPLETED`.
- A chair can accept another ride only after its assigned ride is `COMPLETED`.
- Notifications must preserve state transition order and deliver every transition at least once.
- `POST /api/chair/coordinate` must be reflected in nearby-chair coordinates within 3 seconds.
- `GET /api/owner/chairs` total distance has a 3 second freshness allowance.
- Once a ride is matched, user and chair notifications have a 30 second allowance.
- Notification endpoints may be JSON polling or SSE. Current implementation uses JSON polling with `retry_after_ms = 30`.
- `GET /api/internal/matching` and `isuride-matcher.service` are internal and may be changed freely.
- Payment must complete within 5 seconds after the load phase ends.

## Current Evidence

Latest measured run:

- Commit: `129b90d collect pprotein on initialize`
- Score: `3736`
- Result: `pass=true`
- Warning: `CODE=26` twice, related to owner chair total distance freshness
- Report: `reports/iterations/iteration-20260921-074341.md`

Top API total latency:

- `GET /api/chair/notification`
- `GET /api/app/notification`
- `POST /api/chair/coordinate`
- `GET /api/app/nearby-chairs`

Top SQL total query time:

- latest ride status lookup by ride id
- latest ride lookup by chair id
- chair lookup by access token
- owner chair distance aggregation

## Improvement Priorities

### 1. Reduce Polling Cost Without Breaking Notification Semantics

The notification endpoints dominate total API time because they are called constantly. Optimizing them improves server capacity, but correctness is strict:

- Every status transition must be delivered at least once.
- Delivery order must match transition order.
- The same ride cannot skip expected states.

Candidate changes:

- Return larger `retry_after_ms` only when there is no pending event, while keeping state changes under the 3 second expectation.
- Avoid repeated joins/lookups in notification handlers by denormalizing small pieces needed for responses.
- Maintain per-ride latest status and pending notification pointers, so notification handlers do not repeatedly scan `ride_statuses`.
- Consider SSE only after simpler polling optimizations, because SSE changes connection behavior and needs careful timeout handling.

### 2. Improve Matching For Score, Not Only Latency

The current matcher still chooses an active chair randomly and then checks whether it is empty. The score formula rewards completed rides and distance traveled, so matching should:

- assign quickly enough that rides do not wait in `MATCHING`
- prefer chairs that can reach pickup soon, accounting for chair model speed
- keep high-speed chairs busy on longer or farther rides
- avoid assigning chairs that still have unfinished rides

Candidate changes:

- Replace `ORDER BY RAND()` with deterministic candidate selection.
- Precompute each active chair's latest location.
- Join `chair_models` to include speed.
- Score candidates by estimated pickup time: `distance(current, pickup) / speed`.
- Add a second-order preference for higher total scoring potential when candidate pickup time is similar.
- Reduce matcher interval if the application can handle it, or move matching into ride creation / coordinate updates to reduce wait time.

### 3. Store Hot Derived State

The benchmark pattern is event-driven, but the current schema forces many reads from append-only history tables. Keep history for correctness, but add derived tables or columns for hot reads.

Candidate derived state:

- `rides.latest_status`
- latest ride per chair
- latest location per chair
- active unfinished ride per user
- active unfinished ride per chair
- pending app/chair notification status id
- owner chair total distance cache

Rules:

- Keep derived state updated in the same transaction as the source event.
- Preserve `/initialize` so derived tables are dropped/recreated or reset.
- Treat owner distance carefully because current runs still show `CODE=26` freshness warnings.

### 4. Owner Distance: Fix Correctness Before Aggressive Caching

`GET /api/owner/chairs` is not the largest API by total latency, but it is correctness-sensitive. Latest benchmark produced `CODE=26` warnings. Avoid changing semantics here until the freshness model is explicit.

Safer path:

- On `POST /api/chair/coordinate`, calculate the distance delta from the previous location for that chair.
- Store cumulative total distance and last updated time per chair.
- Update this in the same transaction as inserting `chair_locations`.
- Use the cached value in `GET /api/owner/chairs`.

This should reduce the window-function aggregation cost and improve freshness, but it must be benchmarked carefully because the warning tolerance is 3 seconds.

### 5. Increase Completed Rides

Because completed ride count adds `5` points and unlocks the next ride for both user and chair, end-to-end ride turnover is crucial.

Candidate changes:

- Make matching faster and smarter.
- Make notifications faster enough that clients advance states quickly.
- Make coordinate writes cheap enough that chairs are not blocked waiting for responses.
- Ensure payment retry uses idempotency and does not stall completion.

## Measurement Policy

For every benchmark:

- pprotein collection starts from `POST /api/initialize`.
- Use pprotein saved httplog with `alp` sorted by `sum`.
- Use pprotein saved slowlog with `slp` sorted by `sum-query-time`.
- When API attribution is needed for SQL, parse the raw pprotein slowlog comments directly; `slp` removes comments from normalized output.

## Next Concrete Experiments

1. Build a slowlog attribution helper that outputs `api/fn x normalized query x count x total_time`.
2. Add a latest-location / chair-distance cache table and use it for owner chairs, then verify `CODE=26` disappears or does not increase.
3. Add active ride derived state to eliminate repeated latest-status scans in notification paths.
4. Replace random matching with candidate selection using latest chair location and model speed.
5. Tune notification retry interval after the above, watching completed rides and warning count, not only latency.

## Guardrails

- Do not optimize by dropping required status notifications.
- Do not hide or ignore payment failures.
- Do not let `/initialize` skip derived state reset.
- Do not rely on external compute resources for scoring behavior.
- Do not keep a final result if warnings/errors make the run unstable.
