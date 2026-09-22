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

Recommended prompts:

- Profiler Agent: "Using the latest benchmark and pprotein artifacts, rank bottlenecks by total API time, total SQL time, and benchmark errors. Do not propose code changes yet."
- Resource Monitor Agent: "For the benchmark run that just finished, report per-host CPU/load/memory/disk from the Netdata parent and state whether any instance was resource-bound during the run."
- App Understanding Agent: "For the top candidate APIs, identify ISUCON14 rule risks and invariants that must not break."
- SQL Agent: "Run `slp --sort sum-query-time --reverse` (or an equivalent full aggregation) to get the complete ranked table of query shapes by total Query_time — not a narrative summary. Report the top 10-15 rows verbatim in your findings. Then inspect schema/index/query patterns for those candidates and suggest low-risk database-side improvements. If you flag any query outside the top 10-15 by total time for a different reason (e.g. high per-call/max latency, or a known risk area), say so explicitly and justify it separately from the total-time ranking, rather than blending it into the same list without distinction."

Codex should continue useful local work while these agents run, such as checking git status, reading the latest report, or preparing the benchmark context.

Codex should continue useful local work while these agents run, such as checking git status, reading the latest report, or preparing the benchmark context.

### When Implementation Can Be Delegated

Spawn an Implementer Agent only when all of these are true:

- The hypothesis has already been chosen.
- The file ownership is narrow and explicit.
- The patch can be bounded to one responsibility.
- The work does not require immediate back-and-forth with production logs.

Do not delegate implementation when the next step is tightly coupled to live deploy/debug feedback.
In that case Codex may implement directly, but the report must explain why.

### Verification

Verification can be handled by a Verifier Agent when it can run independently from ongoing analysis.
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

After every benchmark-backed change, Recorder Agent or Codex must update:

- an iteration report under `reports/iterations/`
- `MILESTONES.md` when the overall status changes
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
| Recorder Agent | yes | Wrote this report and updated milestones. |
```

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
- Documentation/report changes: `docs/`, `reports/`, `MILESTONES.md`, `AGENTS.md`

## Safety Boundaries

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
- Splitting web/app/db roles across instances.
- Adding background workers.
- Deleting data or resetting git state.
- Running destructive commands.
- Exposing pprotein or internal services publicly.

## Skill And MCP Mapping

| Agent | Useful Skills | Useful MCPs |
| --- | --- | --- |
| Profiler Agent | `baseline`, `monitor`, `trace_analysis`, `analyze_iteration` | `BenchmarkMCP`, `PproteinMCP`, `LogsMCP`, `MySQLMCP`, `NetdataMCP` |
| Resource Monitor Agent | `monitor`, `baseline` | `NetdataMCP` |
| App Understanding Agent | `trace_analysis`, `analyze_iteration` | `FilesystemMCP`, `LogsMCP`, `HistoryMCP` |
| SQL Agent | `sql_tune`, `trace_analysis` | `MySQLMCP`, `LogsMCP` |
| Implementer Agent | `deploy` after patch review | `FilesystemMCP`, `GitMCP`, `ShellMCP`, `DeployMCP` |
| Verifier Agent | `baseline`, `deploy`, `analyze_iteration` | `BenchmarkMCP`, `DeployMCP`, `LogsMCP`, `PproteinMCP`, `GitMCP` |
| Recorder Agent | `record_improvement` | `HistoryMCP`, `IterationMCP`, `GitMCP` |

## Current Environment Notes

- App host: `s1`, private `192.168.0.11`, public `13.230.132.249`.
- Bench and pprotein host: `s2`, private `192.168.0.12`, public `35.78.44.172`.
- DB host: `s3`, private `192.168.0.13`, public `18.176.6.65` — dedicated MySQL host, split from `s1` on 2026-09-23 after the Resource Monitor Agent found `s1` CPU-bound (mysqld averaging ~97.7% CPU, saturating one of `s1`'s 2 vCPUs) during a valid benchmark run. Provisioned via a CloudFormation update to the existing `isucon14` stack, which already had unused `Instance3`/`InstanceIP3` resources defined (see `reports/iterations/` for the exact iteration). Only `mysql.service` runs there; `isuride-go.service`, `isuride-matcher.service`, `isuride-payment_mock.service`, and `nginx.service` are stopped and disabled on it.
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
