# ISUCON AI Tools Milestones

This file is the working roadmap for turning the current mock MCP/Skill skeleton into usable ISUCON operations tooling.

When a milestone is completed, update:

- Status
- Completed date
- Notes
- Any follow-up tasks

## Current Status

- **Environment recreated on 2026-09-23 after a cost-savings teardown, with roles swapped for clarity**: `s1`+`s2` are now the load-targeted hosts (app, db) and `s3` is the dedicated bench/pprotein host (previously `s1`+`s3` load-targeted / `s2` bench). New public IPs: `s1`=`52.69.150.66`, `s2`=`54.95.127.250`, `s3`=`35.73.191.95` (private IPs unchanged: `.11`/`.12`/`.13`). Verified fully working end-to-end post-recreation: `pass=true`, score `12676`, matching the pre-teardown range. See `reports/iterations/` for the recreation iteration and `docs/environment-teardown-restore.md` for what teardown/restore involved. **If any IP below looks stale, `config/isucon14.yaml` is the source of truth.**
- Last updated: 2026-09-23
- Overall phase: Operational iteration
- Next milestone: Continue evidence-driven tuning
- Startup checklist: `docs/isucon-startup-checklist.md`
- Agent architecture: `docs/agent-architecture.md`
- ISUCON14 improvement approach: `docs/isucon14-improvement-approach.md`
- Resource split policy: `docs/resource-scaling-policy.md`
- MySQL operations tips: `docs/mysql-operations-tips.md`
- pprotein: deployed on `s2`, collecting from `s1` via pprotein-agent; dashboard is available through SSH tunnel to `localhost:9000`.
- pprotein collection policy: the app starts pprotein collection when bench calls `POST /api/initialize`, so human-run and Codex-run benchmarks share the same observability path.
- Analysis policy: rank API and SQL bottlenecks primarily by total latency (`sum` / `sum-query-time`) so high-frequency medium-latency paths are not missed.
- Instance split policy: collect resource metrics during bench and split web/app/db only when CPU, memory, disk IO, or network evidence shows a resource bottleneck.
- Latest app optimization commit: `38b02eb Revert "increase matcher batch size from 3 to 5"` (content-equivalent to `000d3fc`, i.e. `maxMatchesPerCall = 3`).
- Latest verified benchmark: `pass=true`, score `13191`, errors `map[26:1]`.
- Latest iteration report: `reports/iterations/iteration-20260923-160824.md`.
- **Denormalized chair freeness into `chairs.is_free`** (commit `e506027`), replacing the matcher's correlated `NOT EXISTS` chair-freeness scan. App Understanding Agent reviewed race/ordering risk first (Medium risk, implementation-detail risk not algorithmic — the critical detail being that `chairGetNotification`'s `is_free=TRUE` write must be gated on `status=="COMPLETED"` specifically, not fire on every notification). 3/3 clean benchmark runs post-implementation. Query-level win confirmed via `slp`: matching query avg latency dropped ~51ms→~14.8ms (3.5x), max ~186ms→~88ms. **However, `s2`'s aggregate CPU remains fully saturated (mysqld ~181.7% avg, idle ~0.1-0.5%)** — same pattern as the earlier nearby-chairs fix: a real per-query win that wasn't the dominant aggregate cost. SQL-side query optimization has hit diminishing returns; the top-8-by-Sum(Query_time) items were already indexed, and both major per-call outliers (nearby-chairs, matching) are now fixed. Remaining lever: reduce query *count* (notification polling architecture) — **not** a bigger instance for `s2`; ISUCON regulations prohibit scaling up any instance, full stop (see `AGENTS.md`'s Resource And Split Policy). If query-count reduction also hits its limit, this may simply be the contest's real resource ceiling.
- **Methodology gap found and corrected**: the user asked whether the SQL Agent's "top findings" were really the top items by `Sum(Query_time)`. Re-ran `slp --sort sum-query-time --reverse` for a full, authoritative ranking and found the agent's own "finding #3" (matcher chair-selection query) was actually **9th** by summed time (~6.6s), included via an unstated "high per-call/max-latency" heuristic rather than the stated total-time ranking — and that same heuristic, applied inconsistently, is why nearby-chairs (max latency 429ms, higher than the matching query's 280ms at the time) was missed. Lesson: verify a query-analysis agent's narrative summary against the actual full ranked table for the specific metric requested, rather than trusting prose synthesis alone.
- **User-identified fix: denormalized latest chair location** (commits `7b6a13f`, `1099e7b`). The user spotted `appGetNearbyChairs`'s "latest location per chair" JOIN as suspiciously slow (avg 132ms/max 429ms in the slow log) — a query the SQL Agent's cumulative-CPU-cost ranking hadn't flagged. `EXPLAIN ANALYZE` showed the plan itself was efficient but fully recomputed the latest-location-per-chair derived table on every call; `internalGetMatching` does the identical recomputation every matching tick. Added `chairs.latest_latitude`/`latest_longitude`, maintained transactionally in `chairPostCoordinate` (same pattern as `total_distance`), and read directly by both endpoints instead of rejoining through the derived table each time. **Lesson learned**: adding the new columns directly to `1-schema.sql`'s `CREATE TABLE` broke `3-initial-data.sql.gz`'s positional `INSERT` (column-count mismatch) — fixed by moving them to a post-seed `ALTER TABLE` in `init.sh`, matching the existing `total_distance` precedent; any future new column must follow this same pattern. **Result**: nearby-chairs query latency dropped ~5x (132ms→27ms avg, 429ms→76ms max), matching query also improved somewhat, but `s3`'s overall CPU remains fully saturated (idle ~0.1-1%, mysqld ~180% avg, unchanged) — this fix removed a real but non-dominant cost; the matcher's correlated `NOT EXISTS` chair-freeness check (SQL Agent's finding #3) remains the true ceiling.
- **Fixed pprotein slowlog collection**: after the MySQL split, `pprotein-agent` (serving the slow log for pprotein to collect) was still only deployed to the `webapp` group, so it kept reading `s1`'s now-stale local slow log file even though `targets.json` had already been pointed at `s3`. Extended `isucon_ansible`'s `deploy_pprotein.yaml`/`roles/pprotein` to also cover the `db` group and deployed it to `s3`; confirmed a fresh, correctly-sized slowlog artifact was collected on the next benchmark run. (Separate repo/commit: `isucon_ansible` `1e6dead`.)
- **Netdata is now set up on `s3`**: added to `isucon_ansible/inventory/hosts` under `[db]` and ran `deploy_general.yaml --limit s3`; confirmed streaming to the parent on `s2` alongside `s1`. (Separate repo/commit: `isucon_ansible` `eb87d1e`.)
- The 20x matcher batch attempt was rejected for causing a catastrophic overload; retrying with a much smaller `maxMatchesPerCall = 3` succeeded cleanly across 5 runs (avg ≈12278, ~2.2x the pre-fix post-split average).
- **Confirmed ceiling at current infra**: tried bumping `maxMatchesPerCall` 3 → 5 next, using the new `s3` Netdata data to check headroom directly. It failed the same way as the 20x attempt (`pass=false`, "too many errors"). Netdata for the exact failed window showed `s3` CPU idle collapsed to ~1% with load1 peaking at **18.0 on 2 vCPUs** (~9x overloaded), while `s1` still had 41-95% idle — `s3`'s MySQL CPU, not the app, is the confirmed bottleneck at this batch size. Reverted to `maxMatchesPerCall = 3`.
- **Applied SQL Agent's top DB tuning recommendations** (commit `ec8b776`): disabled binlog (`skip-log-bin`, since MySQL 8.0 enables it by default) and relaxed `innodb_flush_log_at_trx_commit` to 2, plus a covering index for the hottest query (`ride_statuses_ride_id_created_at_status_idx`). Confirmed the commit-fsync fix worked precisely as intended (avg COMMIT time dropped ~18x, 1.25ms → 0.07ms). **However, `s3`'s CPU is still fully saturated at peak (idle ~0.1-0.9%) during a benchmark run** — removing the fsync bottleneck simply let other CPU-bound work (most likely the matcher's chair-selection query, whose cost scales with batch size and active-chair count per the SQL Agent's finding #3) fill the freed capacity. Scores post-tuning (10162, 10352, 9856) were not clearly better than the pre-tuning `maxMatchesPerCall=3` baseline. Kept the tuning (both changes are safe and correct on their own terms), but `maxMatchesPerCall` remains at 3 — raising it further needed the matcher's chair-selection query itself optimized (an app-maintained "chair is free" flag — since implemented, see the later `chairs.is_free` entry above). Note: an earlier version of this entry incorrectly suggested upsizing the DB host as a fallback lever — ISUCON regulations prohibit scaling up any instance outright (see `AGENTS.md`'s Resource And Split Policy); that was never actually a valid option.
- **Rejected experiment**: tried fixing the `CODE=32` matching-latency issue by looping the matcher up to 20 matches per tick (commit `de2f88f`). This caused a catastrophic overload (`pass=false`, score 10802, 11+ distinct error categories firing at once, "too many errors" abort) — the fixed one-match-per-tick rate was apparently also implicitly throttling total concurrent active-ride load system-wide, not just matching latency. Reverted immediately (`ebd6765`), then fixed properly with the smaller 3x step above.
- **Infrastructure change**: split MySQL onto a new dedicated host `s3` (`192.168.0.13`, public `18.176.6.65`), after the Resource Monitor Agent + `pidstat` evidence showed `s1` was CPU-bound with `mysqld` alone averaging 97.7% CPU (saturating a full core) versus 43% for the app. Provisioned via a CloudFormation update to the existing `isucon14` stack (it already had unused `Instance3`/`InstanceIP3` resources defined but never deployed — this was a deliberate 2-host practice setup, not drift). User approved both the general split direction and the specific CloudFormation plan (via change-set preview) before execution, and separately granted the IAM permissions needed.
- Post-split resource confirmation: `s1`'s `isuride` process CPU rose to ~73.6% avg (up from ~43%, now that it isn't competing with mysqld) with mysqld gone; `s3`'s `mysqld` averages ~141% CPU on its own 2 vCPUs, confirming MySQL genuinely needed more than the ~1 core it could get while sharing `s1`.
- **Known issue introduced by removing the CPU bottleneck**: 1 of 6 post-split benchmark runs failed with `CODE=32` ("ride not matched for a long time"), which never occurred pre-split this session. Working theory: `isuride-matcher.service`'s fixed 0.5s/one-match-per-tick cadence was implicitly paced by `s1`'s prior CPU contention; with that removed, the app can outpace the matcher during bursts. Not yet fixed — flagged as the next candidate, requires human approval since it's a matching-strategy change.
- Discovered and worked around (without modifying it) a `common/deploy.sh` bug: its per-server override logic checks `$HOSTNAME`, but that resolves to the machine's real hostname, not `s1`/`s2`/`s3` — so overrides silently never applied before. Workaround: invoke as `sudo -u isucon env HOSTNAME=s1 bash ./deploy.sh`. Documented in `AGENTS.md`. `deploy.sh` also unconditionally restarts local `mysql`, so it must be stopped again on `s1` after every future deploy there until `deploy.sh` itself is fixed (needs separate approval).
- Previous app-level finding (still valid, not superseded): retried the `FOR SHARE` removal on `users` in `chairGetNotification` (commit `150e043`) after the CODE=15 root cause was independently fixed. No correctness issues, but it scored consistently ~120 points lower under an A/B check and was rejected again (`35c1e70`, performance reason, not correctness). Do not retry a third time without a new theory.
- Root cause found for the earlier `CODE=15` failure: `internalGetMatching` only checked that a chair's previous ride had a `COMPLETED` status row *inserted*, not that the chair had actually been *sent* that status (`chair_sent_at`). Because `chairGetNotification` always reports on the chair's most-recently-`updated_at` ride, reassigning a chair before it polled its COMPLETED notification permanently stranded that notification. This was a deterministic pre-existing bug, not a concurrency race in the matcher (confirmed sequential, single-process via `ps aux` and httplog timing) — any future throughput improvement could have made it more likely to surface. Fixed by requiring `chair_sent_at IS NOT NULL` on the COMPLETED row before a chair is considered free. This changes matching strategy, so it was proposed to and approved by the user before implementing, per the AGENTS.md guardrail.
- Benchmark noise note: on 2026-09-22 evening, repeated runs of the same commit ranged roughly `5017`-`5324`, and re-measuring an earlier commit (`47398b8`) scored `5233` versus its own earlier-recorded `5336`. Treat single-run deltas under ~300 points as inconclusive; prefer a same-conditions A/B redeploy before accept/reject when a change looks like a regression.
- Rejected experiment: removing the `FOR SHARE` lock on the `users` read in `chairGetNotification` (commit `65d9b68`). Score looked flat, but the 3rd of 3 benchmark runs failed outright with `CODE=15` (a chair received a new ride notification before its current ride's completion notification) — a real notification/matching invariant violation, not just noise. Reverted (`085609b`); re-measuring the pre-change commit twice showed no such failure. Working theory: the lock removal sped up notification polling enough to raise the odds of hitting a pre-existing race elsewhere (likely matching/ride-assignment), rather than the lock itself being load-bearing. Do not retry this specific change without first investigating that race. See `reports/iterations/iteration-20260922-211313.md`.

## Milestone 1: Define Environment And Execution Settings

- Status: Completed
- Completed date: 2026-09-21
- Goal: Make it clear which environment each MCP should operate against.

Tasks:

- [x] Define target hosts.
- [x] Define SSH or local execution method.
- [x] Define application path.
- [x] Define benchmark command.
- [x] Define MySQL connection settings.
- [x] Define log paths.
- [x] Define systemd service names or restart commands.
- [x] Store settings in a config file or environment variables.

Done when:

- MCP implementations can consistently read the required environment settings.
- The target host, app path, benchmark command, DB settings, and log paths are documented.

Notes:

- Keep secrets out of git.
- Environment settings are recorded in `config/isucon14.yaml`.
- Current app host: `13.230.132.249` public, `192.168.0.11` private, EC2 tag `Name=isucon13-1`.
- Current bench host: `35.78.44.172` public, `192.168.0.12` private, EC2 tag `Name=isucon14-bench`.
- SSH method: `ssh -i /home/itohdak/.ssh/isucon.pem ubuntu@<public-ip>`.
- App path: `/home/isucon/webapp`.
- Bench binary: `/home/isucon/bench` on the bench host.
- App services observed: `isuride-go.service`, `isuride-matcher.service`, `isuride-payment_mock.service`, `mysql.service`, `nginx.service`.
- MySQL settings: app-local MySQL, host `127.0.0.1`, port `3306`, database `isuride`, version `8.0.46-0ubuntu0.24.04.3`, accessed with `sudo mysql` on the app host.
- Logs observed via `journalctl -u isuride-go.service -u isuride-payment_mock.service -u isuride-matcher.service`.
- Nginx routes app traffic only for `xiv.isucon.net` / `*.xiv.isucon.net`; direct IP target returns static/default content and makes `/client` fail.
- Use `--target https://bench.xiv.isucon.net --addr 192.168.0.11:443` for benchmark runs.
- Use a non-default payment port for the bench-run payment server because the bench host also runs the AMI's `payment_mock` on `:12345`.
- Working benchmark command:

```bash
cd /home/isucon
sudo -u isucon ./bench run \
  --target https://bench.xiv.isucon.net \
  --addr 192.168.0.11:443 \
  --payment-bind-port 12346 \
  --payment-url http://192.168.0.12:12346
```

## Milestone 2: Implement Minimum Real MCPs

- Status: Completed
- Completed date: 2026-09-21
- Goal: Replace the most important mock MCP behavior with real environment access.

Tasks:

- [x] Verify startup observability setup from `docs/isucon-startup-checklist.md`.
- [x] Verify startup git management setup from `docs/isucon-startup-checklist.md`.
- [x] Capture initial app source and redacted runtime config in git.
- [x] Confirm git status/diff can be collected on the app host.
- [x] Enable or verify Nginx LTSV access logs for API aggregation.
- [x] Enable or verify MySQL slow query log with `long_query_time = 0.0`.
- [x] Define route matching groups for `alp` or pprotein.
- [x] Implement `BenchmarkMCP.run()` with real benchmark execution and score parsing.
- [x] Implement `MySQLMCP.get_slow_queries()`.
- [x] Implement `MySQLMCP.explain_queries()`.
- [x] Add MySQL processlist or active query inspection if useful.
- [x] Implement `LogsMCP.collect_recent()` against real app/nginx/mysql logs.
- [x] Implement `GitMCP.diff()`.
- [x] Implement rollback-capable Git behavior.
- [x] Add tests for each real MCP path.

Done when:

- Nginx access logs and MySQL slow query logs are enabled and can be read after a benchmark run.
- The app host has a git baseline commit, and git diff/status are available for MCP collection.
- `benchmark`, `mysql`, `logs`, and `git` MCPs return real data from the prepared environment.
- Tests or manual commands can verify each MCP independently.

Notes:

- App host repository path: `/home/isucon`
- Branch: `main`
- Template reference: `https://github.com/itohdak/isucon_template`
- Initial commit: `f0b44a2 initial state`
- Observability commit: `18cd32d enable observability logs`
- Template layout commit: `c9292f8 add template server layout`
- Tracked initial content: `webapp`, `common`, `s1`, `s2`, `s3`, `.gitignore`
- Remote repository is not configured yet. Create a repository from `itohdak/isucon_template`, then set it as `origin`.
- Per-server overrides should live under `s1`, `s2`, and `s3` with the same relative paths as `common`.
- Raw `/home/isucon/env.sh` is not tracked; `common/env/env.sh.redacted` is tracked instead.
- Nginx LTSV access log verified at `/var/log/nginx/access.log`.
- MySQL slow query log verified at `/var/log/mysql/mysql-slow.log` with `long_query_time = 0.0`.
- Route matching groups were checked against post-benchmark Nginx logs and updated for ISUCON14 API paths.
- `BenchmarkMCP.run()` verified against the real bench host; latest MCP-driven run returned `pass=true`, score `629`.
- `MySQLMCP.get_slow_queries()` verified against `/var/log/mysql/mysql-slow.log`; current top query is `SELECT * FROM rides WHERE chair_id IS NULL ORDER BY created_at LIMIT 1`.
- `MySQLMCP.explain_queries()` verified; the top query currently scans `rides` with `Using where; Using filesort`.
- `MySQLMCP.get_processlist()` verified against the app host.
- `LogsMCP.summarize_routes()` verified against `/var/log/nginx/access.log`; current top route is `/api/chair/notification`.
- `GitMCP.status()` and `GitMCP.diff()` verified against `/home/isucon`; current app host working tree is clean.
- `GitMCP.restore()` requires explicit paths before running `git restore`.

## Milestone 3: Build Baseline Collection Flow

- Status: Completed
- Completed date: 2026-09-21
- Goal: Capture the current system state in one command before making changes.

Tasks:

- [x] Collect benchmark score.
- [x] Collect git status/diff.
- [x] Collect resource metrics.
- [x] Collect slow queries from `/var/log/mysql/mysql-slow.log`.
- [x] Collect relevant logs, including API route summaries from Nginx access logs.
- [x] Save the baseline as JSON or Markdown.
- [x] Expose the flow from `Orchestrator.run_skill("baseline")` or a CLI/demo command.

Done when:

- One command produces a baseline report that is useful for choosing the first bottleneck.

Notes:

- Manual benchmark smoke test with `-t 10` is not a useful baseline; it produced very low scores such as `20` or `26`.
- A standard benchmark run with the working command above produced `pass=true`, score `1002`, and no categorized errors on 2026-09-21.
- A run using the default payment port `12345` produced a payment consistency failure (`CODE=34`), likely because the bench host already has `payment_mock` listening on that port.
- `Orchestrator.run_skill("baseline")` now collects benchmark, git status/diff, resource snapshot, slow queries, route summary, and recent logs.
- Latest baseline report: `reports/baseline-isucon14-20260921-014901.json`.
- Latest baseline result: `pass=true`, score `673`, error counts `map[26:1]`.
- Latest app git status in the baseline report: clean.
- Latest resource snapshot after the benchmark: load average `13.55, 4.17, 1.91`, memory used `27.2%`, disk used `23%`.
- Latest top route by count: `/api/chair/notification` with `15184` requests, followed by `/api/internal/matching` with `6093` requests.
- Latest slow query candidates are concentrated around `ride_statuses` lookups such as `SELECT status FROM ride_statuses WHERE ride_id = ... ORDER BY created_at DESC LIMIT 1` and `chair_sent_at IS NULL ORDER BY created_at ASC LIMIT 1`.

## Milestone 4: Run One Full Improvement Loop

- Status: Completed
- Completed date: 2026-09-21
- Goal: Support a complete evidence-driven improvement cycle.

Tasks:

- [x] Use `monitor` and `trace_analysis` to gather bottleneck candidates.
- [x] Use `sql_tune` to summarize SQL/index candidates.
- [x] Record one bottleneck hypothesis.
- [x] Apply one minimal human-reviewed change.
- [x] Re-run benchmark.
- [x] Compare before/after score.
- [x] Record the result.
- [x] Roll back if the result is worse or unstable.

Done when:

- One full hypothesis -> change -> benchmark -> judgment cycle has been completed and recorded.

Notes:

- Bottleneck evidence came from the baseline report and direct `EXPLAIN`.
- Before report: `reports/baseline-isucon14-20260921-014901.json`.
- Before score: `673`, `pass=true`, error counts `map[26:1]`.
- Hypothesis: `ride_statuses` notification/latest-status lookups were doing full scans and filesorts because the table only had `PRIMARY KEY (id)`.
- Evidence before change:
  - `SELECT status FROM ride_statuses WHERE ride_id = ? ORDER BY created_at DESC LIMIT 1` used `type=ALL` and `Using where; Using filesort`.
  - `SELECT * FROM ride_statuses WHERE ride_id = ? AND chair_sent_at IS NULL ORDER BY created_at ASC LIMIT 1` used `type=ALL` and `Using where; Using filesort`.
- Change applied to live DB and `webapp/sql/1-schema.sql`:
  - `ride_statuses_ride_id_created_at_idx (ride_id, created_at)`
  - `ride_statuses_ride_id_app_sent_at_created_at_idx (ride_id, app_sent_at, created_at)`
  - `ride_statuses_ride_id_chair_sent_at_created_at_idx (ride_id, chair_sent_at, created_at)`
- Evidence after change:
  - latest-status lookup uses `ride_statuses_ride_id_created_at_idx` with `Backward index scan`.
  - app/chair unsent notification lookups no longer use full table scan.
- After report: `reports/baseline-isucon14-20260921-015831.json`.
- After score: `1297`, `pass=true`, error counts `map[]`.
- Score delta: `+624`.
- App repo commit: `b1bfb60 add ride statuses indexes`.
- Rollback was not needed because the benchmark passed and score improved.
- Next observed bottleneck candidates after the change:
  - `SELECT * FROM rides WHERE chair_id = ? ORDER BY updated_at DESC LIMIT 1`
  - `SELECT * FROM rides WHERE chair_id = ? ORDER BY updated_at DESC`
  - `SELECT * FROM chairs WHERE access_token = ?`
- Note: `trace_analysis` still uses the current mock APM implementation; the real decision used benchmark, slow query log, route summary, resource snapshot, and `EXPLAIN`.

## Milestone 5: Enforce Guardrails

- Status: Completed
- Completed date: 2026-09-21
- Goal: Prevent unsafe file, git, or shell operations.

Tasks:

- [x] Connect `Guardrails` to filesystem writes.
- [x] Connect `Guardrails` to shell command execution once `ShellMCP` exists.
- [x] Connect `Guardrails` to rollback/deploy operations.
- [x] Reject writes outside allowlisted paths.
- [x] Reject denied commands.
- [x] Require backup before writes where appropriate.
- [x] Add tests for allowed and denied operations.

Done when:

- Unsafe operations are rejected by code and covered by tests.

Notes:

- `Guardrails.is_allowed_path()` now uses boundary-aware path checks, so `/home/isucon2` does not match `/home/isucon`.
- `FilesystemMCP.write_file()` now rejects writes outside allowlisted paths.
- `FilesystemMCP.write_file()` creates a `.bak` backup before overwriting an existing file when backup enforcement is enabled.
- Added `ShellMCP` with denied-command and cwd allowlist checks.
- `GitMCP.restore()` now requires an allowed repo path, explicit paths for real restore, and repo-relative paths without parent traversal.
- `Orchestrator` now creates shared `Guardrails` and wires it into `GitMCP`, `FilesystemMCP`, and `ShellMCP`.
- Tests cover allowed and denied path writes, backup creation, shell command rejection, shell command allowance, and unsafe git restore path rejection.
- Actual deploy orchestration does not exist yet; deploy-specific guardrails should be enforced when Milestone 7 implements the deploy skill.

## Milestone 6: Persist History And Reports

- Status: Completed
- Completed date: 2026-09-21
- Goal: Keep a durable record of improvements and failed hypotheses.

Tasks:

- [x] Persist `HistoryMCP.record_run()` to a file or database.
- [x] Store hypothesis, evidence, changed files, scores, delta, and rollback status.
- [x] Implement `HistoryMCP.list_runs()` from persisted data.
- [x] Generate a human-readable report.
- [x] Add tests for history persistence.

Done when:

- Past runs can be listed and used to decide the next hypothesis.

Notes:

- `HistoryMCP.record_run()` now appends JSONL records to `reports/history.jsonl`.
- `HistoryMCP.record_run()` also writes a Markdown report under `reports/history/<run_id>.md`.
- `HistoryMCP.list_runs()` now reads from persisted JSONL instead of returning mock data.
- `HistoryMCP.generate_summary()` returns run count, total score delta, and the best run.
- Recorded the first real improvement run as `ride-statuses-indexes-20260921`.
- Improvement history file: `reports/history.jsonl`.
- Human-readable improvement report: `reports/history/ride-statuses-indexes-20260921.md`.
- Recorded improvement result: before `673`, after `1297`, delta `+624`, rollback `not_needed`, commit `b1bfb60`.
- Tests cover persisted history, reload via a new `HistoryMCP`, summary generation, and Markdown report creation.

## Milestone 7: Implement Deploy Skill

- Status: Completed
- Completed date: 2026-09-21
- Goal: Make the registered `deploy` skill executable.

Tasks:

- [x] Decide deploy command sequence for the environment.
- [x] Add deploy support to `Orchestrator.plan()`.
- [x] Add deploy support to `Orchestrator.run_skill()`.
- [x] Implement build/restart/migration steps as needed.
- [x] Verify service health after deploy.
- [x] Collect logs on failure.
- [x] Roll back on failed deploy if safe.
- [x] Add tests for deploy orchestration.

Done when:

- `deploy` is no longer registry-only and can safely apply/restart the updated artifact.

Notes:

- Added `DeployMCP` and wired it to `Orchestrator.run_skill("deploy")`.
- `Orchestrator.plan()` now includes `deploy`.
- Deploy command is configured in `config/isucon14.yaml`: `cd /home/isucon/common && sudo -u isucon bash ./deploy.sh`.
- Health check services are configured in `config/isucon14.yaml`: `isuride-go.service`, `isuride-matcher.service`, `isuride-payment_mock.service`, `mysql.service`, and `nginx.service`.
- `DeployMCP.deploy()` refuses dirty git working trees unless `allow_dirty=True`.
- `DeployMCP.deploy(dry_run=True)` runs non-destructive preflight checks: git clean, deploy script exists, deploy script syntax, command guardrail, and service health.
- Real environment preflight succeeded on 2026-09-21:
  - dirty files: none
  - deploy script exists: ok
  - deploy script syntax: ok
  - deploy command allowed: ok
  - all configured services: active
- Full live deploy was explicitly approved and succeeded on 2026-09-21:
  - deploy return code: `0`
  - dirty files: none
  - failure logs: none
  - `isuride-go.service`: active
  - `isuride-matcher.service`: active
  - `isuride-payment_mock.service`: active
  - `mysql.service`: active
  - `nginx.service`: active
- Post-deploy app repo status was clean.
- Automatic failed-deploy rollback was evaluated as not safe to perform generically yet because deploy may include migrations, config copies, service restarts, and permission changes. The current behavior is to stop, return failure logs, and require an explicit rollback action.
- Tests cover dirty-tree rejection, dry-run preflight-only behavior, deploy execution flow, health checks, and `Orchestrator.plan()`.
- Follow-up: implement a concrete failed-deploy rollback path after deploy semantics are confirmed.

## Milestone 8: Add Practical Automation

- Status: Completed
- Completed date: 2026-09-21
- Goal: Make the tool helpful during real contest iteration.

Tasks:

- [x] Compare slow queries across benchmark runs.
- [x] Highlight new errors after a change.
- [x] Detect score regression automatically.
- [x] Suggest the next endpoint/query/log area to inspect.
- [x] Integrate Netdata or APM if available.
- [x] Produce concise final iteration reports.

Done when:

- The tool reliably narrows down the next investigation area after each benchmark.

Notes:

- Added `IterationMCP` for before/after benchmark report comparison.
- Added `analyze_iteration` skill and wired it to `Orchestrator.run_skill("analyze_iteration")`.
- `IterationMCP.compare_reports()` compares score, regression status, benchmark error categories, slow query candidates, route counts, and resource load.
- It writes a concise Markdown report under `reports/iterations/`.
- Generated comparison report: `reports/iterations/iteration-20260921-022417.md`.
- Latest comparison result:
  - score: `673` -> `1297`, delta `+624`, regression `false`
  - resolved benchmark error category: `26`
  - next slow query candidate: `SELECT * FROM chairs WHERE access_token = ...`
  - next endpoint candidate: `/api/chair/notification`
  - resource note: load average `9.02`
- Practical automation was used for the next real improvement loop on 2026-09-21:
  - Before report: `reports/baseline-isucon14-20260921-015831.json`
  - After report: `reports/baseline-isucon14-20260921-022931.json`
  - Iteration report: `reports/iterations/iteration-20260921-022940.md`
  - History report: `reports/history/chair-ride-lookup-indexes-20260921.md`
  - Change: added `chairs_access_token_idx (access_token)` and `rides_chair_id_updated_at_idx (chair_id, updated_at)`.
  - Commit: `85d665d add chair and ride lookup indexes`
  - Score: `1297` -> `1972`, delta `+675`, regression `false`
  - Benchmark still passed, but error category `26` reappeared once; keep watching it.
  - Deploy after the change succeeded; all configured services were active.
  - Next candidates from the new report: `rides WHERE user_id = ? ORDER BY created_at DESC LIMIT 1`, `/api/chair/notification`, and CODE `26` investigation.
- Continued practical improvement loops on 2026-09-21:
  - `21411ab add ride user and coupon lookup indexes`
    - Added `rides_user_id_created_at_idx (user_id, created_at)` and `coupons_used_by_idx (used_by)`.
    - Before report: `reports/baseline-isucon14-20260921-022931.json`.
    - Adopted after remeasurement because the first run was noisy.
    - Adopted after report: `reports/baseline-isucon14-20260921-023808.json`.
    - Iteration report: `reports/iterations/iteration-20260921-023816.md`.
    - History report: `reports/history/ride-user-coupon-indexes-20260921.md`.
    - Score: `1972` -> `2076`, delta `+104`, errors `map[]`.
    - Deploy succeeded; all configured services were active.
  - `a3ca81e add ride chair created lookup index`
    - Added `rides_chair_id_created_at_idx (chair_id, created_at)`.
    - Before report: `reports/baseline-isucon14-20260921-023808.json`.
    - After report: `reports/baseline-isucon14-20260921-024119.json`.
    - Iteration report: `reports/iterations/iteration-20260921-024128.md`.
    - History report: `reports/history/ride-chair-created-index-20260921.md`.
    - Score: `2076` -> `2192`, delta `+116`, errors `map[]`.
    - Deploy succeeded; all configured services were active.
  - `b8a01f3 add chair location lookup index`
    - Added `chair_locations_chair_id_created_at_idx (chair_id, created_at)`.
    - Before report: `reports/baseline-isucon14-20260921-024119.json`.
    - After report: `reports/baseline-isucon14-20260921-024509.json`.
    - Iteration report: `reports/iterations/iteration-20260921-024519.md`.
    - History report: `reports/history/chair-location-lookup-index-20260921.md`.
    - Score: `2192` -> `2637`, delta `+445`, errors `map[]`.
    - Deploy succeeded; all configured services were active.
- pprotein-backed practical improvement loops on 2026-09-21:
  - `d3b8e5f enable pprotein pprof endpoint`
    - Added Go pprotein standalone integration on `:8888`.
    - Updated pprotein targets to include `http://s1:8888/debug/pprof/profile`.
    - pprotein collection succeeded with pprof, httplog, and slowlog targets.
  - `9465c20 limit owner chair distance aggregation`
    - Limited `/api/owner/chairs` total-distance aggregation to the target owner's chairs.
    - Added `chairs_owner_id_idx (owner_id)`.
    - Score: `2637` -> `2994`, delta `+357`, errors `map[]`.
  - `952c898 avoid rereading inserted chair location`
    - Removed the insert-then-select pattern in `chairPostCoordinate` by explicitly setting `created_at`.
    - Score: `2994` -> `4354`, delta `+1360`, errors `map[]`.
  - `2e1dd82 annotate hot sql queries`
    - Added SQL comments to hot-path queries so slow query logs show `api:` or `fn:` origins.
    - Covered notification, coordinate, nearby-chair, owner, matching, discount, and shared latest-status queries.
    - Verification: benchmark passed with score `4285`; slow query log contains comments such as `api:internalGetMatching`, `api:ownerGetChairs`, `fn:getLatestRideStatus`, and `fn:calculateDiscountedFare`.
    - This is an observability change, not a score-improvement change.
  - Rejected experiment: aggregate `getChairStats` with one SQL query.
    - Result: `/api/app/notification` returned many 500 responses during benchmark.
    - Action: reverted uncommitted `webapp/go/app_handlers.go` change and redeployed clean state.
- Current recorded improvement history summary: best observed score `4354`.
- Current next investigation candidates:
  - `/api/chair/notification` remains the highest request-count endpoint.
  - `COMMIT` / `START TRANSACTION` appears in slow logs, suggesting frequent notification transactions are now a meaningful cost.
  - `ORDER BY RAND()` in `internalGetMatching` still appears occasionally, but changing it affects matching behavior and should be handled carefully.
  - Further gains likely require code-level optimization or caching, not only simple indexes.
- Netdata itself is not installed on the instance; resource integration currently uses the SSH-backed `NetdataMCP` snapshot from `uptime`, `free`, `df`, and `ps`.
- Tests cover report comparison, resolved error detection, next-action suggestion, Markdown output, and orchestrator skill registration.

## Known Gaps

- `ShellMCP`, `DeployMCP`, and `IterationMCP` are now implemented, but remote command execution still happens partly via direct SSH subprocess calls rather than a single shared remote execution abstraction.
- Current APM integration is still mock data; real route latency currently comes from Nginx log aggregation instead.
- Netdata is not installed on the target instance; `NetdataMCP` is currently an SSH-backed lightweight resource collector.
- Automatic failed-deploy rollback is intentionally conservative and currently requires explicit user direction.
- README mentions YAML skill definitions, but skills are currently defined in Python.
