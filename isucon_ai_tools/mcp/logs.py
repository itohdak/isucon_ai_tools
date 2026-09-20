from __future__ import annotations

from typing import Any, List

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class LogsMCP(BaseMCP):
    name = "logs"

    def collect_recent(self, host: str, patterns: List[str]) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "patterns": patterns,
                "lines": [
                    "ERROR: connection timeout",
                    "slow query 180ms",
                    "too many connections",
                ],
            },
        )
