from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, List

import yaml

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult
from isucon_ai_tools.policies.guardrails import Guardrails


class GitMCP(BaseMCP):
    name = "git"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        config_path: str | None = None,
        runner: Any | None = None,
        guardrails: Guardrails | None = None,
    ):
        if config is None and config_path is not None:
            config = yaml.safe_load(Path(config_path).read_text()) or {}
        super().__init__(config=config)
        self.runner = runner or subprocess.run
        self.guardrails = guardrails or Guardrails()

    def diff(self, repo_path: str) -> ToolResult:
        if self._has_real_git_config():
            completed = self._run_on_app_host(f"cd {shlex.quote(repo_path)} && sudo -u isucon git diff --stat && sudo -u isucon git diff --")
            return ToolResult(
                status="ok" if completed.returncode == 0 else "error",
                data={
                    "repo_path": repo_path,
                    "diff": completed.stdout,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr,
                },
            )

        return ToolResult(
            status="ok",
            data={
                "repo_path": repo_path,
                "diff": [
                    {"file": "app.go", "lines": ["+cache.Set(...)", "-db.Query(...) "]},
                ],
            },
        )

    def status(self, repo_path: str) -> ToolResult:
        if self._has_real_git_config():
            completed = self._run_on_app_host(f"cd {shlex.quote(repo_path)} && sudo -u isucon git status --short")
            return ToolResult(
                status="ok" if completed.returncode == 0 else "error",
                data={
                    "repo_path": repo_path,
                    "status": completed.stdout.splitlines(),
                    "returncode": completed.returncode,
                    "stderr": completed.stderr,
                },
            )
        return ToolResult(status="ok", data={"repo_path": repo_path, "status": []})

    def restore(self, repo_path: str, paths: List[str] | None = None) -> ToolResult:
        validation_error = self.guardrails.validate_path(repo_path)
        if validation_error:
            return ToolResult(status="error", data={"repo_path": repo_path}, message=validation_error)
        if self._has_real_git_config():
            if not paths:
                return ToolResult(status="error", data={"repo_path": repo_path}, message="restore requires explicit paths")
            for path in paths:
                if path.startswith("/") or ".." in Path(path).parts:
                    return ToolResult(
                        status="error",
                        data={"repo_path": repo_path, "paths": paths},
                        message=f"restore path must be repo-relative and cannot traverse parents: {path}",
                    )
            quoted_paths = " ".join(shlex.quote(path) for path in paths)
            remote_command = f"cd {shlex.quote(repo_path)} && sudo -u isucon git restore -- {quoted_paths}"
            command_error = self.guardrails.validate_command(remote_command)
            if command_error:
                return ToolResult(status="error", data={"repo_path": repo_path, "paths": paths}, message=command_error)
            completed = self._run_on_app_host(remote_command)
            return ToolResult(
                status="ok" if completed.returncode == 0 else "error",
                data={
                    "repo_path": repo_path,
                    "paths": paths,
                    "restored": completed.returncode == 0,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr,
                },
            )
        return ToolResult(status="ok", data={"repo_path": repo_path, "restored": True})

    def _has_real_git_config(self) -> bool:
        return all(key in self.config for key in ("ssh", "hosts", "git"))

    def _run_on_app_host(self, remote_command: str) -> subprocess.CompletedProcess[str]:
        ssh_config = self.config["ssh"]
        app_host = self.config["hosts"]["app"]
        ssh_command = [
            "ssh",
            "-i",
            ssh_config["private_key_path"],
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            f"{ssh_config['user']}@{app_host['public_ip']}",
            remote_command,
        ]
        return self.runner(ssh_command, text=True, capture_output=True, timeout=30)
