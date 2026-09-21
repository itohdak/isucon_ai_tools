from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import yaml

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult
from isucon_ai_tools.policies.guardrails import Guardrails


class DeployMCP(BaseMCP):
    name = "deploy"

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        config_path: str | None = None,
        runner: Any | None = None,
        guardrails: Guardrails | None = None,
    ):
        if config is None and config_path is not None:
            config = yaml.safe_load(Path(config_path).read_text()) or {}
        super().__init__(config=config)
        self.runner = runner or subprocess.run
        self.guardrails = guardrails or Guardrails()

    def deploy(self, host: str = "app", allow_dirty: bool = False, dry_run: bool = False) -> ToolResult:
        if not self._has_real_deploy_config():
            return ToolResult(
                status="ok",
                data={
                    "host": host,
                    "deployed": True,
                    "health": "ok",
                    "mock": True,
                    "dry_run": dry_run,
                },
            )

        repo_path = self.config["git"]["app_repo_path"]
        path_error = self.guardrails.validate_path(repo_path)
        if path_error:
            return ToolResult(status="error", data={"repo_path": repo_path}, message=path_error)

        status_result = self._git_status(repo_path)
        if status_result.returncode != 0:
            return ToolResult(
                status="error",
                data=self._completed_data(status_result, {"repo_path": repo_path}),
                message="Failed to inspect git status before deploy.",
            )
        dirty_lines = [line for line in status_result.stdout.splitlines() if line.strip()]
        if dirty_lines and not allow_dirty:
            return ToolResult(
                status="error",
                data={"repo_path": repo_path, "dirty_files": dirty_lines},
                message="Deploy requires a clean git working tree unless allow_dirty=True.",
            )

        deploy_command = self._deploy_command(repo_path)
        command_error = self.guardrails.validate_command(deploy_command)
        if command_error:
            return ToolResult(status="error", data={"command": deploy_command}, message=command_error)

        preflight = self._preflight(repo_path=repo_path, deploy_command=deploy_command)
        if dry_run:
            return ToolResult(
                status=preflight["status"],
                data={
                    "host": host,
                    "repo_path": repo_path,
                    "allow_dirty": allow_dirty,
                    "dry_run": True,
                    "dirty_files": dirty_lines,
                    "preflight": preflight,
                },
                message="Deploy preflight completed." if preflight["status"] == "ok" else "Deploy preflight failed.",
            )
        if preflight["status"] != "ok":
            return ToolResult(
                status="error",
                data={
                    "host": host,
                    "repo_path": repo_path,
                    "allow_dirty": allow_dirty,
                    "dry_run": False,
                    "dirty_files": dirty_lines,
                    "preflight": preflight,
                },
                message="Deploy preflight failed.",
            )

        deploy_result = self._run_on_app_host(deploy_command, timeout=self._deploy_timeout())
        health = self._check_health()
        logs = None
        status = "ok" if deploy_result.returncode == 0 and health["status"] == "ok" else "error"
        if status == "error":
            logs = self._collect_failure_logs()

        return ToolResult(
            status=status,
            data={
                "host": host,
                "repo_path": repo_path,
                "allow_dirty": allow_dirty,
                "dry_run": False,
                "dirty_files": dirty_lines,
                "preflight": preflight,
                "deploy": self._completed_data(deploy_result, {"command": deploy_command}),
                "health": health,
                "failure_logs": logs,
            },
            message="Deploy completed." if status == "ok" else "Deploy failed or health check failed.",
        )

    def _has_real_deploy_config(self) -> bool:
        return all(key in self.config for key in ("ssh", "hosts", "git"))

    def _git_status(self, repo_path: str) -> subprocess.CompletedProcess[str]:
        command = f"cd {shlex.quote(repo_path)} && sudo -u isucon git status --short"
        return self._run_on_app_host(command, timeout=30)

    def _deploy_command(self, repo_path: str) -> str:
        configured = self.config.get("deploy", {}).get("command")
        if configured:
            return str(configured)
        return f"cd {shlex.quote(repo_path)}/common && sudo -u isucon bash ./deploy.sh"

    def _deploy_timeout(self) -> int:
        return int(self.config.get("deploy", {}).get("timeout_seconds", 180))

    def _preflight(self, repo_path: str, deploy_command: str) -> Dict[str, Any]:
        deploy_script = self.config.get("deploy", {}).get("script_path", f"{repo_path}/common/deploy.sh")
        checks = []
        for name, command in [
            ("deploy_script_exists", f"test -x {shlex.quote(deploy_script)}"),
            ("deploy_script_syntax", f"bash -n {shlex.quote(deploy_script)}"),
        ]:
            completed = self._run_on_app_host(command, timeout=30)
            checks.append(
                {
                    "name": name,
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                }
            )
        command_safe = self.guardrails.validate_command(deploy_command) is None
        checks.append(
            {
                "name": "deploy_command_allowed",
                "command": deploy_command,
                "returncode": 0 if command_safe else 1,
                "stdout": "",
                "stderr": "" if command_safe else "Deploy command rejected by guardrails.",
            }
        )
        health = self._check_health()
        ok = all(check["returncode"] == 0 for check in checks) and health["status"] == "ok"
        return {
            "status": "ok" if ok else "error",
            "checks": checks,
            "health": health,
        }

    def _check_health(self) -> Dict[str, Any]:
        services = self.config.get("deploy", {}).get("health_services") or self.config.get("services", {}).get("app", [])
        if not services:
            return {"status": "ok", "services": []}

        service_args = " ".join(shlex.quote(service) for service in services)
        command = f"systemctl is-active {service_args}"
        completed = self._run_on_app_host(command, timeout=30)
        states = completed.stdout.splitlines()
        service_results = [
            {"service": service, "state": states[index] if index < len(states) else "unknown"}
            for index, service in enumerate(services)
        ]
        healthy = completed.returncode == 0 and all(item["state"] == "active" for item in service_results)
        return {
            "status": "ok" if healthy else "error",
            "services": service_results,
            "returncode": completed.returncode,
            "stderr": completed.stderr,
        }

    def _collect_failure_logs(self) -> Dict[str, Any]:
        units = self.config.get("logs", {}).get("app_journal_units", [])
        unit_args = " ".join(f"-u {shlex.quote(unit)}" for unit in units)
        command = f"sudo journalctl {unit_args} -n 80 --no-pager"
        completed = self._run_on_app_host(command, timeout=30)
        return self._completed_data(completed, {"command": command})

    def _run_on_app_host(self, remote_command: str, timeout: int) -> subprocess.CompletedProcess[str]:
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
        return self.runner(ssh_command, text=True, capture_output=True, timeout=timeout)

    def _completed_data(
        self,
        completed: subprocess.CompletedProcess[str],
        extra: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        return {
            **(extra or {}),
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
