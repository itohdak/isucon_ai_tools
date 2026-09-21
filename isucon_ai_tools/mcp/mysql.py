from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import yaml

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult

CommandRunner = Any


class MySQLMCP(BaseMCP):
    name = "mysql"

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

    def get_slow_queries(self, host: str, limit: int = 20) -> ToolResult:
        if self._has_real_mysql_config():
            return self._get_remote_slow_queries(host=host, limit=limit)

        return ToolResult(
            status="ok",
            data={
                "host": host,
                "slow_queries": [
                    {"query": "SELECT * FROM users WHERE id = ?", "time_ms": 180},
                    {"query": "SELECT * FROM orders WHERE user_id = ?", "time_ms": 120},
                ][:limit],
            },
        )

    def explain_queries(self, host: str, queries: List[str]) -> ToolResult:
        if self._has_real_mysql_config():
            return self._explain_remote_queries(host=host, queries=queries)

        return ToolResult(
            status="ok",
            data={
                "host": host,
                "explain": [
                    {"query": q, "plan": ["table_scan", "index_missing"]} for q in queries
                ],
            },
        )

    def get_processlist(self, host: str) -> ToolResult:
        if not self._has_real_mysql_config():
            return ToolResult(status="ok", data={"host": host, "processlist": []})

        database = self.config["mysql"]["database"]
        sql = "SHOW FULL PROCESSLIST"
        completed = self._run_on_app_host(f"sudo mysql {shlex.quote(database)} -e {shlex.quote(sql)}")
        return ToolResult(
            status="ok" if completed.returncode == 0 else "error",
            data={
                "host": host,
                "returncode": completed.returncode,
                "processlist": completed.stdout,
                "stderr": completed.stderr,
            },
        )

    def get_attributed_slow_queries(self, host: str, limit: int = 20) -> ToolResult:
        if self._has_real_mysql_config():
            slow_log = self.config["logs"]["mysql_slow_log"]
            completed = self._run_on_app_host(f"sudo tail -n 20000 {shlex.quote(slow_log)}")
            rows = self._parse_attributed_slow_log(completed.stdout or "", limit=limit)
            return ToolResult(
                status="ok" if completed.returncode == 0 else "error",
                data={
                    "host": host,
                    "slow_log": slow_log,
                    "sort": "total_time_ms",
                    "attributed_slow_queries": rows,
                    "returncode": completed.returncode,
                    "stderr": completed.stderr,
                },
            )

        return ToolResult(
            status="ok",
            data={
                "host": host,
                "sort": "total_time_ms",
                "attributed_slow_queries": [],
            },
        )

    def _has_real_mysql_config(self) -> bool:
        return all(key in self.config for key in ("ssh", "hosts", "mysql", "logs"))

    def _get_remote_slow_queries(self, host: str, limit: int) -> ToolResult:
        slow_log = self.config["logs"]["mysql_slow_log"]
        completed = self._run_on_app_host(f"sudo tail -n 5000 {shlex.quote(slow_log)}")
        queries = self._parse_slow_log(completed.stdout or "", limit=limit)
        return ToolResult(
            status="ok" if completed.returncode == 0 else "error",
            data={
                "host": host,
                "slow_log": slow_log,
                "slow_queries": queries,
                "returncode": completed.returncode,
                "stderr": completed.stderr,
            },
        )

    def _explain_remote_queries(self, host: str, queries: List[str]) -> ToolResult:
        database = self.config["mysql"]["database"]
        explain_results = []
        status = "ok"
        for query in queries:
            explain_sql = f"EXPLAIN {query.rstrip(';')}"
            completed = self._run_on_app_host(
                f"sudo mysql {shlex.quote(database)} -e {shlex.quote(explain_sql)}"
            )
            if completed.returncode != 0:
                status = "error"
            explain_results.append(
                {
                    "query": query,
                    "returncode": completed.returncode,
                    "plan": completed.stdout,
                    "stderr": completed.stderr,
                }
            )
        return ToolResult(
            status=status,
            data={
                "host": host,
                "explain": explain_results,
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
        return self.runner(
            ssh_command,
            text=True,
            capture_output=True,
            timeout=int(self.config.get("mysql", {}).get("timeout_seconds", 30)),
        )

    def _parse_slow_log(self, slow_log: str, limit: int) -> List[Dict[str, Any]]:
        aggregates: Dict[str, Dict[str, Any]] = {}
        current_time: float | None = None
        for raw_line in slow_log.splitlines():
            line = raw_line.strip()
            query_time_match = re.search(r"Query_time:\s+(?P<time>[0-9.]+)", line)
            if query_time_match:
                current_time = float(query_time_match.group("time"))
                continue
            if not line or line.startswith("#") or line.startswith("SET timestamp="):
                continue
            if line.startswith("# administrator command:"):
                continue

            query = line.rstrip(";")
            if not query:
                continue
            entry = aggregates.setdefault(
                query,
                {
                    "query": query,
                    "count": 0,
                    "total_time_ms": 0.0,
                    "max_time_ms": 0.0,
                },
            )
            elapsed_ms = (current_time or 0.0) * 1000
            entry["count"] += 1
            entry["total_time_ms"] += elapsed_ms
            entry["max_time_ms"] = max(entry["max_time_ms"], elapsed_ms)
            entry["avg_time_ms"] = entry["total_time_ms"] / entry["count"]
            current_time = None

        return sorted(
            aggregates.values(),
            key=lambda item: (item["total_time_ms"], item["count"]),
            reverse=True,
        )[:limit]

    def _parse_attributed_slow_log(self, slow_log: str, limit: int) -> List[Dict[str, Any]]:
        aggregates: Dict[tuple[str, str, str], Dict[str, Any]] = {}
        current_time: float | None = None
        current_api = "unknown"
        current_fn = "unknown"
        current_query_lines: List[str] = []

        def flush_query() -> None:
            nonlocal current_time, current_api, current_fn, current_query_lines
            query = self._clean_query_lines(current_query_lines)
            current_query_lines = []
            if not query:
                current_time = None
                current_api = "unknown"
                current_fn = "unknown"
                return

            normalized_query = self._normalize_query(query)
            key = (current_api, current_fn, normalized_query)
            entry = aggregates.setdefault(
                key,
                {
                    "api": current_api,
                    "fn": current_fn,
                    "query": normalized_query,
                    "count": 0,
                    "total_time_ms": 0.0,
                    "max_time_ms": 0.0,
                },
            )
            elapsed_ms = (current_time or 0.0) * 1000
            entry["count"] += 1
            entry["total_time_ms"] += elapsed_ms
            entry["max_time_ms"] = max(entry["max_time_ms"], elapsed_ms)
            entry["avg_time_ms"] = entry["total_time_ms"] / entry["count"]
            current_time = None
            current_api = "unknown"
            current_fn = "unknown"

        for raw_line in slow_log.splitlines():
            line = raw_line.strip()
            query_time_match = re.search(r"Query_time:\s+(?P<time>[0-9.]+)", line)
            if query_time_match:
                flush_query()
                current_time = float(query_time_match.group("time"))
                continue
            if not line or line.startswith("SET timestamp="):
                continue
            if line.startswith("#"):
                continue
            if line.startswith("# administrator command:"):
                continue

            comment_match = re.search(r"/\*\s*(?P<body>.*?)\s*\*/", line)
            if comment_match:
                body = comment_match.group("body")
                api_match = re.search(r"api:(?P<api>[^\s]+)", body)
                fn_match = re.search(r"fn:(?P<fn>[^\s]+)", body)
                route_match = re.search(r"route:(?P<method>[A-Z]+)\s+(?P<route>[^\s]+)", body)
                if route_match:
                    current_api = f"{route_match.group('method')} {route_match.group('route')}"
                elif api_match:
                    current_api = api_match.group("api")
                if fn_match:
                    current_fn = fn_match.group("fn")
                line = re.sub(r"/\*.*?\*/", "", line).strip()
                if not line:
                    continue

            current_query_lines.append(line)
            if line.endswith(";"):
                flush_query()

        flush_query()
        return sorted(
            aggregates.values(),
            key=lambda item: (item["total_time_ms"], item["count"]),
            reverse=True,
        )[:limit]

    def _clean_query_lines(self, query_lines: List[str]) -> str:
        cleaned = " ".join(line.strip() for line in query_lines if line.strip())
        if not cleaned or cleaned.startswith("# administrator command:"):
            return ""
        cleaned = cleaned.rstrip(";")
        if cleaned.upper() in {"BEGIN", "COMMIT", "ROLLBACK", "START TRANSACTION"}:
            return ""
        return cleaned

    def _normalize_query(self, query: str) -> str:
        normalized = re.sub(r"'(?:''|[^'])*'", "?", query)
        normalized = re.sub(r"\b-?\d+(?:\.\d+)?\b", "?", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized
