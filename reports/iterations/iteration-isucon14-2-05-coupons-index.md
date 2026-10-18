# ISUCON14 Practice 2 — Iteration 5: coupons.used_by index

## Agents Used

Sub-agents were not used because: this was found by a direct, systematic grep of every `WHERE col =` pattern in the Go handlers against the current (post-iteration-1) schema, a quick mechanical check rather than a full profiling pass — same low-risk-index-addition category as iteration 1, pre-authorized by AGENTS.md as routine work.

## Hypothesis

`calculateDiscountedFare` (called from `appGetNotification`, one of the two highest-volume routes) runs `SELECT * FROM coupons WHERE used_by = ?` on every call once a ride exists. `coupons`' only key is `PRIMARY KEY(user_id, code)` — `used_by` has no index, so this is a full table scan on every poll.

## Evidence

- Systematic grep of `WHERE [a-z_.]+ ?=` across all Go handler SQL against the schema as of commit `b16ea49` (post iterations 1-4): every other filtered column was already covered by an existing PK/unique/index (`user_id`, `id`, `chair_id`, `ride_id`, `owner_id`, `access_token`, `invitation_code`, `code` as PK suffix, `chair_register_token`) except `coupons.used_by`.
- Code read confirmed the query site (`app_handlers.go` `calculateDiscountedFare`, the `ride != nil` branch).

## Change

Branch `iter5-coupons-index`, commit `b35b67e`. Added `INDEX (used_by)` to `coupons` in `webapp/sql/1-schema.sql`. Pure schema addition, no application code change.

## Verification

- `POST /api/initialize` -> `200`; `SHOW INDEX FROM coupons` confirmed the new index present and populated (cardinality 333).
- 3 benchmark runs (logs truncated between each): 3329 (errors `CODE=26 x2`), 3238 (`CODE=26 x1`), 3493 (no errors) — all `pass=true`. The `CODE=26` warnings are the same pre-existing, unrelated `ownerGetChairs` total_distance-lag warning seen intermittently since the very first baseline run (iteration 0), not a regression from this change.

## Benchmark Result

Mean **~3353** across 3 runs, and a narrower spread (3238-3493) than iteration 4's (2891-3485) — a further, more consistent improvement on top of iteration 4's clear win.

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel. Collection target commit `b35b67e`.

## Commit

`b35b67e` on branch `iter5-coupons-index`, merged to `main` via PR.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/5 (merged, branch deleted).

## Next Candidate

Re-profile (alp/slp) from this now-faster baseline to pick iteration 6's target — likely still the sheer call volume on `/api/chair/notification`/`/api/app/notification`, or a deeper look at `internalGetMatching`'s matching-cadence query cost now that the obvious missing-index/N+1 issues are cleared.
