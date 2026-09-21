# ISUCON AI Tools Architecture

Last updated: 2026-09-21

This document is the map of the current Codex/agent-side architecture. Update it whenever Skills, MCPs, or external observability flows change.

## Overview

```mermaid
flowchart TB
  User[Human operator] --> Codex[Codex]
  Codex --> Orchestrator[Orchestrator]
  Orchestrator --> Registry[SkillRegistry]
  Orchestrator --> Guardrails[Guardrails]

  Registry --> BaselineSkill[baseline]
  Registry --> MonitorSkill[monitor]
  Registry --> TraceSkill[trace_analysis]
  Registry --> SqlSkill[sql_tune]
  Registry --> RecordSkill[record_improvement]
  Registry --> DeploySkill[deploy]
  Registry --> AnalyzeSkill[analyze_iteration]
  Registry --> RollbackSkill[rollback]

  Orchestrator --> BenchmarkMCP[BenchmarkMCP]
  Orchestrator --> NetdataMCP[NetdataMCP]
  Orchestrator --> MySQLMCP[MySQLMCP]
  Orchestrator --> LogsMCP[LogsMCP]
  Orchestrator --> GitMCP[GitMCP]
  Orchestrator --> FilesystemMCP[FilesystemMCP]
  Orchestrator --> ShellMCP[ShellMCP]
  Orchestrator --> DeployMCP[DeployMCP]
  Orchestrator --> IterationMCP[IterationMCP]
  Orchestrator --> PproteinMCP[PproteinMCP]
  Orchestrator --> APMMCP[APMMCP]
  Orchestrator --> HistoryMCP[HistoryMCP]

  Guardrails --> GitMCP
  Guardrails --> FilesystemMCP
  Guardrails --> ShellMCP
  Guardrails --> DeployMCP

  BenchmarkMCP --> BenchHost[Bench host]
  NetdataMCP --> AppHost[App host via SSH]
  MySQLMCP --> AppHost
  LogsMCP --> AppHost
  GitMCP --> AppHost
  DeployMCP --> AppHost
  PproteinMCP --> Pprotein[pprotein server]

  IterationMCP --> Reports[reports/]
  HistoryMCP --> Reports
  Orchestrator --> Reports
  Reports --> GitHub[GitHub repository]
```

## Skill Flow

```mermaid
sequenceDiagram
  participant Human
  participant Codex
  participant Orchestrator
  participant MCPs
  participant Reports
  participant AppHost
  participant Pprotein

  Human->>Codex: Ask for baseline or improvement loop
  Codex->>Orchestrator: run_skill(...)
  AppHost->>Pprotein: collect when bench calls /api/initialize
  Orchestrator->>Pprotein: collect only for MCP-only baseline runs
  Orchestrator->>MCPs: benchmark, logs, mysql, git, resources
  MCPs->>AppHost: SSH / MySQL / journalctl / git / deploy
  MCPs-->>Orchestrator: ToolResult
  Orchestrator->>Reports: write baseline/history/iteration files
  Codex->>Human: summary and next action
```

## Skills

| Skill | Purpose | Main MCPs |
| --- | --- | --- |
| `baseline` | Run or record benchmark state and collect current system state. | `BenchmarkMCP`, `MySQLMCP`, `LogsMCP`, `GitMCP`, `NetdataMCP`, `PproteinMCP` |
| `monitor` | Collect resource and APM-style telemetry. | `NetdataMCP`, `APMMCP` |
| `trace_analysis` | Summarize traces and DB hotspots. Currently APM data is mock-like. | `APMMCP`, `MySQLMCP` |
| `sql_tune` | Inspect slow queries and SQL/index candidates. | `MySQLMCP`, `LogsMCP` |
| `record_improvement` | Persist hypothesis, evidence, score delta, reports, and commit. | `HistoryMCP` |
| `deploy` | Run deploy command, preflight, health checks, and failure log collection. | `DeployMCP`, `GitMCP`, `ShellMCP` |
| `analyze_iteration` | Compare before/after reports and suggest next bottleneck area. | `IterationMCP` |
| `rollback` | Placeholder for explicit rollback workflows. | `GitMCP`, `FilesystemMCP`, `ShellMCP`, `HistoryMCP` |

## MCPs

| MCP | Current Role | Notes |
| --- | --- | --- |
| `BenchmarkMCP` | Runs the ISUCON benchmark on the bench host and parses score/pass/error counts. | Real SSH-backed path exists. |
| `NetdataMCP` | Collects lightweight resource snapshots. | Despite the name, currently uses `uptime`, `free`, `df`, and `ps`; Netdata is not installed. |
| `MySQLMCP` | Reads slow query log, EXPLAINs queries, and checks processlist. | SSH-backed `sudo mysql` flow. |
| `LogsMCP` | Reads recent journal logs and summarizes Nginx LTSV routes. | Used in baseline reports. |
| `GitMCP` | Reads status/diff and guarded restore. | Guardrails enforce repo path and restore path constraints. |
| `FilesystemMCP` | Guarded local file writes with backup. | Used for safe file operations inside allowlist. |
| `ShellMCP` | Guarded local shell command execution. | Denies configured dangerous commands. |
| `DeployMCP` | Runs preflight, deploy command, service health checks, and failure log collection. | Full deploy requires clean git unless `allow_dirty=True`. |
| `IterationMCP` | Compares benchmark reports and generates iteration reports. | Outputs Markdown under `reports/iterations/`. |
| `PproteinMCP` | Integrates shared observability collection/dashboard links. | Current practice default is initialize hook mode; the app triggers pprotein when bench calls `/api/initialize`. |
| `APMMCP` | Placeholder APM data provider. | Real route latency currently comes from Nginx logs, not APM. |
| `HistoryMCP` | Persists improvement records and Markdown summaries. | Stores JSONL and Markdown under `reports/`. |

## External Systems

| System | Role |
| --- | --- |
| App host `s1` | Runs ISUCON app, MySQL, Nginx, services, git repo. |
| Bench host `s2` | Runs official/practice benchmark command. |
| pprotein host `s2` | Shared dashboard for pprof, httplog, slowlog, and future human/agent collaboration. It is not exposed publicly; use SSH tunnel `localhost:9000`. |
| GitHub repo | Shared source, deploy state, docs, reports, and decision history. |

## Benchmark Collection Policy

- The primary trigger is the Go application's `POST /api/initialize` handler.
- The handler starts pprotein collection asynchronously and best-effort.
- This applies to both human-run and Codex-run benchmarks because both go through bench initialization.
- `PproteinMCP.collect()` remains available for MCP-only baseline runs that do not exercise `/api/initialize`.

## Update Rule

Update this file when any of these change:

- A Skill is added, removed, renamed, or changes its main MCPs.
- An MCP is added, removed, renamed, or changes from mock to real behavior.
- Guardrails start protecting a new operation type.
- pprotein/manual/agent collection flow changes.
- Reports move location or change schema.
