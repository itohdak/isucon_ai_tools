# Why This Is Archived

This directory holds the original `isucon-ai-tools` Python package (Skills/MCP/Agents/tests, see its own `README.md` for what it was designed to be) and its supporting files (`pyproject.toml`, `run_demo.py`, `prompt.md`, `prompt_ja.md`).

**Correction (this note originally overstated its case — see below for what actually happened):** this code *was* genuinely used for real ISUCON improvement work early in the project. On 2026-09-21, `Orchestrator`/`BenchmarkMCP`/`GitMCP`/`MySQLMCP`/`HistoryMCP`/`IterationMCP` produced real baseline reports (`baseline-isucon14-*.json`, containing genuine remote-host benchmark output) and tracked several accepted index changes with real before/after evidence (e.g. `reports/history/ride-statuses-indexes-20260921.md`: commit `b1bfb60`, score 673→1297, real `EXPLAIN` output) — these files were never touched again after that one session and were moved into this `archive/reports/` directory on 2026-09-23, alongside this package. There is no packaged CLI for this (no `console_scripts` in `pyproject.toml`, and `run_demo.py` only exercises fake `localhost`/mock scenarios) — those real Sept 21 runs were almost certainly ad-hoc `python3 -c "..."` invocations of the classes directly, the same pattern used to verify this package's current state below, not a maintained CLI tool.

What changed since then: across the entire multi-day tuning session that followed (index/query changes, an infrastructure split moving MySQL to a dedicated host, matcher throughput tuning, etc.), every real interaction with the live environment went through direct Bash/SSH commands inside Agent-tool-dispatched subagents instead — the `Orchestrator`/MCP layer was not touched again, and (see below) parts of it silently drifted out of sync with the infrastructure changes made during that period.

An investigation confirmed why it was safe to stop relying on this layer:

- `mcp/apm.py` is fully hardcoded mock data (fake routes that don't even exist in the target app).
- `mcp/netdata.py` is real, correctly-implemented code, but is configured to hit a private VPC IP that is unreachable from the operator machine — verified by actually running it (every metric call timed out).
- `mcp/mysql.py` is real SSH-based code, but is hardcoded to query the app host. After the app's MySQL was split onto a dedicated host mid-session, this MCP was never updated and would now silently read a stale, no-longer-updated log instead of erroring.
- `mcp/git.py` (and structurally similar `benchmark.py`/`deploy.py`/`logs.py`) were verified genuinely functional, but duplicated what the actual working process already did directly over SSH.
- `agents/orchestrator.py` and `skills/registry.py` are a thin catalog/dispatch layer over the above MCPs; they worked when the MCPs underneath them worked (Sept 21), and would inherit the same staleness now.

The real, currently-accurate operational knowledge for each ISUCON agent role now lives in `docs/skills/<role>.md` at the repository root, referenced from `AGENTS.md`. Those files are plain instructions (commands, access patterns, gotchas) for a general-purpose subagent with shell/SSH access — no bespoke Python tooling required to maintain them.

## If You Want To Revive This

The code itself isn't deleted, only moved. If a future session wants a real MCP layer again: fix `mcp/netdata.py` to go through an SSH-reachable path (see `docs/skills/resource-monitor-agent.md` for the pattern that actually works), fix `mcp/mysql.py` to target the configured DB host instead of a hardcoded app host, and replace `mcp/apm.py` with something real or remove it. Until that work happens, treat everything under this directory as reference/prior-art, not as something to invoke.
