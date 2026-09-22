from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class HistoryMCP(BaseMCP):
    name = "history"

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        storage_path: str | None = None,
        report_dir: str | None = None,
    ):
        super().__init__(config=config)
        history_config = self.config.get("history", {})
        self.storage_path = Path(storage_path or history_config.get("storage_path", "reports/history.jsonl"))
        self.report_dir = Path(report_dir or history_config.get("report_dir", "reports/history"))

    def record_run(
        self,
        run_id: str,
        before_score: int,
        after_score: int,
        hypothesis: str,
        changed_files: List[str],
        evidence: Dict[str, Any] | None = None,
        rollback_status: str = "not_needed",
        before_report: str | None = None,
        after_report: str | None = None,
        commit: str | None = None,
    ) -> ToolResult:
        record = {
            "run_id": run_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "before_score": before_score,
            "after_score": after_score,
            "delta": after_score - before_score,
            "hypothesis": hypothesis,
            "changed_files": changed_files,
            "evidence": evidence or {},
            "rollback_status": rollback_status,
            "before_report": before_report,
            "after_report": after_report,
            "commit": commit,
        }
        self._append_record(record)
        markdown_path = self._write_markdown_report(record)
        return ToolResult(
            status="ok",
            data={
                **record,
                "storage_path": str(self.storage_path),
                "markdown_path": str(markdown_path),
            },
        )

    def list_runs(self) -> ToolResult:
        records = self._read_records()
        return ToolResult(
            status="ok",
            data={
                "storage_path": str(self.storage_path),
                "runs": records,
            },
        )

    def generate_summary(self) -> ToolResult:
        records = self._read_records()
        total_delta = sum(int(record.get("delta", 0)) for record in records)
        best = max(records, key=lambda record: int(record.get("after_score", 0)), default=None)
        return ToolResult(
            status="ok",
            data={
                "run_count": len(records),
                "total_delta": total_delta,
                "best_run": best,
                "storage_path": str(self.storage_path),
            },
        )

    def _append_record(self, record: Dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("a", encoding="utf-8") as history_file:
            history_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _read_records(self) -> List[Dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        records = []
        for line in self.storage_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            records.append(json.loads(line))
        return records

    def _write_markdown_report(self, record: Dict[str, Any]) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        path = self.report_dir / f"{record['run_id']}.md"
        lines = [
            f"# {record['run_id']}",
            "",
            f"- Recorded at: `{record['recorded_at']}`",
            f"- Before score: `{record['before_score']}`",
            f"- After score: `{record['after_score']}`",
            f"- Delta: `{record['delta']}`",
            f"- Rollback status: `{record['rollback_status']}`",
            f"- Commit: `{record['commit'] or ''}`",
            f"- Before report: `{record['before_report'] or ''}`",
            f"- After report: `{record['after_report'] or ''}`",
            "",
            "## Hypothesis",
            "",
            record["hypothesis"],
            "",
            "## Changed Files",
            "",
            *[f"- `{file}`" for file in record["changed_files"]],
            "",
            "## Evidence",
            "",
            "```json",
            json.dumps(record["evidence"], ensure_ascii=False, indent=2, sort_keys=True),
            "```",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
