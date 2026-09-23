# isucon_ai_tools

Operational notes and agent instructions for AI-assisted ISUCON tuning. Start with `AGENTS.md` — it defines the agent roles used during an improvement loop and links to everything else.

## Where Things Live

- `AGENTS.md` — the entry point: agent roles, the improvement loop, safety boundaries, and pointers to everything below.
- `docs/skills/<role>.md` — concrete, verified operational instructions per agent role (Profiler, Resource Monitor, App Understanding, SQL, Implementer, Verifier, Recorder). Read the relevant one before acting as that role.
- `docs/` (top level) — standing references: startup checklist, resource-scaling policy, MySQL operations tips, the ISUCON14 improvement approach and known invariants.
- `reports/summary/<contest>.md` (e.g. `reports/summary/isucon13.md`) — the running, per-contest project history and current status. Nothing reads this automatically; check it manually at the start of a session for context. See `AGENTS.md`'s "Per-Contest Summary Reports" section for the convention.
- `config/<contest>.yaml` (e.g. `config/isucon13.yaml`, `config/isucon14.yaml`) — environment facts (hosts, credentials, benchmark command) for that contest.
- `reports/` — per-iteration reports (`reports/iterations/`), per-change evidence (`reports/history/`), and the per-contest summaries above.
- `archive/` — an earlier Python Skills/MCP/Agents package that turned out not to reflect how this project actually operates (see `archive/NOTE.md`), plus the retired `MILESTONES.md` (see `archive/MILESTONES.md`, superseded by `reports/summary/<contest>.md`). Kept for reference, not in active use.

## How This Actually Works

There is no bespoke tooling layer in active use. An ISUCON improvement loop works by dispatching general-purpose subagents (with real shell/SSH access) with a task prompt that tells them which `docs/skills/<role>.md` to read first, then acting on real evidence gathered directly from the live environment (SSH, `mysql`, `slp`/`alp`, Netdata's HTTP API, `git`, AWS/Ansible CLIs). See `AGENTS.md`'s Sub-Agent Execution Protocol for the exact loop.
