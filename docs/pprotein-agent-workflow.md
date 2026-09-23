# Pprotein And Agent Workflow

This document describes how humans and Codex share observability during ISUCON practice or contest operations.

## Roles

- pprotein is the shared observability surface for humans and agents.
- In the current ISUCON14 practice environment, pprotein runs on `s2` and listens on port `9000`.
- GitHub stores source, deploy scripts, summaries, and decision history.
- Codex reads reports, logs, and pprotein links, then proposes or applies low-risk improvements.
- Humans stay in the loop for official benchmark execution and risky application logic changes.

## Collection Modes

In the current practice environment, pprotein collection is started by the application when bench calls `POST /api/initialize`. This keeps human and agent observability tied to the actual benchmark lifecycle, including official/manual bench runs.

### Manual

Use this as a fallback when the initialize hook is disabled or unavailable.

1. Human deploys the selected branch.
2. Human opens an SSH tunnel with `ssh -i /home/itohdak/.ssh/isucon.pem -L 9000:127.0.0.1:9000 ubuntu@13.115.244.165`.
3. Human starts pprotein collection from the dashboard or `/api/group/collect` only when automatic collection is unavailable.
4. Human starts the official benchmark.
5. Codex reads the generated reports/logs after the run.
6. Codex records the run in `reports/history/` and suggests the next action.

### Agent

Use this for MCP-only practice loops where Codex needs to collect pprotein outside the application lifecycle.

1. Set `pprotein.enabled: true`.
2. Set `pprotein.collection.mode: agent`.
3. Run `Orchestrator.run_skill("baseline", collect_observability=True)` for MCP-driven baseline reports.
4. Codex calls pprotein collection before the benchmark and records the pprotein dashboard URL in the report.

### Initialize Hook

This is the preferred mode for the current ISUCON14 practice environment.

The application should call pprotein asynchronously during initialization:

```go
go func() {
    if _, err := http.Get("http://s2:9000/api/group/collect"); err != nil {
        log.Printf("failed to communicate with pprotein: %v", err)
    }
}()
```

Rules:

- Never fail `/initialize` because pprotein is unavailable.
- Keep the hook behind an environment flag.
- Prefer this mode when pprotein collection should happen for both human-run and agent-run benchmarks.

## Report Contract

Every benchmark report should include:

- benchmark score and pass/fail status
- pprotein dashboard URL
- pprotein collection status
- nginx route summary sorted by total latency, not only count or max latency
- MySQL slow query summary sorted by total query time, not only single-query latency
- git commit or dirty status
- next action suggestions

pprotein stores collected httplog and slowlog files under `/home/isucon/data/`. For CLI analysis, prefer:

```bash
alp ltsv --config /home/isucon/data/alp.yml --file <httplog> --filters 'Uri matches "^/api/"' --sort sum --reverse
slp my --config /home/isucon/data/slp.yml --file <slowlog> --dump /tmp/latest-slp.yml
slp my --load /tmp/latest-slp.yml --sort sum-query-time --reverse
```

## Safe Automation Boundary

Codex may proceed automatically with:

- report comparison
- slow query and route aggregation
- EXPLAIN checks
- low-risk index additions
- history/report generation

Ask a human before:

- changing matching behavior
- changing `/initialize`
- changing deploy scripts
- adding background jobs
- changing database semantics
- running the official benchmark
