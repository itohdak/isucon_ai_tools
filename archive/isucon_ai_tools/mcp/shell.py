from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult
from isucon_ai_tools.policies.guardrails import Guardrails


class ShellMCP(BaseMCP):
    name = "shell"

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        runner: Any | None = None,
        guardrails: Guardrails | None = None,
    ):
        super().__init__(config=config)
        self.runner = runner or subprocess.run
        self.guardrails = guardrails or Guardrails()

    def run(self, command: str, cwd: str | None = None, timeout_seconds: int = 30) -> ToolResult:
        command_error = self.guardrails.validate_command(command)
        if command_error:
            return ToolResult(status="error", data={"command": command}, message=command_error)

        if cwd is not None:
            path_error = self.guardrails.validate_path(cwd)
            if path_error:
                return ToolResult(status="error", data={"command": command, "cwd": cwd}, message=path_error)

        completed = self.runner(
            command,
            shell=True,
            cwd=str(Path(cwd)) if cwd else None,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        return ToolResult(
            status="ok" if completed.returncode == 0 else "error",
            data={
                "command": command,
                "cwd": cwd,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )
