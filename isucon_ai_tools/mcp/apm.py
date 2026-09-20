from __future__ import annotations

from typing import Any, Dict, List

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class APMMCP(BaseMCP):
    name = "apm"

    def get_services(self, host: str) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "services": [
                    {"name": "web", "latency_ms_p95": 260, "error_rate": 0.03},
                    {"name": "db", "latency_ms_p95": 180, "error_rate": 0.01},
                    {"name": "cache", "latency_ms_p95": 40, "error_rate": 0.00},
                ],
            },
        )

    def get_slow_endpoints(self, host: str, limit: int = 10) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "slow_endpoints": [
                    {"route": "/api/users", "p95_ms": 420, "requests": 200},
                    {"route": "/api/orders", "p95_ms": 360, "requests": 140},
                    {"route": "/api/summary", "p95_ms": 280, "requests": 110},
                ][:limit],
            },
        )

    def get_db_hotspots(self, host: str, limit: int = 10) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "db_hotspots": [
                    {"query": "SELECT * FROM orders WHERE user_id = ?", "latency_ms": 180, "count": 230},
                    {"query": "SELECT * FROM users WHERE id = ?", "latency_ms": 140, "count": 410},
                ][:limit],
            },
        )

    def summarize_traces(self, host: str) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "summary": {
                    "most_expensive_span": "db.query",
                    "slowest_route": "/api/users",
                    "root_cause_hypothesis": "transaction holds lock while waiting on external dependency",
                },
            },
        )
