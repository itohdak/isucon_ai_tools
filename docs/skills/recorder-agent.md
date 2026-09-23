# Recorder Agent Skill

Persist the decision history so future iterations (and future sessions, which do not automatically read anything — see below) can build on it instead of re-deriving it.

## Files To Update, Every Benchmark-Backed Iteration

1. A new iteration report at `reports/iterations/iteration-YYYYMMDD-HHMMSS.md`, following the Reporting Contract in `AGENTS.md` (`Agents used`, `Hypothesis`, `Evidence`, `Change`, `Verification`, `Benchmark result`, `pprotein artifacts`, `Commit`, `Next candidate`).
2. `reports/summary/<contest>.md` (e.g. `reports/summary/isucon13.md` — see AGENTS.md's "Per-Contest Summary Reports" section; this replaced `MILESTONES.md`, now frozen at `archive/MILESTONES.md`) — append a new dated bullet, and update *both*:
   - The narrative bullet describing what changed.
   - The `Latest app optimization commit:` / `Latest verified benchmark:` / `Latest iteration report:` pointer lines.
   A past run of this skill (back when this lived in `MILESTONES.md`) updated the narrative bullets but forgot the pointer lines, leaving `Latest iteration report:` pointing at a stale file for several iterations — check both every time, not just one.
3. `docs/agent-architecture.md` or `AGENTS.md` itself, only when the agent process changes (new role, new skill file, changed report contract).
4. `docs/isucon14-improvement-approach.md`'s "Known Fixed Issue" / guardrails sections, when a genuinely new invariant or gotcha is discovered (not every iteration — only durable, reusable findings).

## Nothing Is Read Automatically

There is no `CLAUDE.md` in this repo (or `isucon14_practice`), and nothing in `AGENTS.md` currently instructs a future session to read `reports/summary/<contest>.md` before starting work — it is a write-only convention right now. A future Codex/Claude session will only benefit from these records if it (or the human) chooses to read them. Do not assume continuity across sessions; write reports as if the next reader has zero prior context beyond what's on disk.

## Git Hygiene

- `isucon_ai_tools` and `isucon14_practice` (and `isucon_ansible`, when touched) are **separate git repositories** — commit each one separately, and say which repo a commit belongs to in the iteration report.
- Before staging, check `git status --short` for pre-existing unrelated uncommitted changes (this has happened more than once in this project) and stage only the files you intend to commit — never a blanket `git add -A`/`git add .` in these repos.
- `webapp/go` is covered by a `go/` pattern in `.gitignore` that appears to be a leftover from ignoring a Go module cache directory elsewhere, but it does not block committing already-tracked files there (only warns) — `git add <specific-file>` under `webapp/go/` still works despite the warning.
