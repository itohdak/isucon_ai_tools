from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult
from isucon_ai_tools.policies.guardrails import Guardrails


class FilesystemMCP(BaseMCP):
    name = "filesystem"

    def __init__(self, config: Dict[str, Any] | None = None, guardrails: Guardrails | None = None):
        super().__init__(config=config)
        self.guardrails = guardrails or Guardrails()

    def read_file(self, path: str) -> ToolResult:
        file_path = Path(path)
        if not file_path.exists():
            return ToolResult(status="error", message=f"File not found: {path}")
        return ToolResult(status="ok", data={"path": path, "content": file_path.read_text()})

    def write_file(self, path: str, content: str) -> ToolResult:
        validation_error = self.guardrails.validate_path(path)
        if validation_error:
            return ToolResult(status="error", data={"path": path}, message=validation_error)

        file_path = Path(path)
        backup_path = None
        if self.guardrails.require_backup_before_write and file_path.exists():
            backup_path = file_path.with_suffix(file_path.suffix + ".bak")
            backup_path.write_text(file_path.read_text())

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return ToolResult(
            status="ok",
            data={
                "path": path,
                "bytes_written": len(content),
                "backup_path": str(backup_path) if backup_path else None,
            },
        )

    def diff(self, path: str) -> ToolResult:
        return ToolResult(status="ok", data={"path": path, "diff": "+init"})
