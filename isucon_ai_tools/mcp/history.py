from __future__ import annotations

from typing import Any, Dict, List

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class HistoryMCP(BaseMCP):
    name = "history"

    def record_run(self, run_id: str, before_score: int, after_score: int, hypothesis: str, changed_files: List[str]) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "run_id": run_id,
                "before_score": before_score,
                "after_score": after_score,
                "hypothesis": hypothesis,
                "changed_files": changed_files,
            },
        )

    def list_runs(self) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "runs": [
                    {"run_id": "r1", "before_score": 1200, "after_score": 1500, "hypothesis": "index optimization"},
                    {"run_id": "r2", "before_score": 1500, "after_score": 1700, "hypothesis": "endpoint cache"},
                ]
            },
        )
