from __future__ import annotations

from typing import Any, Dict, List

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class BenchmarkMCP(BaseMCP):
    name = "benchmark"

    def run(self, host: str, command: str, capture_logs: bool = True) -> ToolResult:
        """Simulated benchmark runner; replace with actual remote execution in production."""
        score = 1200
        if "bench" in command.lower():
            score = 1500
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "command": command,
                "score": score,
                "capture_logs": capture_logs,
                "timestamp": "2026-08-31T00:00:00Z",
            },
            message="Benchmark completed.",
        )

    def history(self, host: str) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "host": host,
                "history": [
                    {"score": 1200, "note": "baseline"},
                    {"score": 1500, "note": "after t1"},
                ],
            },
        )
