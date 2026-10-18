# ISUCON14 Practice 2 — Iteration 2: getChairStats N+1

## Agents Used

Sub-agents were not used because: iteration 1's App Understanding Agent had already flagged this exact N+1 pattern as a candidate, and iteration 1's Profiler Agent methodology (alp/slp) was reused directly by Codex rather than re-dispatching agents, to move faster and reduce load on the small (2 vCPU / 3.7 GB) app host after the resource incidents described below. Resource Monitor-style netdata checks were also done directly by Codex.

## Hypothesis

With the schema fully indexed (iteration 1), `GET /api/app/notification` remained the single highest total-time route (alp `sum`). It calls `getChairStats` on every poll once a ride has an assigned chair, and that function ran 1 query for the chair's rides + 1 more `ride_statuses` query per ride (N+1), growing unboundedly as a chair accumulates completed rides. Replacing it with a single aggregation query should reduce round-trips without changing output.

## Evidence

- `alp` (clean-log run at `83ae447`, score 2486): `GET /api/app/notification` 6317 calls, sum **1362.7s** (highest of any route); `GET /api/chair/notification` 10262 calls, sum 1180.5s; `GET /api/owner/chairs` 111 calls, avg 1.73s; `GET /api/app/nearby-chairs` 118 calls, avg 1.39s (both still N+1-shaped per iteration 1's App Understanding Agent notes, left for a later iteration).
- netdata during the bench window: mysqld still dominant (90-130% of 2 cores) vs. app (20-40%) even after iteration 1's indexes — i.e. query *count*, not just per-query cost, is still the limiting factor on this host.
- Code read (`app_handlers.go:763`): `getChairStats` confirmed N+1 as described in the hypothesis.

## Change

Branch `iter2-chairstats-n1`, commit `f68bb81`. Replaced `getChairStats`'s per-ride loop (1 + N queries) with one query joining `rides`+`ride_statuses` and using `MAX(status = 'X')` aggregation per ride, preserving the exact original gating logic (ARRIVED+CARRYING+COMPLETED all required) and the evaluation-average computation. No API/behavior change, no schema change.

## Incident (environment, not code)

Mid-iteration, `s1` became fully unresponsive a second time (SSH banner-exchange timeouts, netdata child stopped streaming) — root-caused this time: the mysql slow log had grown to **285MB** (accumulated across 3 unflushed benchmark runs from iteration 1 at `long_query_time=0`), and Codex ran `alp`+`slp`+a plain `ls`/`wc` concurrently against it on the 2 vCPU / 3.7 GB host with no swap configured. The user rebooted `s1` via the AWS console a second time (operator IAM still cannot reboot/read console output/CloudWatch). After recovery, two mitigations were applied directly to the host: **(1)** added a 2GB swapfile (`/swapfile`, persisted in `/etc/fstab`) so memory pressure degrades instead of making the host unresponsive; **(2)** truncated both logs and switched to running one analysis command at a time, never overlapping. These are host-level mitigations only (not yet captured in a git-tracked playbook) — worth formalizing in `docs/skills/resource-monitor-agent.md` or a general ops note if this environment is reused.

## Verification

- `go build` succeeded on `s1` before deploy.
- `POST /api/initialize` -> `200`.
- 3 benchmark runs at `f68bb81` (logs truncated between each): 2879, 2404, 2132 (mean ~2472), all `pass=true`, no errors.
- Compared against 3 runs at the pre-change commit `83ae447` (same code as iteration 1, clean logs): 2486, 1984, 3296 (mean ~2589).

## Benchmark Result

Inconclusive by mean (~2472 vs ~2589) — within this environment's observed run-to-run noise band (roughly ±30%, seen both within and across these two sets). No regression: all 6 runs across both commits passed with zero errors. The change is retained because it is a correctness-preserving reduction in SQL round-trips (verified by code read, not just benchmark score), and is expected to matter more as per-chair completed-ride counts grow (longer runs / real contest duration) than in this environment's short bench window.

## pprotein Artifacts

Dashboard via `ssh pprotein` tunnel. Collection target commit `f68bb81`.

## Commit

`f68bb81` on branch `iter2-chairstats-n1`, merged to `main` via PR.

## PR

https://github.com/itohdak/isucon14_practice_2/pull/2 (merged, branch deleted).

## Next Candidate

- `appGetNearbyChairs` (per-chair N+1 over rides + a separate latest-location query) and `GET /api/owner/chairs` (window-function query previously measured at avg 2.55s/call) remain the two highest per-call-latency routes — both flagged by iteration 1's App Understanding Agent, neither touched yet.
- Given the benchmark noise observed this iteration, future iterations should budget 3+ runs per side before concluding a change helped or regressed, and truncate logs between every run.
