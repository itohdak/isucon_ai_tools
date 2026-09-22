# isucon_ai_tools

This project provides a minimal, enterprise-friendly structure for building AI-assisted ISUCON tooling.

The design intentionally separates:

- Skills: safe workflow definitions and decision logic
- MCP servers: external execution interfaces like benchmark, MySQL, logs, and Netdata
- Agents: orchestrators that decide which skill to execute

## Quick start

```bash
python -m unittest discover -s tests -v
```

## High-level structure

- `agents/`: orchestration and specialized agents
- `skills/`: YAML definitions for operational workflows
- `mcp/`: focused tool servers for external systems
- `policies/`: guardrails and rule definitions
- `tests/`: automated verification
