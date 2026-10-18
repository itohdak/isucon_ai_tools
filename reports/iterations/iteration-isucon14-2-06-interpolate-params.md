# ISUCON14 Practice 2 — Iteration 6: MySQL InterpolateParams

## Agents Used

Sub-agents were not used because: after re-profiling (alp) showed per-call latency on the two highest-volume routes was already low (<0.12s avg) and mysqld was still the larger CPU consumer relative to the app (netdata, ~109% vs ~51% of 2 cores at peak) despite no remaining obvious missing index or N+1, Codex inspected the MySQL driver configuration directly (`main.go`'s `setup()`) as the next most likely lever, rather than dispatching a fresh SQL Agent pass over an already-indexed, low-per-query-cost workload.

## Hypothesis

With iterations 1-5 clearing every missing index and the obvious N+1 patterns, the remaining mysqld load on the two highest-volume routes is now dominated by round-trip *count*, not per-query execution time. `main.go`'s `mysql.NewConfig()` never set `InterpolateParams`, which defaults to `false` in go-sql-driver/mysql — every parameterized query (`?` placeholders, used throughout this codebase) is therefore a separate prepare + execute + close round trip (3 network round trips) instead of one.

## Evidence

- Re-profiled with `alp` after iteration 5: `/api/chair/notification` (14620 calls, avg 0.074s) and `/api/app/notification` (8521 calls, avg 0.117s) still dominate total time by sum, but per-call latency is already low — pointing at round-trip overhead rather than slow queries.
- netdata at peak during that run: `mysqld` ~109% vs. `isuride` (app) ~51% of a 2-core host — mysqld still ahead, consistent with the driver issuing 3x the necessary round trips per query.
- Code read (`main.go` `setup()`): `dbConfig.InterpolateParams` was never set (default `false`).

## Change

Branch `iter6-interpolate-params`, commit `9ba3583`. Added `dbConfig.InterpolateParams = true` to the DSN config. The driver's interpolation is parameterized/escaped client-side (not raw string concatenation), so this does not introduce an injection risk. No other code changed.

## Verification

- `go build` on `s1` before deploy.
- `POST /api/initialize` -> `200`.
- 3 benchmark runs (logs truncated between each): 4314 (errors `CODE=26 x2`, the same pre-existing unrelated warning), 4054 (no errors), 2962 (no errors) — all `pass=true`.

## Benchmark Result

Mean **~3777** across 3 runs. The top two runs (4314, 4054) are the highest scores recorded in this project so far; the third (2962) falls within this environment's established noise band. Net clear improvement over iteration 5's mean (~3353).

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel. Collection target commit `9ba3583`.

## Commit

`9ba3583` on branch `iter6-interpolate-params`, merged to `main` via PR.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/6 (merged, branch deleted).

## Next Candidate

Re-check the mysqld-vs-app CPU split now that round-trips are reduced — if app CPU has become the larger share, future iterations should look at Go-side costs (JSON encoding, ULID generation, connection pool sizing) rather than more SQL work. Also worth a resource check on whether `s2` (still idle) should be considered for a DB split now that overall throughput has roughly quintupled since baseline (744 -> ~3777 mean), per AGENTS.md's Resource And Split Policy (evidence-based only).
