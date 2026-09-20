from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class FilesystemMCP(BaseMCP):
    name = "filesystem"

    def read_file(self, path: str) -> ToolResult:
        file_path = Path(path)
        if not file_path.exists():
            return ToolResult(status="error", message=f"File not found: {path}")
        return ToolResult(status="ok", data={"path": path, "content": file_path.read_text()})

    def write_file(self, path: str, content: str) -> ToolResult:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return ToolResult(status="ok", data={"path": path, "bytes_written": len(content)})

    def diff(self, path: str) -> ToolResult:
        return ToolResult(status="ok", data={"path": path, "diff": "+init"})
