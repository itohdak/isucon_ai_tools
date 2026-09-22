# Why This Is Archived

This directory holds the original `isucon-ai-tools` Python package (Skills/MCP/Agents/tests, see its own `README.md` for what it was designed to be) and its supporting files (`pyproject.toml`, `run_demo.py`, `prompt.md`, `prompt_ja.md`).

None of this code has actually been used to run real ISUCON improvement work. Across a full multi-day tuning session (index/query changes, an infrastructure split, matcher throughput tuning, etc.), every real interaction with the live environment — SSH, MySQL, benchmarks, CloudFormation, Ansible, git — went through direct Bash/SSH commands inside Agent-tool-dispatched subagents, never through this package's `Orchestrator`, `SkillRegistry`, or MCP classes.

An investigation confirmed why it was safe to stop relying on this layer:

- `mcp/apm.py` is fully hardcoded mock data (fake routes that don't even exist in the target app).
- `mcp/netdata.py` is real, correctly-implemented code, but is configured to hit a private VPC IP that is unreachable from the operator machine — verified by actually running it (every metric call timed out).
- `mcp/mysql.py` is real SSH-based code, but is hardcoded to query the app host. After the app's MySQL was split onto a dedicated host mid-session, this MCP was never updated and would now silently read a stale, no-longer-updated log instead of erroring.
- `mcp/git.py` (and structurally similar `benchmark.py`/`deploy.py`/`logs.py`) were verified genuinely functional, but duplicated what the actual working process already did directly over SSH.
- `agents/orchestrator.py` and `skills/registry.py` are a thin catalog/dispatch layer over the above MCPs; since the MCPs weren't relied on, neither was this.

The real, currently-accurate operational knowledge for each ISUCON agent role now lives in `docs/skills/<role>.md` at the repository root, referenced from `AGENTS.md`. Those files are plain instructions (commands, access patterns, gotchas) for a general-purpose subagent with shell/SSH access — no bespoke Python tooling required to maintain them.

## If You Want To Revive This

The code itself isn't deleted, only moved. If a future session wants a real MCP layer again: fix `mcp/netdata.py` to go through an SSH-reachable path (see `docs/skills/resource-monitor-agent.md` for the pattern that actually works), fix `mcp/mysql.py` to target the configured DB host instead of a hardcoded app host, and replace `mcp/apm.py` with something real or remove it. Until that work happens, treat everything under this directory as reference/prior-art, not as something to invoke.
