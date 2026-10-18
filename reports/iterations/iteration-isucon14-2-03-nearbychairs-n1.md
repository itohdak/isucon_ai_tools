# ISUCON14 Practice 2 — Iteration 3: appGetNearbyChairs double N+1

## Agents Used

Sub-agents were not used because: the candidate was already flagged by iteration 1's App Understanding Agent, and Codex performed the analysis/EXPLAIN-equivalent verification directly (running both the old and new query shapes against live data before deploying) to keep iteration pace up and avoid repeating the resource incidents from iterations 1-2.

## Hypothesis

`appGetNearbyChairs` loops every chair and, per chair, ran one query per ride (`getLatestRideStatus`) to determine if the chair is busy, then one more query for its latest location — O(chairs × (rides_per_chair + 1)) round trips. It had the second-worst avg per-call latency of any route in iteration 2's profiling (1.39s avg, 118 calls, sum 164.2s).

## Evidence

- Code read (`app_handlers.go:829`): confirmed the double-N+1 shape described above.
- Verified on live data before deploying: a window-function query (`ROW_NUMBER() OVER (PARTITION BY ride_id ORDER BY created_at DESC)`) picking each ride's latest status produces an identical result to the original per-ride `getLatestRideStatus` query, for a spot-checked chair with an active ride.

## Change

Branch `iter3-nearbychairs-n1`, commit `981164e`. Replaced the per-chair loop with two queries total:
1. Active chairs with no ride whose latest status is not `COMPLETED` (the "available" set), via one `NOT IN` + window-function subquery.
2. Latest location for every chair in one query (same window-function pattern over `chair_locations`), joined to the available-chair list via a Go map.

No API/behavior change. `errors`/`sql` imports still used elsewhere in the file (no unused-import issue from removing the `sql.ErrNoRows` check at this call site).

## Verification

- `go build` on `s1` before deploy.
- `POST /api/initialize` -> `200`.
- 3 benchmark runs (logs truncated between each): 2087, 2310, 2071 (mean ~2156), all `pass=true`.
- One run (`run3`) logged `CODE=26 x2` ("owner chairs list total_distance reflection delayed") — confirmed via raw bench log grep this is the *same* warning type seen once in the very first baseline run (iteration 0 report), unrelated to this change (it concerns `ownerGetChairs`'s total_distance computation, not `appGetNearbyChairs`), not a regression introduced here.

## Benchmark Result

Mean ~2156 across 3 runs, within this environment's observed noise band (1984-3296 across iterations 1-3 at various commits on this small, ~24-active-chair dataset). No clear win or regression by score; change retained because it is a verified-correct reduction in query count (O(chairs × rides) -> O(1) round trips) that should matter more as the chair/ride count grows.

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel. Collection target commit `981164e`.

## Commit

`981164e` on branch `iter3-nearbychairs-n1`, merged to `main` via PR.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/3 (merged, branch deleted).

## Next Candidate

`GET /api/owner/chairs` (`ownerGetChairs`) has by far the worst avg per-call latency measured so far (1.73-2.6s avg over ~84-111 calls, a `chairs` + window-function `total_distance` subquery) despite low call volume — a strong candidate since a single heavy query, unlike the small-dataset N+1s in iterations 2-3, should show a clear win independent of dataset size. Investigate next.
