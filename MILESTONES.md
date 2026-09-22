# ISUCON AI Tools Milestones

This file is the working roadmap for turning the current mock MCP/Skill skeleton into usable ISUCON operations tooling.

When a milestone is completed, update:

- Status
- Completed date
- Notes
- Any follow-up tasks

## Current Status

- Last updated: 2026-09-22
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
- Latest app optimization commit: `9179ded close CODE=15 race: require notification-delivered COMPLETED before rematching chair`.
- Latest verified benchmark: `pass=true` across 5 consecutive runs (5228, 5021, 5160, 5138, 5078), errors `map[]` on all.
- Latest iteration report: `reports/iterations/iteration-20260922-220533.md`.
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
- SSH method: `ssh -i /home/itohdak/Downloads/isucon.pem ubuntu@<public-ip>`.
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
