# ISUCON14 Practice 2 — Iteration 4: ownerGetChairs total_distance scope

## Agents Used

Sub-agents were not used because: the candidate (flagged by iteration 1's App Understanding Agent and confirmed by the worst avg-latency numbers across iterations 1-3) was investigated and verified directly by Codex — reading the query, spot-checking old vs. new query output on live data, same approach as iterations 2-3.

## Hypothesis

`GET /api/owner/chairs` had the worst avg per-call latency of any route measured in this project so far (1.7-2.6s avg across iterations 1-3). Its `total_distance` subquery computed a `LAG()`-based distance sum over **every** `chair_locations` row in the entire system on every call, applying the `owner_id` filter only in the outer query — i.e. it window-functioned the whole table regardless of which owner (with typically only 4-8 chairs) was asking.

## Evidence

- Code read (`owner_handlers.go:193`): the inner `chair_locations` subquery had no `WHERE` clause at all; `owner_id = ?` only appeared in the outermost `WHERE`.
- Spot-checked on live data: ran both the original query and a version with `WHERE chair_id IN (SELECT id FROM chairs WHERE owner_id = ?)` pushed into the inner subquery, for the same owner — identical `total_distance` output per chair.

## Change

Branch `iter4-ownerchairs-distance`, commit `b16ea49`. Added `WHERE chair_id IN (SELECT id FROM chairs WHERE owner_id = ?)` to the inner `chair_locations` scan inside the `total_distance` subquery (bound with `owner.ID` a second time). No change to the query's output shape or the outer logic.

## Verification

- `go build` on `s1` before deploy.
- `POST /api/initialize` -> `200`.
- `alp` after run1: `/api/owner/chairs` avg dropped from the previous 1.7-2.6s to **0.084s** (166 calls, sum 14.0s) — roughly a 20-30x per-call speedup.
- 3 benchmark runs (logs truncated between each): 2986, 2891, 3485, all `pass=true`, zero errors.

## Benchmark Result

Mean **~3121** across 3 runs — clearly above every prior iteration's range (1984-2879 across iterations 1-3). Unlike iterations 2-3 (inconclusive within noise), this is a clear, unambiguous win, both at the query level (avg latency) and at the overall score level.

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel. Collection target commit `b16ea49`.

## Commit

`b16ea49` on branch `iter4-ownerchairs-distance`, merged to `main` via PR.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/4 (merged, branch deleted).

## Next Candidate

Re-profile from this new, faster baseline (alp/slp on a fresh run) to find the next bottleneck now that `/api/owner/chairs` is no longer a factor — `/api/chair/notification` (924.5s sum, 17055 calls) and `/api/app/notification` (777.1s sum, 7815 calls) are still the two largest total-time routes by far and warrant another look now that overall throughput has increased.
