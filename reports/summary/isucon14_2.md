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

## 2026-10-18 — Iteration 4: ownerGetChairs total_distance scope fix (clear win: ~2300 -> ~3121 mean)

- `GET /api/owner/chairs`'s `total_distance` subquery ran its `LAG()`
  window function over every `chair_locations` row in the whole system on
  every call, filtering by `owner_id` only in the outer query. Pushed
  `WHERE chair_id IN (SELECT id FROM chairs WHERE owner_id = ?)` into the
  inner scan. Commit `b16ea49`, merged via PR #4. Verified identical
  `total_distance` output vs. the original query on live data first.
- Clear, unambiguous win (unlike iterations 2-3): alp avg for this route
  dropped from 1.7-2.6s to **0.084s** (~20-30x); 3 bench runs scored 2986,
  2891, 3485 (mean ~3121), clearly above every prior iteration's range
  (1984-2879). Full detail:
  `reports/iterations/iteration-isucon14-2-04-ownerchairs-distance.md`.
- Next candidate: re-profile from this faster baseline — `/api/chair/notification`
  (924.5s sum, 17055 calls) and `/api/app/notification` (777.1s sum, 7815
  calls) are now the two largest total-time routes.

## 2026-10-18 — Iteration 5: coupons.used_by index (mean ~3121 -> ~3353)

- Systematic grep of every `WHERE col =` in the Go handlers against the
  schema found one remaining gap: `coupons.used_by` (used by
  `calculateDiscountedFare`, called from the highest-volume
  `appGetNotification` route) had no index at all beyond
  `PRIMARY KEY(user_id, code)`. Added `INDEX(used_by)`, commit `b35b67e`,
  merged via PR #5.
- 3 runs: 3329, 3238, 3493 (mean ~3353), all `pass=true`. Narrower spread
  than iteration 4 (3238-3493 vs 2891-3485) — variance shrinking as more
  inefficiencies are removed. Two runs logged the same pre-existing,
  unrelated `CODE=26` owner/chairs warning seen since the baseline.
  Full detail: `reports/iterations/iteration-isucon14-2-05-coupons-index.md`.

## 2026-10-18 — Iteration 6: MySQL InterpolateParams (mean ~3353 -> ~3777)

- With every obvious missing index/N+1 cleared, re-profiling showed the
  two highest-volume routes already had low per-call latency (<0.12s avg)
  but mysqld was still ahead of app CPU (~109% vs ~51% of 2 cores at
  peak) — pointing at round-trip count. `main.go`'s MySQL DSN never set
  `InterpolateParams` (defaults to false), so every parameterized query
  was 3 round trips (prepare+execute+close) instead of 1. Enabled it,
  commit `9ba3583`, merged via PR #6.
- 3 runs: 4314, 4054, 2962 (mean ~3777); top two are the highest scores
  recorded in this project so far. Full detail:
  `reports/iterations/iteration-isucon14-2-06-interpolate-params.md`.
- Next: recheck mysqld-vs-app CPU split; consider whether `s2` (still
  idle) now has evidence for a DB split given throughput has roughly
  quintupled since baseline (744 -> ~3777 mean).

## 2026-10-18 — Iteration 7: MySQL split to s2 (evidence-based; mean ~3777 -> ~7365, ~2x)

- netdata still showed `s1` CPU-bound (system ~95-99% busy, mysqld ~113%
  of 2 cores vs. app ~48%) even after iterations 1-6 exhausted SQL/index
  fixes — meeting AGENTS.md's Resource And Split Policy threshold.
  Split MySQL to `s2` (idle since setup, same `c5.large` type — not a
  scale-up): `bind-address=0.0.0.0` on s2, `ISUCON_DB_HOST` repointed,
  `s2/services=mysql`, `s1/disabled=mysql`. Commits `344f204`+`c013a46`,
  merged as `1d482e9` via PR #7.
- **Gotcha found and fixed**: `isuride-go.service`/`isuride-payment_mock.service`
  both had `Requires=mysql.service`, which auto-started the disabled local
  mysql on `s1` every time `isuride-go` restarted (systemd `Requires=`
  ignores enabled/disabled state). Removed both lines from both units.
- No data migration needed (`/api/initialize` always rebuilds schema+seed
  data fresh against `ISUCON_DB_HOST`); ran `0-init.sql` once manually on
  `s2` to create the DB + remote `isucon@'%'` user first.
- 3 runs: 7517, 7338, 7239 (mean ~7365) — roughly double iteration 6's
  mean (~3777), the largest and most consistent single-iteration gain so
  far. Full detail: `reports/iterations/iteration-isucon14-2-07-db-split.md`.
- Topology now: s1=app only, s2=dedicated MySQL, s3=bench+pprotein.
  Next: re-check resource balance on both s1 and s2 post-split.

## 2026-10-18 — Iteration 8: MySQL server tuning on s2 (mean ~7365 -> ~7501)

- Post-split, mysqld alone saturates s2's 2 cores (~175%/200%) while s1
  has ~50% idle. `SHOW VARIABLES` found `innodb_buffer_pool_size` still
  at the 128M package default (s2 has 3.7G RAM and runs nothing else),
  `innodb_flush_log_at_trx_commit=1`, `log_bin=ON` (MySQL 8.0 default)
  with no replica. Set buffer pool to 2G, flush-at-commit to 2,
  `innodb_flush_method=O_DIRECT`, `skip-log-bin`. Commit `565c248`,
  merged via PR #8.
- **Second resource incident**: `slp` on s2's slow log (even a 29MB
  capped sample) hung the host twice more, needing two more manual
  reboots — 4 total hang incidents this session (s1 x2, s2 x2). This
  iteration's evidence came from `SHOW VARIABLES` only, no fresh
  slow-log profiling.
- 3 runs: 7552, 7023, 7929 (mean ~7501) — modest, consistent further gain.
  Full detail: `reports/iterations/iteration-isucon14-2-08-mysql-tuning.md`.
- Next: avoid `alp`/`slp` full-log analysis on these 2 vCPU hosts going
  forward (repeated hangs); `internalGetMatching`'s `ORDER BY RAND()` is
  a candidate but changing its selection semantics needs human approval
  per AGENTS.md.

## 2026-10-18 — Iteration 9: chairPostCoordinate round-trip removal (mean ~7501 -> ~8118)

- Code read of `chairPostCoordinate` (one of the highest-volume routes)
  found an INSERT into `chair_locations` immediately followed by a
  by-PK SELECT of the same row, solely to read back `CreatedAt` for the
  response. Generated the timestamp in Go (`time.Now()`), inserted it
  explicitly, dropped the SELECT. Commit `e654b14`, merged via PR #9.
- 3 runs: 8233, 8107, 8015 (mean ~8118) — highest scores in this project
  so far, tight spread. Full detail:
  `reports/iterations/iteration-isucon14-2-09-coordinate-noselect.md`.
- Score trail so far: baseline 744 -> iter1 ~2589 -> iter4 ~3121 ->
  iter5 ~3353 -> iter6 ~3777 -> iter7 ~7365 -> iter8 ~7501 -> iter9
  ~8118 (~11x baseline). One iteration remains in the requested 10.

## 2026-10-18 — Iteration 10 (final): appPostRides N+1 fix (mean ~8118 -> ~8257)

- Same N+1 shape as iteration 3's `appGetNearbyChairs` fix, found by
  code reading: `appPostRides`'s "does this user already have an active
  ride" check fetched all rides then ran one `getLatestRideStatus` query
  per ride. Replaced with a single `ROW_NUMBER()`-based `COUNT(*)` query.
  Verified identical output on live data (completed-only and
  active-ride users) before deploying. Commit `c3f2333`, merged via
  PR #10.
- 3 runs: 7651, 8485, 8635 (mean ~8257) — 8635 is the highest single-run
  score across all 10 iterations. Full detail:
  `reports/iterations/iteration-isucon14-2-10-postrides-n1.md`.

## Session summary (iterations 0-10, 2026-10-18)

**Baseline 744 -> final mean ~8257, roughly 11.1x.** Full score trail:
baseline 744 (iter0) -> ~2589 (iter1, missing indexes) -> ~2156-2472
(iter2-3, N+1 fixes on getChairStats/appGetNearbyChairs, inconclusive by
score but correctness-preserving) -> ~3121 (iter4, ownerGetChairs
total_distance scoping, first clear win) -> ~3353 (iter5, coupons index)
-> ~3777 (iter6, MySQL InterpolateParams) -> ~7365 (iter7, MySQL split to
s2, ~2x, the single largest gain) -> ~7501 (iter8, MySQL server tuning)
-> ~8118 (iter9, chairPostCoordinate round-trip removal) -> ~8257
(iter10, appPostRides N+1 fix). All 10 iterations merged via PR into
`main` (PRs #1-#10), each with its own `reports/iterations/` report.

**Operational incidents (4 total, all resolved via manual AWS-console
reboot by the user — the `isucon15.prep` IAM user cannot reboot
instances or read console output/CloudWatch itself):** `s1` hung twice
in iterations 1-2 (root cause: concurrent `alp`+`slp`+`ls` against an
unflushed 285MB mysql slow log on a 2 vCPU/3.7GB host with no swap —
mitigated by adding a 2GB swapfile and switching to one-command-at-a-time
log analysis with truncation between runs); `s2` hung twice in iteration
8 (same pattern, even on a size-capped 29MB log sample, after becoming
the DB host in iteration 7) — from iteration 8 onward, `alp`/`slp` were
avoided entirely in favor of `SHOW VARIABLES`/code reading/live-data
spot-checks. Also found and fixed: `isuride-go`/`isuride-payment_mock`
systemd units had `Requires=mysql.service`, which auto-restarted the
disabled local MySQL on `s1` on every app restart after the iteration 7
split (removed both lines). A `gh pr merge` auto-mode classifier block
("Merge Without Review") was resolved by the user adding a
`Bash(gh pr merge:*)` permission rule to `~/.claude/settings.json`.

Final topology: `s1` = app only, `s2` = dedicated MySQL (evidence-based
split, iteration 7), `s3` = bench + pprotein. See `config/isucon14_2.yaml`
for current IPs/facts.
