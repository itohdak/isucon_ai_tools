# ISUCON14 Practice 2 — Iteration 10 (final): appPostRides N+1

## Agents Used

Sub-agents were not used because: found by direct, systematic code reading (grepping for `INSERT INTO` and the surrounding handler logic across all Go files, continuing the approach from iterations 8-9 to avoid further `alp`/`slp` dispatches on these small hosts after the repeated hang incidents), a small and self-contained fix verifiable against live data before deploying.

## Hypothesis

`POST /api/app/rides` fetches all of the requesting user's rides, then runs one `getLatestRideStatus` query per ride just to count how many are not yet `COMPLETED` (the "do you already have an active ride" guard before creating a new one). This is the exact same 1+N shape fixed for `appGetNearbyChairs`'s busy-chair check in iteration 3, here keyed on `user_id` instead of `chair_id`, and grows per call as a user accumulates more completed rides over a long run.

## Evidence

Code read (`app_handlers.go` `appPostRides`): confirmed the `SELECT * FROM rides WHERE user_id = ?` followed by a `getLatestRideStatus` call inside a `for _, ride := range rides` loop, used only to increment `continuingRideCount`.

## Change

Branch `iter10-postrides-n1`, commit `c3f2333`. Replaced the fetch-all-then-loop pattern with a single query: `ROW_NUMBER() OVER (PARTITION BY ride_id ORDER BY created_at DESC)` to pick each ride's latest status row, then `COUNT(*)` where that status is not `COMPLETED`. No other logic changed.

## Verification

- `go build` on `s1` before deploy.
- Spot-checked on live data before deploying: for a user with only completed rides (old-style query and new window-function query both returned `0`) and for a user with an active ride (both returned `1`).
- `POST /api/initialize` -> `200`.
- 3 benchmark runs (logs truncated between each): 7651, 8485, 8635 (`CODE=26 x1`, the same pre-existing unrelated warning) — all `pass=true`.

## Benchmark Result

Mean **~8257** across 3 runs, slightly above iteration 9's mean (~8118); run3's 8635 is the highest single-run score recorded across this project's 10 iterations.

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel. Collection target commit `c3f2333`.

## Commit

`c3f2333` on branch `iter10-postrides-n1`, merged to `main` via PR.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/10 (merged, branch deleted).

## Next Candidate (post-session)

This was the 10th and final iteration of the loop requested on 2026-10-18. Remaining candidates for a future session, not yet investigated:
- `internalGetMatching`'s `ORDER BY RAND()` chair-selection query — touches matching-selection semantics (AGENTS.md ask-first item), so any change needs explicit human approval even if scoped to query-shape only.
- Re-run a full Resource Monitor Agent pass now that the score has grown ~11x from baseline (744 -> ~8257 mean) to see whether `s1` or `s2` is newly CPU-bound, and whether the auth-middleware's per-request `SELECT * FROM {users,owners,chairs} WHERE access_token = ?` lookups are worth an in-process cache (all three tables are small and access_token is immutable once issued).
- Avoid `alp`/`slp` full-log-file analysis directly on these 2 vCPU hosts going forward — it caused 4 hang incidents across this session (`s1` x2, `s2` x2), each requiring a manual AWS-console reboot since the operator IAM user cannot reboot or inspect console output itself.
