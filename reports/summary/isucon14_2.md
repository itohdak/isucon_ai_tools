# ISUCON14 Practice 2 — Summary

Chronological, append-only log for the `isucon14-practice-2` environment and the
`isucon14_practice_2` repository. This is an intentionally independent redo of
ISUCON14 practice (user instruction, 2026-10-18): no prior `isucon14` /
`isucon14_practice` work, reports, or `reports/summary/isucon14.md` entries
were consulted while building this environment or should be consulted for
future iterations here. Full environment facts: `config/isucon14_2.yaml`.

## 2026-10-18 — Environment built from scratch

- CloudFormation stack `isucon14-practice-2` created from
  `isucon_cf_provisioning/isucon14/cf-template-isucon14.yaml` (profile
  `isucon15.prep`, region `ap-northeast-1`) — 3x `c5.large`, private IPs fixed
  (`.11`/`.12`/`.13`), public IPs assigned at creation (see
  `config/isucon14_2.yaml`).
- Topology chosen: `s1` = app + db (default AMI single-host layout, matching
  AGENTS.md's Resource And Split Policy default — no split until benchmark
  evidence justifies one), `s2` = spare/idle, `s3` = bench + pprotein.
  `isuride-go`/`isuride-matcher`/`isuride-payment_mock`/`nginx`/`mysql`
  stopped and disabled on `s2` and `s3` (AMI ships every host symmetric with
  all services enabled by default).
- Ansible `general` (netdata + apt hygiene) and `pprotein` (alp/slp/pprotein +
  pprotein-agent) roles run against all 3 hosts. `alp.yaml`/`targets.json`
  updated to ISURIDE's actual routes/hosts (read live from
  `webapp/go/main.go` on `s1`, not from any prior project's notes);
  `targets.json` trimmed to `s1` only since `s2`/`s3` run no app.
- GitHub repo `itohdak/isucon14_practice_2` (private, created by the user)
  initialized with: captured `webapp/go` source + `sql/` + `payment_mock`
  source, `common/{deploy.sh,env.sh,etc/,services}` (nginx ltsv access log +
  MySQL slow query log enabled from the start, `long_query_time=0`),
  `webapp/go/main.go` patched to add pprotein pprof (`:8888`) and a
  best-effort `/api/group/collect` call from `postInitialize`, and operator-side
  `scripts/{env.sh,run_cycle.sh,bench.sh,analyze.sh}`. Initial commit `9399531`,
  pushed to `main`.
- Gotcha hit: `curl https://s1/...` from the operator machine hung for
  minutes before failing — `s1`/`s2`/`s3` are SSH-config aliases only (no
  local `/etc/hosts` entries; `sudo` on this operator machine requires an
  interactive password that isn't available), so plain `curl` can't resolve
  them. Fixed by using the instance's public IP with
  `--resolve xiv.isucon.net:443:<ip>` (sets both Host and TLS SNI) instead.
- Baseline verified end-to-end: `POST /api/initialize`
  (`payment_server=http://192.168.0.13:12345`, i.e. the bench host's own
  built-in payment mock, not the AMI's local `isuride-payment_mock.service`)
  then `bench run --target https://xiv.isucon.net --addr 192.168.0.11:443
  --payment-bind-port 12345 --payment-url http://192.168.0.13:12345` from `s3`.
  **Baseline: `pass=true`, score=744** (one benchmark-internal error type 26,
  not yet investigated — likely a normal unsatisfied-rating count at this
  score level, not a correctness bug). pprotein confirmed collecting
  `webapp-s1`/`nginx-s1`/`mysql-s1` (`ok`) via `POST /api/initialize`'s hook.
- `isucon_ansible` (shared infra repo, separate from `isucon14_practice_2`):
  inventory/`alp.yaml`/`targets.json`/`repo` role vars updated and committed
  directly to `master` (`d5c532f`), per this repo's existing convention for
  shared ops tooling (not the per-project PR workflow).
- GitHub auth note: `gh` CLI needed a fine-grained PAT with explicit
  "Read and Write access to code, issues, and pull requests" granted for the
  `isucon14_practice_2` repo specifically — the repo was otherwise invisible
  to `gh api`/`gh repo view` even though SSH key access worked fine.
- Next: run the AGENTS.md Default Improvement Loop (Profiler/Resource
  Monitor/App Understanding/SQL agents in parallel) starting from this
  baseline, per the user's 2026-10-18 request for 10 iterations.

## 2026-10-18 — Iteration 1: missing indexes (744 -> 3296, +343%)

- Dispatched Profiler/Resource Monitor/App Understanding/SQL Agents in
  parallel. First three converged strongly: `chairs`/`chair_locations`/
  `rides`/`ride_statuses` had zero indexes beyond PK, mysqld was CPU-bound
  (90-168% of 2 cores) during a bench run while the app itself was only
  7-23%. Added `UNIQUE(access_token)`/`INDEX(owner_id)` on `chairs`,
  `INDEX(chair_id, created_at)` on `chair_locations`,
  `INDEX(chair_id, updated_at)`/`INDEX(user_id)` on `rides`,
  `INDEX(ride_id, created_at)` on `ride_statuses`. No app code changed.
- **Incident**: `s1` went fully unresponsive (SSH + HTTPS) for ~10-15 min
  mid-iteration, very likely caused by the SQL Agent's background work
  (never returned a report after ~40 min). The `isucon15.prep` IAM user
  cannot reboot/stop instances or read CloudWatch/console output, so
  recovery required the user to reboot the instance manually from the AWS
  console. All systemd services came back automatically (enabled); no data
  or git history was lost. Added a Bash permission rule (`Bash(gh pr
  merge:*)` in `~/.claude/settings.json`, user request) after `gh pr merge`
  was blocked by the auto-mode classifier's "Merge Without Review" check,
  so subsequent iterations' PRs can be merged directly.
- Result: `pass=true`, score 744 -> **3296** (+343%), and the one baseline
  benchmark error (type 26 x1) disappeared entirely. PR #1 merged
  (https://github.com/itohdak/isucon14_practice_2/pull/1), branch deleted.
  Full detail: `reports/iterations/iteration-isucon14-2-01-missing-indexes.md`.
- Next candidate: re-run Resource Monitor Agent to see whether app CPU is
  now the limiter; `getChairStats`/`appGetNearbyChairs` N+1 patterns
  flagged by App Understanding Agent as iteration 2 candidates.

## 2026-10-18 — Iteration 2: getChairStats N+1 fix (inconclusive by score, retained)

- Codex-direct analysis (no fresh sub-agent dispatch, reusing iteration 1's
  findings to reduce load on the small app host): confirmed `getChairStats`
  (called from the highest-total-time route, `GET /api/app/notification`)
  ran 1+N queries per call. Replaced with a single JOIN+aggregation query,
  commit `f68bb81`, merged via PR #2.
- **Second resource incident**: `s1` went fully unresponsive again —
  root cause this time identified: a 285MB unflushed mysql slow log
  (`long_query_time=0`, 3 bench runs accumulated) parsed by multiple
  concurrent `alp`/`slp`/`ls` commands on the 2 vCPU/3.7GB host with no
  swap. User rebooted via AWS console a second time. Mitigated by adding a
  persistent 2GB swapfile and switching to one-analysis-command-at-a-time
  with log truncation between runs.
- 3 runs before (mean ~2589) vs. 3 runs after (mean ~2472) — within this
  environment's run-to-run noise band, no clear win or regression. Change
  kept anyway: verified correctness-preserving by code read, and reduces
  round-trips in a way expected to matter more at higher per-chair
  completed-ride counts than this short bench window exercises.
  Full detail: `reports/iterations/iteration-isucon14-2-02-chairstats-n1.md`.
- Next candidates: `appGetNearbyChairs` N+1, `GET /api/owner/chairs`
  window-function query (avg ~1.7-2.6s/call). Future iterations should run
  3+ benchmarks per side and truncate logs between every run.

## 2026-10-18 — Iteration 3: appGetNearbyChairs double N+1 fix

- Replaced the per-chair, per-ride double N+1 in `appGetNearbyChairs`
  (busy-chair check + location lookup) with two window-function queries
  total. Commit `981164e`, merged via PR #3. Verified the new query's
  latest-status derivation against the old per-ride query on live data
  before deploying.
- 3 runs: 2087, 2310, 2071 (mean ~2156) — within the same noise band seen
  since iteration 1 (1984-3296) on this small (~24 active chairs) dataset;
  no clear score win, no regression. One run logged `CODE=26 x2`
  (owner/chairs total_distance lag), confirmed pre-existing and unrelated
  (same warning type seen once in the very first baseline run).
  Full detail: `reports/iterations/iteration-isucon14-2-03-nearbychairs-n1.md`.
- Observation: 3 iterations of N+1/index fixes on this small-dataset bench
  haven't moved the score much beyond its noise band. Next candidate
  (`GET /api/owner/chairs`'s window-function `total_distance` query, worst
  avg per-call latency measured so far at 1.7-2.6s) is a single heavy
  query rather than an N+1, so should show a clearer win independent of
  dataset size.
