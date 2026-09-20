from __future__ import annotations

from typing import Any, Dict, List

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class NetdataMCP(BaseMCP):
    name = "netdata"

    def get_snapshot(self, host: str, window_seconds: int = 300) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "window_seconds": window_seconds,
                "points": {
                    "cpu": [10, 15, 18, 20, 25],
                    "memory": [60, 63, 65, 64, 66],
                    "disk": [40, 42, 41, 43, 45],
                },
            },
        )

    def get_alerts(self, host: str) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "alerts": [
                    {"name": "cpu_usage", "status": "warning", "value": 78},
                    {"name": "memory_pressure", "status": "ok", "value": 64},
                ],
            },
        )
