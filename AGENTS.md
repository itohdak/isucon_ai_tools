# ISUCON AI Tools Agents

This file defines the operational agent roles for ISUCON improvement work.
Update it whenever agent roles, ownership, handoff rules, or report requirements change.

## Current Reality

There are two layers called "agent" in this repository:

1. `Orchestrator + Skill + MCP`
   - Implemented in `isucon_ai_tools/agents/orchestrator.py`.
   - Runs skills such as `baseline`, `sql_tune`, `deploy`, and `analyze_iteration`.
   - This is the current coded automation layer.

2. Human/Codex sub-agent workflow
   - Used when Codex explicitly delegates work to role-specific agents.
   - This is the operational collaboration layer.
   - It must be invoked deliberately during an improvement loop.

Do not assume that defining roles here automatically runs multiple agents.
For every serious optimization loop, Codex should explicitly name which agents were used and record their outputs.

## Agent Roster

| Agent | Primary Responsibility | Main Inputs | Main Outputs | Can Edit Code? |
| --- | --- | --- | --- | --- |
| Profiler Agent | Identify bottlenecks from benchmark, pprotein, alp, slp, pprof, logs. | Latest benchmark, pprotein artifacts, slowlog, httplog, pprof, route summary. | Ranked bottlenecks by total latency and error impact. | No |
| Resource Monitor Agent | Capture per-instance resource usage (CPU, load, memory, disk IO) while a benchmark is running, and flag whether any instance is resource-bound. | Netdata parent dashboard/API on the pprotein host, per-host CPU/load/memory/disk snapshots during the bench window. | Per-host resource summary during the bench window, and a bottleneck-type verdict (CPU-bound app/db/other, or not resource-bound). | No |
| App Understanding Agent | Understand ISURIDE behavior, regulations, API invariants, and code flow. | App manual, regulation docs, Go handlers, middleware, DB models. | Risk notes, invariants, safe change boundaries. | No |
| SQL Agent | Analyze query plans and database access patterns. | Slow queries, attributed SQL comments, EXPLAIN, schema, indexes. | SQL/index/cache candidates and correctness risks. | Usually no |
| Implementer Agent | Apply one selected minimal change. | Chosen hypothesis, file ownership, guardrails, existing patterns. | Patch, changed file list, implementation notes. | Yes |
| Verifier Agent | Validate behavior after a change. | Git diff, deploy result, benchmark result, logs, pprotein artifacts. | Pass/fail judgment, score delta, regression notes. | No |
| Recorder Agent | Persist the decision history. | Hypothesis, evidence, before/after scores, commit, artifacts. | Iteration report, milestone updates, architecture updates if needed. | Yes, docs/reports only |

## Default Improvement Loop

Use this loop for each score improvement attempt:

1. Profiler Agent reads the latest benchmark and pprotein artifacts.
2. Resource Monitor Agent captures per-host CPU/load/memory/disk during the same benchmark run (from the Netdata parent) and reports whether any instance is resource-bound.
3. App Understanding Agent checks whether the top candidates are safe under the ISUCON14 rules.
4. SQL Agent inspects query plans for the promising candidates.
5. Codex chooses exactly one hypothesis to implement, using the Resource Monitor Agent's verdict to decide between an application/SQL fix and an instance split (see `Resource And Split Policy`).
6. Implementer Agent or Codex applies the smallest useful change.
7. Codex deploys the change.
8. Verifier Agent checks benchmark, pprotein, logs, score delta, errors, and per-host resource usage.
9. Recorder Agent writes the iteration report and updates milestones.

If the next action is urgent or tightly coupled, Codex may perform it directly, but the final report must say that no sub-agent delegation was used and why.

## Sub-Agent Execution Protocol

Use this protocol whenever Codex is asked to continue optimization, improve score, investigate the next bottleneck, or run another improvement loop.

### Required At Loop Start

At the start of a non-trivial improvement loop, Codex should spawn or otherwise explicitly delegate these four analysis roles in parallel:

- Profiler Agent
- Resource Monitor Agent
- App Understanding Agent
- SQL Agent

Each role must receive a narrow question and must return a short, actionable output.

Every dispatch prompt should tell the agent to read its skill doc first (`docs/skills/<role>.md` — see Skill And MCP Mapping below), since that's where the concrete, currently-correct commands and gotchas live. Recommended prompts:

- Profiler Agent: "Read `docs/skills/profiler-agent.md` first. Using the latest benchmark and pprotein artifacts, rank bottlenecks by total API time, total SQL time, and benchmark errors. Do not propose code changes yet."
- Resource Monitor Agent: "Read `docs/skills/resource-monitor-agent.md` first. For the benchmark run that just finished, report per-host CPU/load/memory/disk and state whether any instance was resource-bound during the run, using the exact run window, not a post-hoc snapshot."
- App Understanding Agent: "Read `docs/skills/app-understanding-agent.md` first. For the top candidate APIs, identify ISUCON14 rule risks and invariants that must not break."
- SQL Agent: "Read `docs/skills/sql-agent.md` first. Run `slp --sort sum-query-time --reverse` (or an equivalent full aggregation) to get the complete ranked table of query shapes by total Query_time — not a narrative summary. Report the top 10-15 rows verbatim in your findings. Then inspect schema/index/query patterns for those candidates and suggest low-risk database-side improvements. If you flag any query outside the top 10-15 by total time for a different reason (e.g. high per-call/max latency, or a known risk area), say so explicitly and justify it separately from the total-time ranking, rather than blending it into the same list without distinction."

Codex should continue useful local work while these agents run, such as checking git status, reading the latest report, or preparing the benchmark context.

Codex should continue useful local work while these agents run, such as checking git status, reading the latest report, or preparing the benchmark context.

### When Implementation Can Be Delegated

An Implementer Agent (delegated or Codex acting directly) should read `docs/skills/implementer-agent.md` first for deploy gotchas and change-size discipline. Spawn an Implementer Agent only when all of these are true:

- The hypothesis has already been chosen.
- The file ownership is narrow and explicit.
- The patch can be bounded to one responsibility.
- The work does not require immediate back-and-forth with production logs.

Do not delegate implementation when the next step is tightly coupled to live deploy/debug feedback.
In that case Codex may implement directly, but the report must explain why.

### Verification

A Verifier Agent (delegated or Codex acting directly) should read `docs/skills/verifier-agent.md` first, particularly for run-count discipline (a single benchmark run is not conclusive in this environment). Verification can be handled by a Verifier Agent when it can run independently from ongoing analysis.
At minimum, the Verifier Agent should check:

- git status and commit hash
- deploy result
- benchmark pass/fail, score, and error counts
- pprotein artifacts and recorded repository hash
- top API and SQL totals after the run
- per-host resource usage during the run (CPU, load average, memory, disk IO) from the Netdata parent
- service errors or suspicious logs

If Codex verifies directly, record that in `Agents Used`.

### Recorder

A Recorder Agent (delegated or Codex acting directly) should read `docs/skills/recorder-agent.md` first — in particular, nothing is read automatically by a future session, so records must stand alone. After every benchmark-backed change, Recorder Agent or Codex must update:

- an iteration report under `reports/iterations/`
- `reports/summary/<contest>.md` (e.g. `reports/summary/isucon13.md`) when the overall status changes — see "Per-Contest Summary Reports" below
- `docs/agent-architecture.md` or this file when the agent process changes

### Allowed Reasons To Skip Sub-Agents

Skipping sub-agents is allowed only for:

- tiny documentation-only edits
- emergency rollback
- a one-command status check
- a user explicitly asking not to use sub-agents
- a task where tool limits or environment access prevent delegation

When skipped during an optimization loop, the iteration report must include the reason.

### Required Report Statement

Every benchmark-backed iteration must include one of these statements:

- "Sub-agents were used: Profiler, App Understanding, SQL, ..."
- "Sub-agents were not used because: ..."

## Evidence Rules

**Benchmark runs are a limited resource in a real contest, not a free/automated loop.** The multi-run verification guidance throughout this file and `docs/skills/verifier-agent.md` (2-3 runs for routine changes, 5+ for risky ones, A/B redeploys to check noise) assumes this *practice* environment's automated, freely-repeatable `./bench run` command. A real ISUCON contest benchmark is normally triggered manually through a portal website and is commonly rate-limited or capped in total attempts — do not assume that budget is available. See `docs/skills/verifier-agent.md`'s "Contest-Mode Adjustment" section for how to adapt (build confidence before spending a run, accept fewer runs per hypothesis, be more conservative in change design rather than relying on repeated runs to catch mistakes).

Before every benchmark run, commit the exact application/config state being measured. pprotein records the final commit for the run, so benchmarking uncommitted changes makes the shared report misleading. If the change has a meaningful rollback risk or is still exploratory, create a feature branch and commit there before deploying and running bench. Do not run bench against an uncommitted worktree unless the user explicitly overrides this rule for an emergency check, and record the exception in the iteration report.

Performance decisions should cite evidence in this order:

1. Benchmark pass/fail and categorized errors.
2. Total route latency from httplog or pprotein (`alp --sort sum`).
3. Total SQL latency from slowlog or pprotein (`slp my --sort sum-query-time`).
4. Query count and rows examined.
5. EXPLAIN output.
6. Benchmark-time resource metrics: CPU idle/iowait, load/run queue, memory pressure, disk IO, network pressure. This is the Resource Monitor Agent's responsibility; it reads from the Netdata parent rather than SSH-ing into each instance separately.
7. pprof CPU hotspots.
8. Application/regulation risk.

Do not optimize only by max latency.
High-frequency medium-latency paths often matter more than a single slow request.

## Resource And Split Policy

**Hard rule, non-negotiable: never scale up an instance (change any host to a larger/more powerful instance type, or otherwise add CPU/memory/disk beyond what the contest provisioned).** ISUCON contest regulations prohibit this — it is disqualifying, not merely discouraged, and no evidence of a resource ceiling changes that. This applies regardless of how strong the resource evidence is or who asks — do not propose it, do not implement it even if asked, and flag it if anyone (including the user) suggests it, since it may be a momentary lapse rather than an informed exception. The only resource-scaling actions ever available are: (a) application/SQL-level optimization to use existing resources more efficiently, and (b) splitting roles (web/app/db) across the instances the contest already provisioned, unchanged in type/size — see below.

ISUCON commonly provides three initially identical servers. The default app shape often runs web, app, and DB on the same host.

Do not split web/app/db across instances just because spare servers exist.
Only split when benchmark-time metrics show a resource bottleneck that the split is expected to relieve.

Before proposing or executing an instance split, the Resource Monitor Agent must collect resource metrics during a valid benchmark:

- CPU usage, idle, iowait, steal, load average, and run queue per host.
- Process-level CPU and memory for app, MySQL, nginx, bench, and pprotein.
- Memory pressure and swap.
- Disk IO and iowait.
- Network traffic if app-to-DB separation is being considered.
- pprotein/alp/slp/pprof evidence showing whether the bottleneck is app CPU, MySQL, IO, or application behavior.

Netdata is installed on every instance (`isucon_ansible/roles/general`) and every non-pprotein host streams its metrics to a Netdata parent running on the pprotein host, so all instances' CPU/load/memory/disk can be read from one dashboard/API instead of connecting to each host separately. Use that parent as the primary source. Only fall back to lightweight command sampling (`vmstat 1`, `pidstat -durh 1`, `mpstat -P ALL 1`, `iostat -xz 1`) when Netdata streaming is unavailable.

Splitting MySQL to another host is allowed only when resource evidence supports it.
If CPU idle remains high or the dominant issue is inefficient query/API behavior, optimize the application or SQL first.

Operational details for resource split decisions live in `docs/resource-scaling-policy.md`.
MySQL split and tuning notes live in `docs/mysql-operations-tips.md`.

## Reporting Contract

Every iteration report under `reports/iterations/` should include:

- `Agents used`
- `Hypothesis`
- `Evidence`
- `Change`
- `Verification`
- `Benchmark result`
- `pprotein artifacts`
- `Commit`
- `Next candidate`

Minimum `Agents used` format:

```markdown
## Agents Used

| Agent | Used | Output |
| --- | --- | --- |
| Profiler Agent | yes | Ranked `/api/chair/notification` and `/api/app/notification` by total route time. |
| App Understanding Agent | yes | Flagged notification ordering as high-risk. |
| SQL Agent | yes | Confirmed latest-status lookup dominates slowlog total time. |
| Implementer Agent | no | Codex implemented directly because the patch was small and coupled. |
| Verifier Agent | yes | Benchmark passed and pprotein artifacts were recorded. |
| Recorder Agent | yes | Wrote this report and updated the summary. |
```

## Per-Contest Summary Reports

There is one running summary file per contest/project at `reports/summary/<contest>.md` (e.g. `reports/summary/isucon13.md`, `reports/summary/isucon14.md`) — a chronological, append-only narrative log of overall status: accepted/rejected iterations with their score deltas, environment changes, and user-directed policy changes. It is the "read this first" entry point for a session resuming work on that contest, before diving into the much more detailed per-change evidence under `reports/iterations/`. Full current environment facts still live in `config/<contest>.yaml` and this file's "Current Environment Notes" sections — the summary file is a log, not a source of truth for current state.

(`reports/history/`, `reports/history.jsonl`, and `reports/baseline-*.json` are NOT part of this convention, despite similar naming — they were real output of the now-archived Python MCP/orchestrator layer's `HistoryMCP`/`Orchestrator.run_skill("baseline")`, genuinely used for one session on 2026-09-21 and never touched again since. Moved to `archive/reports/` on 2026-09-23 alongside `MILESTONES.md`, for the same reason. Do not write to these paths; use `reports/iterations/` and `reports/summary/<contest>.md` instead.)

Update the relevant `reports/summary/<contest>.md` (never both — write to the contest actually being worked on) as part of the Recorder role, alongside every iteration report, and also for non-benchmark-backed events worth a human knowing about later (an environment recreation, a user correction, an incident like a broken observability pipeline). Append new entries at the end; do not rewrite or delete earlier entries, and do not edit another contest's summary file when working on a different one.

This replaces the older `MILESTONES.md` convention. That file mixed two things — build-out tracking for an earlier, now-archived Python MCP/orchestrator tooling layer (see `archive/NOTE.md`) that has nothing to do with actual ISUCON tuning, and a later, informally-added running-status narrative that overlapped with `reports/iterations/`. The user pointed this out on 2026-09-23 and asked for it to be retired: `MILESTONES.md` was moved to `archive/MILESTONES.md` (frozen, not updated further) and its narrative-summary role was split out per-contest into `reports/summary/<contest>.md` as described above. Do not create or update a top-level `MILESTONES.md` again.

## Ownership Rules

When using an Implementer Agent:

- Assign explicit file ownership before work starts.
- Do not let two agents edit the same files in parallel.
- Tell the agent that other changes may exist and must not be reverted.
- Require a final answer listing changed files.
- Review the patch before deploy.

Suggested ownership boundaries:

- Go application behavior: `webapp/go/*.go`
- SQL schema or seed changes: `webapp/sql/*`
- Deployment/runtime changes: `common/`, `s1/`, `s2/`, `s3/`, systemd/nginx/mysql config copies
- Tooling changes: `isucon_ai_tools/isucon_ai_tools/**`
- Documentation/report changes: `docs/`, `reports/` (including `reports/summary/<contest>.md`), `AGENTS.md`

## Safety Boundaries

**Never do, regardless of approval or how compelling the evidence looks:**

- Scale up any instance (bigger/more powerful instance type, or otherwise more CPU/memory/disk than the contest provisioned). ISUCON regulations prohibit this outright — see Resource And Split Policy above. This is not an "ask the human" item; it is never done.

Codex may proceed without asking for routine work:

- Reading logs and reports.
- Running local tests.
- Aggregating httplog and slowlog.
- Running practice benchmark when already authorized in the current flow.
- Adding low-risk indexes or local cache fields when evidence is strong.
- Writing reports and milestone updates.

Ask the human before:

- Changing matching strategy.
- Changing notification semantics.
- Changing `/api/initialize`.
- Changing deploy scripts.
- Adding background workers.
- Deleting data or resetting git state.
- Running destructive commands.
- Exposing pprotein or internal services publicly.

**Splitting web/app/db roles across instances no longer requires asking first** (standing authorization from the user, given 2026-09-23, in response to being asked about the split flagged as a next candidate at the end of the first ISUCON13 tuning session): once the Resource Monitor Agent has produced real benchmark-time evidence of a resource bottleneck the split is expected to relieve (per the Resource And Split Policy above — same instance type/size as already provisioned, never a scale-up), Codex may execute the split directly, same as any other evidence-backed change in the routine-work list above. This is narrower than it sounds: it authorizes *executing* an evidence-based split without a pause, it does not relax the evidence bar itself (still needs the Resource Monitor Agent's data first, not just a hunch) and it does not touch the absolute, never-relaxable no-scale-up rule.

## Skill And MCP Mapping

Each Agent Roster role has a markdown **skill doc** under `docs/skills/` containing the concrete, verified commands, access patterns, and known gotchas for that role, written from what has actually worked (and failed) in this environment. **Read the relevant skill doc before dispatching or acting as that role** — it is the current, trustworthy operational reference for that role, more so than the "Useful MCPs" column below.

The Python `isucon_ai_tools/isucon_ai_tools/mcp/*.py` layer is only partially real, and has not been kept in sync with infrastructure changes (notably the MySQL split to `s3`). Verified status as of the DB split:

- `apm.py` — **fully mock**: hardcoded fake data (`/api/users`, `/api/orders` — routes that don't even exist in this app), not connected to anything.
- `netdata.py` — real code, correctly implements the Netdata HTTP API, but **currently non-functional**: it's configured to hit a private VPC IP unreachable from the operator machine (verified by running it — every metric fetch times out). Use the Resource Monitor Agent skill's SSH+localhost pattern instead.
- `mysql.py` — real SSH-based code, but **hardcoded to the app host (`s1`)** for both live queries and slow-log tailing. Since the DB split, this silently reads `s1`'s stale, no-longer-updated slow log instead of erroring. Use the SQL Agent skill's direct-to-`s3` pattern instead.
- `git.py` (and structurally similar `benchmark.py`/`deploy.py`/`logs.py`) — real and verified working (SSH to the public IP, matching what the skill docs also do directly).
- `filesystem.py`/`history.py`/`iteration.py`/`shell.py` — local-only operations, not host-dependent, not verified against the split.

None of this MCP/orchestrator layer has actually been used to do real ISUCON tuning work this session — every real interaction with the live environment (SSH, MySQL, benchmarks, CloudFormation, Ansible, git) has gone through direct Bash/SSH commands inside an Agent-tool-dispatched subagent following that role's skill doc. Treat the skill docs as the source of truth; treat "Useful MCPs" as aspirational/partially-stale unless you've just re-verified the specific tool you're about to rely on.

| Agent | Skill Doc | Useful Skills (Python registry) | Useful MCPs (verify before trusting — see above) |
| --- | --- | --- | --- |
| Profiler Agent | `docs/skills/profiler-agent.md` | `baseline`, `monitor`, `trace_analysis`, `analyze_iteration` | `BenchmarkMCP`, `PproteinMCP`, `LogsMCP`, `MySQLMCP`, `NetdataMCP` |
| Resource Monitor Agent | `docs/skills/resource-monitor-agent.md` | `monitor`, `baseline` | `NetdataMCP` (broken — see above) |
| App Understanding Agent | `docs/skills/app-understanding-agent.md` | `trace_analysis`, `analyze_iteration` | `FilesystemMCP`, `LogsMCP`, `HistoryMCP` |
| SQL Agent | `docs/skills/sql-agent.md` | `sql_tune`, `trace_analysis` | `MySQLMCP` (stale post-split — see above), `LogsMCP` |
| Implementer Agent | `docs/skills/implementer-agent.md` | `deploy` after patch review | `FilesystemMCP`, `GitMCP`, `ShellMCP`, `DeployMCP` |
| Verifier Agent | `docs/skills/verifier-agent.md` | `baseline`, `deploy`, `analyze_iteration` | `BenchmarkMCP`, `DeployMCP`, `LogsMCP`, `PproteinMCP`, `GitMCP` |
| Recorder Agent | `docs/skills/recorder-agent.md` | `record_improvement` | `HistoryMCP`, `IterationMCP`, `GitMCP` |

## Current Environment Notes — ISUCON13 (ISUPipe) — ACTIVE PROJECT

**This is the currently active project as of 2026-09-23.** A separate, currently-paused ISUCON14 (ISURIDE) project also lives in this same `isucon_ai_tools` repo (its own config, reports, and environment notes are further below) — do not mix up route lists, service names (`isuride-*` vs `isupipe-*`), schema, or scoring model between the two. ISUPipe scores by total Tip (ISUCOIN) amount over the bench run, not a synthetic points formula.

Full environment facts: `config/isucon13.yaml`. Key points:

- This is a self-managed practice environment built from the team's own saved CloudFormation template (`isucon_cf_provisioning/isucon13/cf-template-isucon13.yaml`), not the ISUCON13 contest portal. The only authoritative ISUCON13 references are `/home/itohdak/Downloads/isupipe.md` and `/home/itohdak/Downloads/cautionary_note.md` — general internet search for ISUCON13 contest info is disallowed per user instruction (tool documentation lookups for generic OSS like pprotein are fine).
- **MySQL split executed 2026-09-23** (commit `309c390` in `isucon13_practice_3`): `s1` (app, private `192.168.0.11`) now runs `isupipe-go.service`, `pdns.service`, `nginx.service` only. `s2` (private `192.168.0.12`) is the dedicated MySQL host (`isupipe` + `isudns` databases; PowerDNS's `pdns` process itself still runs on `s1`, only its `isudns` backend DB moved). `s3` (private `192.168.0.13`) remains the dedicated bench/pprotein host, app-role services stopped and disabled. This was the evidence-based split flagged since iteration 5 of the first tuning session (Resource Monitor Agent: `s1`'s 2 vCPUs saturated, `mysqld` ~1 core + app ~0.65 core) and executed under the user's standing authorization (see Safety Boundaries) once they confirmed it — same instance type/size as provisioned, not a scale-up. **Result: avg score 17424.7 → 27934.7 (3 runs: 28773/27402/27629, all `pass=true`) — a further ~1.6x gain**, confirming the CPU-saturation hypothesis. Mechanics: `s2`'s `mysqld.cnf` now tracks `bind-address=0.0.0.0` (restricted at the security-group/VPC layer to `192.168.0.0/24`); `isucon@'%'`/`isudns@'%'` remote-capable users created via `webapp/sql/initdb.d/00_create_database.sql` (the AMI's default users were `localhost`-only); `s1`'s `env.sh` and `/etc/powerdns/pdns.d/gmysql-host.conf` (now tracked at `common/etc/powerdns/pdns.d/gmysql-host.conf`) both point at `192.168.0.12`. **Gotcha hit and fixed**: `isupipe-go.service`'s unit file had `Requires=mysql.service` — stopping the now-redundant local `mysql.service` on `s1` automatically killed the app too via systemd's dependency semantics, with no obviously-related error (just "Stopped isupipe-go" moments after "Stopped mysql" in the journal). Removed both `After=mysql.service`/`Requires=mysql.service` from the tracked unit file. **New deploy split**: `common/deploy.sh` (app host, `s1`) no longer touches `mysql` at all; a new `common/deploy_db.sh` (db host, `s2`) copies only `mysqld.cnf`, restarts `mysql`, and truncates the slow log — kept separate from `deploy.sh` because `common/etc/` also holds app-host-only files that must never land on `s2`. `s2` now has its own git checkout (same repo, same SSH deploy key) so `deploy_db.sh` can run there the same way `deploy.sh` runs on `s1`.
- The practice domain is `u.isucon.local` (self-signed cert in `/etc/nginx/tls`), not the real contest's `u.isucon.dev`. PowerDNS on the app host needs `ISUCON13_POWERDNS_SUBDOMAIN_ADDRESS` in `/home/isucon/env.sh` set to that host's own private IP, then `bash /home/isucon/webapp/pdns/init_zone.sh` re-run, so `pipe.u.isucon.local` / `*.u.isucon.local` resolve to it.
- Benchmark command (from `s4` since 2026-09-24; it was `s3` before): `sudo -u isucon /home/isucon/bench run --target https://pipe.u.isucon.local --nameserver 192.168.0.13 --webapp 192.168.0.11 --enable-ssl` (`--nameserver` is the DNS host s3). Original baseline (2026-09-23, commit `d5bd00d`): `pass=true`, `score=3371`. Current topology and IPs: see `config/isucon13.yaml`.
- **pprotein collect trigger is a plain GET, not POST**: `curl http://127.0.0.1:9000/api/group/collect` (from `s4`, the pprotein host). A POST returns 404. `webapp/go/main.go`'s `initializeHandler` calls this asynchronously and best-effort via `collectPprotein()`, matching the isucon14_practice pattern; `go standalone.Integrate(":8888")` was added to `main()` for pprof (required adding the `github.com/kaz/pprotein` dependency via `go get` + `go mod tidy`, which also bumped the go toolchain to 1.23.3 and a couple of transitive deps as an unavoidable side effect).
- **MySQL slow query log was OFF by default on the ISUCON13 AMI** (`slow_query_log=0`, commented out in `mysqld.cnf`, and `/var/log/mysql/` didn't even exist / wasn't writable) — this silently broke pprotein slowlog collection with `failed to open: ... no such file or directory` until fixed. Enabled `slow_query_log=1`, `long_query_time=0`, `slow_query_log_file=/var/log/mysql/mysql-slow.log` on both `s1` and `s2` (symmetry) and created `/var/log/mysql/` with permissive permissions. Check this first if a slowlog artifact ever goes missing/empty again after an environment recreation.
- **CRITICAL, user-flagged incident (2026-09-23): both the nginx access log and the MySQL slow log went dark for large stretches of the first 10-iteration session, and it was not caught until the user asked "what evidence were you actually using?" after the loop finished.** Two independent causes, now both fixed (commit `9983294` in `isucon13_practice_3`) and verified live with a real `alp ltsv`/slow-log query against fresh traffic:
  1. `common/etc/nginx/nginx.conf` was left on the AMI's stock `access_log ... ;` directive using the default `combined` format, which has no `$request_time` field. `profiler-agent.md`'s documented command is `alp ltsv --file <httplog> ...` — running `alp ltsv` against a `combined`-format file does not error, it silently returns a **valid-looking but completely empty table** (zero rows). This was actually *noticed* by the Profiler Agent in iteration 1 of that session ("nginx access log is stock combined format... alp-based route latency is currently unavailable") but was only logged as a "follow-up," never fixed, and every later iteration's route-latency claims relied on other sources (journalctl-parsed Go app request logs, cached data from one earlier SQL Agent dispatch, and direct code reading) instead — legitimate evidence, but the user reasonably expected the normal alp/httplog pipeline to be the source and it wasn't. **Fixed**: added an `ltsv` `log_format` (same shape as the ISUCON14 project's, with `reqtime`/`apptime`) and switched `access_log` to use it, in the tracked `common/etc/nginx/nginx.conf` so it survives every `deploy.sh` run.
  2. Separately, MySQL's slow query log — enabled correctly during initial environment setup (see the bullet above) — was later disabled again mid-session: iteration 6 of that tuning loop found `long_query_time=0` cost ~20-25% benchmark score and reverted the setting **in the tracked `common/etc/mysql/mysql.conf.d/mysqld.cnf`**, not just live on the host. Since `deploy.sh` copies that tracked file over the live config and restarts `mysql` on every single deploy, this silently disabled slow-query logging for the rest of that session (iterations 7-10) too, with no error surfaced anywhere. **Fixed**: re-enabled `slow_query_log=1`/`long_query_time=0` in the tracked config so it's on by default again; the score cost is real (confirmed ~16000-16300 vs ~17400-18200 with it off, at the current code state) but the user explicitly wants these logs available from the moment the environment is up, for humans to reference, not just agents — treat "environment default has full logging on" as the standing baseline, and treat disabling logging for one specific maximum-score attempt as a deliberate, temporary, explicitly-flagged exception, never something silently left off after an iteration ends.
  - Also added: `common/deploy.sh` now truncates (`sudo truncate -s 0`, safe on files with an open writer) both `/var/log/nginx/access.log` and `/var/log/mysql/mysql-slow.log` after every deploy, so `alp`/`slp` analysis of "the log" always means "since the last deploy," not "since instance boot" — before this, `mysql-slow.log` had silently grown to 1.4GB from accumulated historic runs.
  - **Lesson for future sessions**: an agent's own performance-motivated revert of an *observability* setting (as opposed to reverting a functional/behavioral change) needs to distinguish "turn this off for the one risky benchmark run being measured" from "remove this from the environment's standing configuration" — the tracked config file IS the standing environment state here (deploy.sh enforces it every time), so committing a revert to it has a much bigger, longer-lived blast radius than a live-only `SET GLOBAL`/`sed` change would. Before committing a revert to a tracked config file, ask whether the change is meant to be permanent policy or just true for the one A/B test at hand.
- **Gitignore trap**: a bare `go/` line in `.gitignore` (copied from the isucon14_practice pattern, intended only to exclude the isucon user's home-directory `~/go` module cache) is an *unanchored* gitignore pattern and matches a directory named `go` at *any* depth — it silently excluded the entire `webapp/go/*.go` application source from the very first `git add -A`, and `git status`/`git add` gave no error, just quietly omitted those files. Caught only by explicitly diffing `git ls-files webapp/go/` against `find webapp/go -type f` after the fact. Fixed by anchoring the pattern to `/go/`. **Any time a `.gitignore` is copied from another ISUCON project, re-verify with `git ls-files <app-source-dir>` that the actual application source landed in the initial commit — do not trust a clean `git status` alone.**
- Shared GitHub repository: `git@github.com:itohdak/isucon13_practice_3.git`. **The operator sandbox's auto-mode classifier has intermittently flagged plain `git push` over SSH to the app host as "Credential Leakage" / "Data Exfiltration" and blocked it** even though it's a normal push to the user's own prepared, private repo; a same-command retry succeeded both times this was hit. If a push is denied, retry once or twice before treating it as a real blocker worth surfacing to the user.
- **4-host layout (2026-09-24), added at the user's request**: `s1` app+nginx only, `s2` MySQL for the app DB, `s3` DNS host (`pdns_server` + a local MySQL holding only `isudns`), `s4` (new, `192.168.0.14`, added via a CloudFormation change set — only `Instance4`/`InstanceIP4` were Adds, no replacements; template `isucon_cf_provisioning/isucon13/cf-template-isucon13-4host.yaml`) bench + pprotein + netdata parent. Rationale: the real contest provisions 3 competition servers and the bench runs portal-side, so using the 3 provisioned instances all as competition servers is closer to the contest and is not a scale-up. **Measured before the move** (bench window, 1 core = 100%): s1 isupipe ~56% + nginx ~25% + pdns_server ~5% — DNS is *not* CPU-bound on the app host; but on s2 the pdns queries were only 6% of statements yet ~27% of summed query time (pdns.conf has `cache-ttl=0`), i.e. the DNS attack's real cost was MySQL CPU on s2, and the benchmark's DNS-attacker parallelism is adaptive (rises when DNS answers fast), which is why speeding DNS up on a shared host kept regressing. **After the move**: s2 `mysqld` ~139% → ~100%, but the DNS load moved to s3 (`mysqld` ~133%, `pdns_server` ~10%); DNS successes per run doubled (~5k → ~10k, attacker parallelism 4). Scores were bimodal — the first run after an idle gap ~191-193k, immediately following runs ~155-171k (previous topology: ~160k steady) — so treat the net gain as unproven until the run-order effect is understood; isolating DNS on s3 makes DNS-side tuning (an index on `isudns.records(name,type)`, pdns query cache) cost-free for the other hosts, which was the reason for the move and has not been tried yet. Gotchas: the DNS zone is still loaded by s1's `init.sh` -> `init_zone.sh`; `pdnsutil` there writes to s3's isudns DB through s1's tracked `/etc/powerdns/pdns.d/gmysql-host.conf` (`192.168.0.13`) while `pdns_server` on s1 is stopped/disabled; `deploy.sh` no longer restarts pdns; `rotateLogs()` in `/api/initialize` also truncates s3's slow log (env `ISUCON13_DNS_HOST`).
- **Per-run log rotation (2026-09-24, user request)**: `POST /api/initialize` now truncates the nginx access log (s1) and the MySQL slow logs (s2 and s3, via ssh from s1) right after `init.sh` and before the pprotein collect, so each bench run starts from empty logs and pprotein's httplog/slowlog artifacts never accumulate earlier runs (env `LOG_ROTATE_DISABLED=1` turns it off). Verified: consecutive runs produced artifacts starting at each run's start time with the same line counts (~127k httplog lines, ~177MB slowlog). This is a small addition to `/api/initialize` (normally an ask-first area) made on the user's explicit request; it is best-effort and never fails initialization.
- **Stack recreated 2026-09-24** after the CloudFormation stack was accidentally deleted overnight. Restored (not re-tuned from scratch) by: recreating the same CF stack from `isucon_cf_provisioning/isucon13/cf-template-isucon13.yaml`, re-running the `general`/`pprotein` ansible roles, giving `s1` and `s2` fresh git checkouts of `isucon13_practice_3` at its last-pushed commit, reapplying the DB schema+remote users to `s2`'s fresh MySQL (same `DROP DATABASE`/`CREATE DATABASE` + `10_schema.sql` + `00_create_database.sql` procedure as the original split — all tuning progress lives in git and MySQL schema/index state, not in any AWS resource, so this fully restores prior work), repointing `env.sh`/PowerDNS's `gmysql-host.conf` at the new instances' (unchanged) private IPs, and stopping local `mysql` on `s1` again. Re-verified with a benchmark run scoring in the expected range before resuming tuning. Public IPs are reassigned on every recreation (private IPs `.11`/`.12`/`.13` are fixed by the template) — `config/isucon13.yaml` is always the source of truth, never trust IPs from chat history.
- **Freshly recreated instances run `unattended-upgrade` for the first ~30-60 minutes after boot — disable it before benchmarking (found 2026-09-24).** It burned ~92% of a core on `s1` and did a full mysql-server/systemd/kernel/nginx upgrade on `s2` (25+ min, 35-97% CPU), silently producing scores of 16086-24473 that looked like a regression. After any stack recreation: `sudo systemctl disable --now unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer` on every load-targeted host, then confirm no `/usr/bin/python3 /usr/bin/unattended-upgrade` process remains (`ps aux --sort=-%cpu | head`). If one is already mid-run, send it a plain SIGTERM to the real PID (it finishes the current dpkg batch then stops; `sudo dpkg --audit` should then be clean) — never SIGKILL it mid-dpkg on the DB host. Gotcha: `pkill -f unattended-upgrade` / `pgrep -f unattended-upgrade` over ssh match the ssh shell's own command line (exit 255 / never-ending wait loops); use an anchored pattern like `pgrep -f '^/usr/bin/python3 /usr/bin/unattended-upgrade'`. Also do not run heavy log analysis (`slp` on the multi-hundred-MB slow log, which OOM-kills on the 3.6GB `s2` — use a tail) while a benchmark is being scored.
- **Second tuning session results (2026-09-24, iterations 2-16): 27750 -> ~155-162k (~48x the 3371 baseline).** Order of wins: MySQL commit-path config on s2 (no binlog, `innodb_flush_log_at_trx_commit=2`, O_DIRECT: +13%); in-process caches of *immutable* data (icon sha256, users, themes, icon bytes + name->user + 304 on `If-None-Match`: +28%, +65%, +53%); `reservation_slots` sargable range (+13%); `interpolateParams=true` on the DSN (+20%); `e.Debug=false`, nginx upstream keepalive + TLS session cache (+10%), dropping the echo access logger (+5%). Rejected (A/B): `isudns.records` index (third time; the bench's DNS attacker parallelism climbed to 9), livestream tag-list cache (-7.6%). Full trail in `reports/summary/isucon13.md`. Reusable lessons: (1) profile with *both* pprotein's pprof (`go tool pprof -top -cum` on the s3 artifact; a manual `/debug/pprof/profile` fails with "cpu profiling already in use" because pprotein holds it) and per-process netdata on both hosts; (2) check the DB driver/DSN for per-statement round-trip multipliers (`interpolateParams`) — `slp`'s SELECT/INSERT/UPDATE filter hides `Prepare`/`Close stmt`, count them in the raw log; (3) a cache/optimization that pays under one host balance can regress under another (and vice versa), and the closed-loop bench shifts scenario mix when a path gets faster — A/B every step with several runs (single-run noise is +/-5% above 100k); (4) `mysql-slow.log` is only truncated by `deploy_db.sh` (pprotein collects a 60s tail and never truncates it): after ~35 bench runs it hit 14GB — truncate it (`sudo truncate -s 0 /var/log/mysql/mysql-slow.log`) periodically; (5) after a reboot `s2` may boot a newer kernel than `s1` if a partial `unattended-upgrade` ran (kernel 6.8.0 on s2 vs 6.2.0 on s1 at the end of this session) — the symmetry preference applies, consider upgrading/aligning or note it in the report. Post-reboot verification done: all services and tracked settings came back unaided and the bench passed (~155k).
- **Netdata streaming to the pprotein parent (s3) is verified genuinely working** (checked 2026-09-23 in response to the user asking whether this was as intended): `curl http://127.0.0.1:19999/api/v1/info` on `s3` lists `mirrored_hosts: [s3, s1, s2]` all `reachable: true`, and `curl 'http://127.0.0.1:19999/host/s1/api/v1/data?chart=system.cpu&after=-60'` returns real, live, per-second data points from `s1`. This is unlike the nginx/MySQL log gaps above — netdata was not affected and needed no fix.
- Node.js reference implementation: the `stats-handler.ts` patch documented in `isupipe.md` (guards `Number(tips)`/`Number(totalTip)` against the MySQL driver returning a string for `SUM()`) was already present in this AMI's `webapp/node` source as shipped — verified, no action needed unless that file is later regenerated from an older template.

## Current Environment Notes — ISUCON14 (ISURIDE) — paused, kept for reference

**Role mapping as of the 2026-09-23 environment recreation: `s1`+`s2` are the load-targeted hosts (app, db) and `s3` is the dedicated bench/pprotein host — swapped from the original `s1`+`s3` load-targeted / `s2` bench arrangement, for clarity. Private IPs per host label are fixed by the CloudFormation template (`s1`=`.11`, `s2`=`.12`, `s3`=`.13`); public IPs are reassigned on every stack recreation — check `config/isucon14.yaml` for the current values, do not trust old IPs in chat history or old report files.**

- App host: `s1`, private `192.168.0.11`, public `52.69.150.66` (current as of the 2026-09-23 recreation — reconfirm in `config/isucon14.yaml` if this looks stale).
- DB host: `s2`, private `192.168.0.12`, public `54.95.127.250` — dedicated MySQL host, split from `s1` on 2026-09-23 after the Resource Monitor Agent found the combined host CPU-bound (mysqld averaging ~97.7% CPU, saturating one of its 2 vCPUs) during a valid benchmark run; moved from `s3` to `s2` in the later role-swap recreation. Only `mysql.service` runs there; `isuride-go.service`, `isuride-matcher.service`, `isuride-payment_mock.service`, and `nginx.service` are stopped and disabled on it.
- Bench/pprotein host: `s3`, private `192.168.0.13`, public `35.73.191.95` — moved from `s2` in the role-swap recreation. `isuride-go.service`, `isuride-matcher.service`, `isuride-payment_mock.service`, `nginx.service`, and `mysql.service` are all stopped and disabled here too (dedicated bench/pprotein role, no app/db services needed).
- **The app's `POST /api/initialize` handler (`webapp/go/main.go`'s `collectPprotein()`) has a hardcoded default pprotein collection URL** (`http://s3:9000/api/group/collect` as of the current role mapping) that must be updated (and redeployed) whenever the bench/pprotein host's logical label changes — it is not derived from ansible inventory or `config/isucon14.yaml` at runtime. Same caveat for `isucon_ansible/roles/pprotein/tasks/main.yaml`'s host-alias `/etc/hosts` registration task, which must include every group (`pprotein`, `webapp`, `db`) that any other host needs to resolve by bare name — a prior version of this task omitted the `db` group entirely, which was a latent bug independent of which host played which role.
- **`deploy.sh` per-server override gotcha**: `common/deploy.sh` checks `../${HOSTNAME}/...` to find per-server overrides, but `$HOSTNAME` resolves to the machine's actual hostname (e.g. `ip-192-168-0-11`), not the repo's logical `s1`/`s2`/`s3` names — so the override mechanism silently never matched before this was discovered. Do not rely on plain `sudo -u isucon bash ./deploy.sh` to pick up `s1`/`s2`/`s3`-specific files. Until `deploy.sh` itself is fixed (which needs human approval, since it's a deploy script change), invoke it as `sudo -u isucon env HOSTNAME=s1 bash ./deploy.sh` (substituting the correct logical host name) whenever a per-server override file exists. `deploy.sh` also unconditionally runs `sudo systemctl restart mysql`, so on `s1` (which no longer runs MySQL) that silently starts a now-unused local `mysql.service` on every deploy — stop it again afterward (`sudo systemctl stop mysql.service`) if resource cleanliness matters for the next benchmark.
- Known follow-up: after the split relieved `s1`'s CPU pressure, one of 6 post-split benchmark runs failed with `CODE=32` ("a ride was not matched for a long time"), which did not occur pre-split. Working theory: `isuride-matcher.service`'s fixed cadence (one match per `/api/internal/matching` call, every `ISUCON_MATCHING_INTERVAL=0.5`s) was previously paced below its limit by `s1`'s CPU contention, and now that the app can sustain higher throughput, the matcher can't always keep up during bursts. Not yet fixed — flagged as the next candidate.
- pprotein dashboard: SSH tunnel to `localhost:9000`.
- pprotein collection is triggered by the app when bench calls `POST /api/initialize`.
- Netdata parent (all instances stream their metrics here): pprotein host, dashboard at `<pprotein host>:19999`, access via SSH tunnel like pprotein. Configured by `isucon_ansible/roles/general` (`stream.conf.parent.j2` / `stream.conf.child.j2`); the parent is whichever host is in the ansible `pprotein` inventory group.
- App repository on host: `/home/isucon`.
- Shared GitHub repository: `git@github.com:itohdak/isucon14_practice.git`.

## Update Rule

Update this file when:

- A new agent role is added.
- A role's responsibility or ownership changes.
- A new Skill or MCP changes how agents work.
- The benchmark/pprotein/report contract changes.
- The safety boundary changes.

Update the relevant `docs/skills/<role>.md` (separately from this file) whenever a session discovers a durable, reusable operational fact for that role — a new gotcha, a command that stopped working, an access pattern that changed (e.g. a future infrastructure split), or a mistake worth preventing next time. Keep entries concrete (exact commands, exact file paths, what actually happened) rather than generic advice — that's what makes them worth reading instead of re-deriving.
