# ISUCON14 Practice 2 — Iteration 1: Missing Indexes

## Agents Used

| Agent | Used | Output |
| --- | --- | --- |
| Profiler Agent | yes | slp: ride_statuses lookups (5 shapes) sum ~383s; alp: `/api/chair/notification` (sum 1087s), `/api/app/notification` (sum 590s), `/api/chair/coordinate` (sum 493s) dominate total route time. |
| Resource Monitor Agent | yes | s1 CPU-bound (97-100% of 2 cores); mysqld 90-168%, app only 7-23% — bottleneck is mysqld, not app. |
| App Understanding Agent | yes | Confirmed matching is random-sample (not nearest-chair); flagged missing indexes as the lowest-risk/highest-confidence candidate; flagged `getChairStats`/`appGetNearbyChairs` N+1 patterns for a later iteration. |
| SQL Agent | no (timed out) | Dispatched but its background work ran far longer than expected (~40 min) and likely caused s1 to become fully unresponsive (SSH banner-exchange timeouts, port 443 also down) — see Verification note below. Proceeded without its report since the other three agents + direct schema inspection already gave strong, convergent evidence. |

## Hypothesis

`chairs`, `chair_locations`, `rides`, and `ride_statuses` define no index beyond `PRIMARY KEY(id)` (confirmed by direct read of `webapp/sql/1-schema.sql`, independently corroborated by the App Understanding Agent's code read and the Profiler Agent's slp data). Every hot lookup by `ride_id`/`chair_id`/`user_id`/`owner_id`/`access_token` is a full table scan, which plausibly explains the Resource Monitor Agent's finding that mysqld (not the app) is the CPU bottleneck. Per AGENTS.md's Resource And Split Policy ("if the dominant issue is inefficient query/API behavior, optimize the application or SQL first"), fix the missing indexes before considering any instance split.

## Evidence

- `SHOW INDEX` / schema read on `s1`: `chairs`, `chair_locations`, `rides`, `ride_statuses` had only `PRIMARY KEY(id)`; `users`/`owners` already had `UNIQUE(access_token)`.
- Profiler Agent (slp, baseline run, commit `9399531`): `ride_statuses` queries (5 shapes) sum to ~383s; `chairs WHERE access_token=?` (8808 calls) sum 31s; `rides WHERE chair_id=?` queries sum ~70s; one `chairs` owner/window-function query (84 calls, avg 2.55s) sum 214.5s.
- Resource Monitor Agent (netdata, during a live bench run): s1 `system.cpu` 97-100% busy; per-process `mysqld` 90-168% of a 2-core host vs. `isuride` (app) 7-23%.
- App Understanding Agent: code read confirms `getLatestRideStatus(ride_id)` is called from nearly every handler; `getChairStats` N+1-queries `ride_statuses` per ride.

## Change

Branch `iter1-missing-indexes`, commit `a0bc47e`, added to `webapp/sql/1-schema.sql`:

- `chairs`: `UNIQUE(access_token)`, `INDEX(owner_id)`
- `chair_locations`: `INDEX(chair_id, created_at)`
- `rides`: `INDEX(chair_id, updated_at)`, `INDEX(user_id)`
- `ride_statuses`: `INDEX(ride_id, created_at)`

No application code changed — pure schema/index addition, applied via the next `POST /api/initialize` (which re-runs `1-schema.sql`). Pre-authorized as routine, low-risk work per AGENTS.md ("Adding low-risk indexes ... when evidence is strong").

## Verification

**Incident during this iteration**: after pushing the branch, `s1` became fully unresponsive for roughly 10-15 minutes — SSH banner-exchange timeouts (even from `s3` over the private network) and no response on port 443, while TCP port 22 itself accepted connections and the AWS security group was unchanged. The operator IAM user (`isucon_user`) lacks `ec2:RebootInstances`/`ec2:GetConsoleOutput`/CloudWatch permissions, so the agent could not self-diagnose or recover; the user rebooted the instance manually via the AWS console. Likely cause: the SQL Agent's background work (still running after ~40 minutes per its own tool-use log) plausibly ran an unbounded query against a full-scanned table. Not confirmed, since the agent never returned its final report. After reboot: all systemd services (enabled) came back automatically, git was still on the `iter1-missing-indexes` branch at the old pre-deploy state; `common/deploy.sh` and a fresh `POST /api/initialize` were re-run cleanly.

- `SHOW INDEX FROM ride_statuses` / `chairs` after `/api/initialize`: confirms both new indexes (`ride_id`+`created_at`; `access_token` unique, `owner_id`) are present and populated (non-zero cardinality).
- Benchmark: `pass=true`, 0 errors (vs. 1 error, type 26, at baseline).

## Benchmark Result

| | Baseline (`9399531`) | This change (`a0bc47e`) |
| --- | --- | --- |
| pass | true | true |
| score | 744 | **3296** (+343%) |
| errors | type 26 ×1 | none |

Run: 2026-10-18, `s3` -> `s1` (192.168.0.11:443).

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel, `http://127.0.0.1:9000/#/group/`. Collection target commit `a0bc47e`; `webapp-s1`/`nginx-s1`/`mysql-s1` all `ok`.

## Commit

`a0bc47e` on branch `iter1-missing-indexes`, merged to `main` via PR.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/1 (merged, branch deleted).

## Next Candidate

- `getChairStats` (called from the high-frequency `appGetNotification` poll) and `appGetNearbyChairs` both N+1-query per-ride/per-chair (flagged by the App Understanding Agent) — now that the underlying per-call cost is index-backed instead of full-scan, re-measure whether these are still worth batching/caching.
- Re-run the Resource Monitor Agent after this change lands to see whether mysqld CPU dropped proportionally, and whether app CPU is now the limiting factor (which would redirect iteration 2 toward application-level caching instead of more SQL work).
- Treat any future SQL Agent dispatch against this environment with an explicit row-count/timeout guard in its instructions, given this iteration's unresponsiveness incident.
