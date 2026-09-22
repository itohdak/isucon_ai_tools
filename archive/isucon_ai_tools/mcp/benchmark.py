from __future__ import annotations

import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class BenchmarkMCP(BaseMCP):
    name = "benchmark"

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        config_path: str | None = None,
        runner: CommandRunner | None = None,
    ):
        if config is None and config_path is not None:
            config = yaml.safe_load(Path(config_path).read_text()) or {}
        super().__init__(config=config)
        self.runner = runner or subprocess.run

    def run(self, host: str = "localhost", command: str = "make bench", capture_logs: bool = True) -> ToolResult:
        if self._has_real_benchmark_config():
            return self._run_remote_benchmark(host=host, capture_logs=capture_logs)

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

    def _has_real_benchmark_config(self) -> bool:
        return all(
            key in self.config
            for key in ("ssh", "hosts", "benchmark")
        )

    def _run_remote_benchmark(self, host: str, capture_logs: bool) -> ToolResult:
        ssh_config = self.config["ssh"]
        bench_host = self.config["hosts"]["bench"]
        benchmark_config = self.config["benchmark"]

        remote_user = ssh_config["user"]
        private_key_path = ssh_config["private_key_path"]
        remote_host = bench_host["public_ip"]
        workdir = benchmark_config["working_directory"]
        benchmark_command = [str(part) for part in benchmark_config["command"]]

        remote_command = f"cd {shlex.quote(workdir)} && {shlex.join(benchmark_command)} 2>&1"
        ssh_command = [
            "ssh",
            "-i",
            private_key_path,
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            f"{remote_user}@{remote_host}",
            remote_command,
        ]

        completed = self.runner(
            ssh_command,
            text=True,
            capture_output=True,
            timeout=int(benchmark_config.get("timeout_seconds", 180)),
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        parsed = self._parse_benchmark_output(output)

        data = {
            "host": host,
            "remote_host": remote_host,
            "command": benchmark_command,
            "capture_logs": capture_logs,
            "returncode": completed.returncode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            **parsed,
        }
        status = "ok" if completed.returncode == 0 and parsed.get("pass") is True else "error"
        message = "Benchmark completed." if status == "ok" else "Benchmark failed or did not pass."
        return ToolResult(status=status, data=data, message=message)

    def _parse_benchmark_output(self, output: str) -> Dict[str, Any]:
        result_match = re.search(
            r"結果\s+pass=(?P<pass>true|false)\s+スコア=(?P<score>-?\d+)\s+種別エラー数=(?P<errors>[^\n]+)",
            output,
        )
        if result_match is None:
            return {
                "pass": None,
                "score": None,
                "error_counts": None,
            }
        return {
            "pass": result_match.group("pass") == "true",
            "score": int(result_match.group("score")),
            "error_counts": result_match.group("errors"),
        }

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
