from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any, List

import yaml

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class LogsMCP(BaseMCP):
    name = "logs"

    def __init__(self, config: dict[str, Any] | None = None, config_path: str | None = None, runner: Any | None = None):
        if config is None and config_path is not None:
            config = yaml.safe_load(Path(config_path).read_text()) or {}
        super().__init__(config=config)
        self.runner = runner or subprocess.run

    def collect_recent(self, host: str, patterns: List[str]) -> ToolResult:
        if self._has_real_logs_config():
            return self._collect_remote_recent(host=host, patterns=patterns)

        return ToolResult(
            status="ok",
            data={
                "host": host,
                "patterns": patterns,
                "lines": [
                    "ERROR: connection timeout",
                    "slow query 180ms",
                    "too many connections",
                ],
            },
        )

    def summarize_routes(self, host: str, limit: int = 20) -> ToolResult:
        if not self._has_real_logs_config():
            return ToolResult(status="ok", data={"host": host, "routes": []})

        access_log = self.config["logs"]["nginx_access_log"]
        command = (
            "sudo awk -F'\\t' "
            + shlex.quote(
                "{uri=\"\"; elapsed=0; for(i=1;i<=NF;i++){"
                "if($i ~ /^uri:/){u=$i; sub(/^uri:/,\"\",u); split(u,a,\"?\"); uri=a[1]}"
                "if($i ~ /^apptime:/){v=$i; sub(/^apptime:/,\"\",v); if(v != \"-\" && v != \"\") elapsed=v+0}"
                "if($i ~ /^reqtime:/){v=$i; sub(/^reqtime:/,\"\",v); if(elapsed == 0 && v != \"-\" && v != \"\") elapsed=v+0}"
                "} if(uri != \"\"){count[uri]++; sum[uri]+=elapsed; if(elapsed > max[uri]) max[uri]=elapsed}} "
                "END{for (u in count) printf \"%.6f %d %.6f %.6f %s\\n\", sum[u], count[u], sum[u]/count[u], max[u], u}"
            )
            + f" {shlex.quote(access_log)} | sort -nr | head -{int(limit)}"
        )
        completed = self._run_on_app_host(command)
        routes = []
        for line in (completed.stdout or "").splitlines():
            parts = line.split(" ", 4)
            if len(parts) != 5:
                continue
            total_time, count, avg_time, max_time, uri = parts
            if count.isdigit() and uri:
                routes.append(
                    {
                        "count": int(count),
                        "uri": uri,
                        "total_time_seconds": float(total_time),
                        "avg_time_seconds": float(avg_time),
                        "max_time_seconds": float(max_time),
                    }
                )
        return ToolResult(
            status="ok" if completed.returncode == 0 else "error",
            data={
                "host": host,
                "access_log": access_log,
                "sort": "total_time_seconds",
                "routes": routes,
                "returncode": completed.returncode,
                "stderr": completed.stderr,
            },
        )

    def _has_real_logs_config(self) -> bool:
        return all(key in self.config for key in ("ssh", "hosts", "logs"))

    def _collect_remote_recent(self, host: str, patterns: List[str]) -> ToolResult:
        units = self.config["logs"].get("app_journal_units", [])
        unit_args = " ".join(f"-u {shlex.quote(unit)}" for unit in units)
        grep_pattern = "|".join(patterns) if patterns else "."
        remote_command = (
            f"sudo journalctl {unit_args} --since '15 minutes ago' --no-pager "
            f"| grep -E {shlex.quote(grep_pattern)} | tail -200"
        )
        completed = self._run_on_app_host(remote_command)
        lines = (completed.stdout or "").splitlines()
        return ToolResult(
            status="ok" if completed.returncode in (0, 1) else "error",
            data={
                "host": host,
                "patterns": patterns,
                "lines": lines,
                "returncode": completed.returncode,
                "stderr": completed.stderr,
            },
        )

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
