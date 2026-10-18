# ISUCON14 Practice 2 — Iteration 9: chairPostCoordinate round-trip removal

## Agents Used

Sub-agents were not used because: found by direct code reading (continuing the pattern from iterations 8-9 of avoiding further `alp`/`slp` dispatches on these small hosts after the repeated hang incidents), a small and self-contained fix verifiable by a straightforward read of the handler.

## Hypothesis

`POST /api/chair/coordinate` is one of the highest-volume routes (6700+ calls/run). It inserted a `chair_locations` row relying on the column's `DEFAULT CURRENT_TIMESTAMP(6)`, then immediately re-`SELECT`ed that exact row by primary key solely to read back `CreatedAt` for the JSON response. Generating the timestamp in Go and inserting it explicitly removes the need for that second query.

## Evidence

Code read (`chair_handlers.go` `chairPostCoordinate`): confirmed the insert-then-select-by-PK pattern, and that `location.CreatedAt` was the only field read from the second query's result.

## Change

Branch `iter9-coordinate-noselect`, commit `e654b14`. Added a `time` import; generate `createdAt := time.Now()` and pass it explicitly to the `INSERT` (`created_at` column); removed the follow-up `SELECT`; the response now uses `createdAt.UnixMilli()` directly. No other logic in the handler changed (the ride/ride_statuses status-transition code later in the function is independent of this).

## Verification

- `go build` on `s1` before deploy.
- `POST /api/initialize` -> `200`.
- 3 benchmark runs (logs truncated between each): 8233, 8107 (`CODE=26 x1`), 8015 (`CODE=26 x1`) — all `pass=true`. `CODE=26` is the same pre-existing, unrelated `ownerGetChairs` lag warning seen since the baseline.

## Benchmark Result

Mean **~8118** across 3 runs, clearly above iteration 8's mean (~7501) with a tight spread (8015-8233) — the highest scores recorded in this project so far (run1's 8233 is the single-run peak).

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel. Collection target commit `e654b14`.

## Commit

`e654b14` on branch `iter9-coordinate-noselect`, merged to `main` via PR.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/9 (merged, branch deleted).

## Next Candidate

One iteration remains in the user's requested 10-iteration loop. Candidates: check for the same insert-then-reselect pattern elsewhere (e.g. any other `INSERT` immediately followed by a by-PK `SELECT` of the same row); or a final resource-balance check across s1/s2/s3 now that the score has grown roughly 11x from baseline (744 -> ~8118 mean) to decide whether anything else stands out.
