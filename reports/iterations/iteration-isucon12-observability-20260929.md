# ISUCON12 qualify — observability experiments (2026-09-29)

Not a scoring iteration (no tuning change kept on `main`). This records the environment recreation after the 2026-09-24 teardown, and the real-hardware verification of two experimental observability branches the user asked to try, per their two questions: (1) can we get a per-request trace of where time goes inside a handler, beyond what alp/slp aggregate profiling shows, and (2) can we recover which sequence of APIs a given bench-simulated actor calls, to infer the bench's scenario/state machine.

Sub-agents were not used: this was direct environment recreation + two small, well-scoped code experiments the user explicitly asked to be tried on branches, not an optimization-hypothesis loop.

## Environment recreation

Stack `isucon12-qualify` had been deleted 2026-09-24 for cost savings (see `reports/summary/isucon12.md`). Recreated from the already-tracked 4-host template (`isucon_cf_provisioning/isucon12_qualify/cf-template-isucon12-qualify-4host.yaml`), same private IPs, new public IPs (recorded in `config/isucon12.yaml` and `isucon_ansible/inventory/hosts`). Steps, in order:

1. `aws cloudformation create-stack` + `wait stack-create-complete` (~4 min).
2. Disabled `unattended-upgrades`/`apt-daily*` timers on s1-s3 (s4 already disables them via the template's `UserData`, per the earlier isucon13 lesson).
3. `ansible-playbook playbooks/deploy_general.yaml` (Netdata) and `deploy_pprotein.yaml` — both clean, no failures.
4. `ansible-playbook playbooks/setup_repo.yaml` (git checkout of `isucon12_qualify_practice_2` on s1-s3, HTTPS clone). **Gotcha found**: the `repo` role's `clone repo` task (`git init; remote add; checkout -b main; fetch --all; reset --hard origin/main`) never sets upstream tracking, so a later plain `git pull` (as used by `common/deploy.sh`/`scripts/run_cycle.sh`) fails with "no tracking information." Fixed live with `git branch --set-upstream-to=origin/main main` on each host; not yet fixed in the ansible role itself (low-risk follow-up: add that step to `roles/repo/tasks/setup.yaml`).
5. Go 1.23.4 was **not** present on the fresh AMI (the `go` ansible role installs a different, apt/PPA-based Go that `deploy.sh` doesn't look for). Installed manually at `/home/isucon/local/golang` on s1/s2/s3 (symmetric) via the official tarball, matching how it was originally set up per `reports/summary/isucon12.md`'s first setup note. This isn't automated anywhere — worth turning into an ansible task if this environment gets recreated again.
6. `bench`, `blackauth`, TLS certs (`*.t.isucon.local`/`*.t.isucon.dev` SAN) are all baked into the AMI itself (dated at AMI build time), not part of the git repo (explicitly gitignored) or ansible — nothing to redo there.
7. Deployed `main` (`04b5f6f`) to s1 (app) and s2 (nginx+MySQL) via `bash common/deploy.sh` (mirrors `scripts/run_cycle.sh`'s deploy loop). `POST /initialize` verified end-to-end, then a full benchmark from s4 confirmed the recreated environment matches the pre-teardown state: **pass=true, score=236455** (previously recorded range: 233844-240397).

## Experiment 1 — per-request span tracing (`experiment/request-tracing`, commit `5e33967`)

Deployed to s1 only (app-only change).

- **Tracing off (default)**: pass=true, score=232925 — within normal run-to-run noise of the 236455 baseline. Confirms the no-op code path costs nothing measurable.
- **Tracing on** (live-only env edit, `ISUCON_REQUEST_TRACE_FILE=/home/isucon/request-trace.log` appended to `/home/isucon/env.sh`, not committed): pass=true, score=214285 — **an ~8% drop** from the per-request JSON-line write (single mutex-protected file, one write per request). This is a real, non-trivial cost and confirms the design intent: this is a manual-investigation tool to run for a short traced session, not something to leave on during a scored benchmark.
- Output inspected: 175,782 trace lines from one bench run. Aggregated locally (fetch + a small ad hoc Python pass, not committed — see below for why): the top-by-total-time-contribution instrumented handlers were `GET /api/organizer/billing` and `GET /api/admin/tenants/billing`, both dominated by the `billingReportByCompetition:all` span (avg 9.27-5.61 ms of their ~7-10 ms total) — exactly the kind of "which part of the transaction is slow" breakdown that alp/slp's per-route/per-query aggregates don't show directly. One surprise: `competitionRankingHandler`'s top span was `insertVisitHistory` at 5.85 ms avg, despite only firing on a cache-miss subset of calls (`visitSeen`) — worth a closer look if this path is ever a tuning target again.
- **Verdict: works as intended.** Recommend keeping this pattern (opt-in via env var, same shape as the existing `sqltrace.go`) for future targeted investigations, but do not enable it during an actual scored/contest benchmark run given the measured overhead.

## Experiment 2 — actor-tagged responses for API-transition mining (`experiment/actor-transition-trace`, commit `612c5e9`)

Deployed to both s1 (sets the `X-Isucon-Actor` header) and s2 (nginx LTSV gains the `actor` field).

- pass=true, score=230438 — in line with baseline, confirming two things the commit message had flagged as unverified: (1) the bench does **not** reject responses carrying the extra header, and (2) the overhead of setting one more header per response and logging one more LTSV field is negligible.
- Fetched s2's access log (188,153 lines, 9,668 distinct actors) and ran `scripts/actor_transitions.py` against it for real. It correctly recovers the bench's per-role scenario shape from nothing but existing log data:
  - Organizer loop: `GET /api/organizer/players -> POST /api/organizer/competitions/add -> POST /api/organizer/competition/:id/score -> POST /api/organizer/competition/:id/finish -> GET /api/organizer/billing -> GET /api/organizer/players` (a repeating cycle, 1000+ occurrences of each edge).
  - Player loop: `GET /api/player/competitions -> GET /api/player/competition/:id/ranking <-> GET /api/player/player/:id` (tens of thousands of occurrences — this is the bulk of bench traffic, confirming `Player`/`PlayerHeavyTenant` are the dominant scenario tags, consistent with `ScenarioCount` in the bench's own output).
  - Admin loop: `POST /api/admin/tenants/add -> GET /api/admin/tenants/billing` repeating.
- **Verdict: works as intended**, and cheaply — it's a genuinely new capability (log-derived scenario reconstruction) built entirely from data the app already computes, at negligible cost.

## Cleanup

Both branches reverted on all hosts (`git checkout main` on s1/s2/s3, redeployed on s1/s2). Final check: pass=true, score=230396. No code from either experiment is on `main`; both remain as pushed branches (`experiment/request-tracing`, `experiment/actor-transition-trace`) for future reference or reuse. Ad hoc local analysis scripts used for the trace-file aggregation above were not committed (only `scripts/actor_transitions.py`, which ships with the second branch, was); if per-request trace analysis becomes a recurring need, that aggregation is worth turning into a small committed script the same way.

## Next candidates

- Fix the ansible `repo` role's missing upstream-tracking step (small, low-risk).
- Automate the Go toolchain install (currently manual/undocumented in ansible) so a future recreation doesn't need to rediscover it.
- If per-request tracing proves useful again, consider sampling (e.g. trace 1-in-N requests) to get visibility at a fraction of the ~8% cost, rather than all-or-nothing.
- Both experiments are ready to merge into `main` if the user wants them as standing tooling; currently left as separate branches per the user's request to "try them on branches."
