from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

import yaml

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class NetdataMCP(BaseMCP):
    name = "netdata"

    def __init__(self, config: Dict[str, Any] | None = None, config_path: str | None = None, runner: Any | None = None):
        if config is None and config_path is not None:
            config = yaml.safe_load(Path(config_path).read_text()) or {}
        super().__init__(config=config)
        self.runner = runner or subprocess.run

    def get_snapshot(self, host: str, window_seconds: int = 300) -> ToolResult:
        if self._has_real_resource_config():
            return self._get_remote_snapshot(host=host, window_seconds=window_seconds)

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
        if self._has_real_resource_config():
            snapshot = self.get_snapshot(host=host)
            metrics = snapshot.data.get("metrics", {}) if snapshot.data else {}
            alerts = []
            load_average = metrics.get("load_average", {})
            memory = metrics.get("memory", {})
            if load_average.get("load1") is not None and load_average["load1"] >= 2:
                alerts.append({"name": "load_average_1m", "status": "warning", "value": load_average["load1"]})
            if memory.get("used_percent") is not None and memory["used_percent"] >= 85:
                alerts.append({"name": "memory_used_percent", "status": "warning", "value": memory["used_percent"]})
            return ToolResult(
                status=snapshot.status,
                data={
                    "host": host,
                    "alerts": alerts,
                    "source": "remote shell",
                },
                message=snapshot.message,
            )

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

    def _has_real_resource_config(self) -> bool:
        return all(key in self.config for key in ("ssh", "hosts"))

    def _get_remote_snapshot(self, host: str, window_seconds: int) -> ToolResult:
        remote_command = (
            "printf 'UPTIME\\n'; uptime; "
            "printf 'FREE\\n'; free -m; "
            "printf 'DF\\n'; df -h /; "
            "printf 'PS\\n'; ps -eo pid,comm,%cpu,%mem --sort=-%cpu | head -6"
        )
        completed = self._run_on_app_host(remote_command)
        metrics = self._parse_snapshot(completed.stdout or "")
        return ToolResult(
            status="ok" if completed.returncode == 0 else "error",
            data={
                "host": host,
                "window_seconds": window_seconds,
                "source": "remote shell",
                "metrics": metrics,
                "raw": completed.stdout,
                "returncode": completed.returncode,
                "stderr": completed.stderr,
            },
        )

    def _parse_snapshot(self, output: str) -> Dict[str, Any]:
        sections: Dict[str, List[str]] = {}
        current: str | None = None
        for line in output.splitlines():
            if line in {"UPTIME", "FREE", "DF", "PS"}:
                current = line
                sections[current] = []
                continue
            if current is not None:
                sections[current].append(line)

        return {
            "load_average": self._parse_load_average(sections.get("UPTIME", [])),
            "memory": self._parse_memory(sections.get("FREE", [])),
            "disk": self._parse_disk(sections.get("DF", [])),
            "top_processes": self._parse_processes(sections.get("PS", [])),
        }

    def _parse_load_average(self, lines: List[str]) -> Dict[str, float | None]:
        if not lines:
            return {"load1": None, "load5": None, "load15": None}
        _, _, tail = lines[0].partition("load average:")
        values = [value.strip().rstrip(",") for value in tail.split(",")]
        parsed = []
        for value in values[:3]:
            try:
                parsed.append(float(value))
            except ValueError:
                parsed.append(None)
        parsed = (parsed + [None, None, None])[:3]
        return {"load1": parsed[0], "load5": parsed[1], "load15": parsed[2]}

    def _parse_memory(self, lines: List[str]) -> Dict[str, float | int | None]:
        mem_line = next((line for line in lines if line.startswith("Mem:")), "")
        parts = mem_line.split()
        if len(parts) < 3:
            return {"total_mb": None, "used_mb": None, "used_percent": None}
        total = int(parts[1])
        used = int(parts[2])
        used_percent = round((used / total) * 100, 1) if total else None
        return {"total_mb": total, "used_mb": used, "used_percent": used_percent}

    def _parse_disk(self, lines: List[str]) -> Dict[str, str | None]:
        data_line = next((line for line in lines if line.startswith("/")), "")
        parts = data_line.split()
        if len(parts) < 5:
            return {"filesystem": None, "used": None, "available": None, "used_percent": None}
        return {"filesystem": parts[0], "used": parts[2], "available": parts[3], "used_percent": parts[4]}

    def _parse_processes(self, lines: List[str]) -> List[Dict[str, Any]]:
        processes = []
        for line in lines[1:]:
            parts = line.split(None, 3)
            if len(parts) != 4:
                continue
            pid, command, cpu, memory = parts
            processes.append({"pid": int(pid), "command": command, "cpu_percent": float(cpu), "memory_percent": float(memory)})
        return processes

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
