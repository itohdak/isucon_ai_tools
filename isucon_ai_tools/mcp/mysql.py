from __future__ import annotations

from typing import Any, Dict, List

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class MySQLMCP(BaseMCP):
    name = "mysql"

    def get_slow_queries(self, host: str, limit: int = 20) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "slow_queries": [
                    {"query": "SELECT * FROM users WHERE id = ?", "time_ms": 180},
                    {"query": "SELECT * FROM orders WHERE user_id = ?", "time_ms": 120},
                ][:limit],
            },
        )

    def explain_queries(self, host: str, queries: List[str]) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "explain": [
                    {"query": q, "plan": ["table_scan", "index_missing"]} for q in queries
                ],
            },
        )
