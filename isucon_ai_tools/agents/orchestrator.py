from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from isucon_ai_tools.mcp.apm import APMMCP
from isucon_ai_tools.mcp.benchmark import BenchmarkMCP
from isucon_ai_tools.mcp.deploy import DeployMCP
from isucon_ai_tools.mcp.filesystem import FilesystemMCP
from isucon_ai_tools.mcp.git import GitMCP
from isucon_ai_tools.mcp.history import HistoryMCP
from isucon_ai_tools.mcp.iteration import IterationMCP
from isucon_ai_tools.mcp.logs import LogsMCP
from isucon_ai_tools.mcp.mysql import MySQLMCP
from isucon_ai_tools.mcp.netdata import NetdataMCP
from isucon_ai_tools.mcp.pprotein import PproteinMCP
from isucon_ai_tools.mcp.shell import ShellMCP
from isucon_ai_tools.policies.guardrails import Guardrails
from isucon_ai_tools.skills.registry import SkillRegistry


class Orchestrator:
    def __init__(self, config: Dict[str, Any] | None = None, config_path: str | None = None, runner: Any | None = None):
        if config is None and config_path is not None:
            config = yaml.safe_load(Path(config_path).read_text()) or {}
        self.config = config or {}
        self.config_path = config_path
        self.guardrails = Guardrails()
        self.benchmark = BenchmarkMCP(config=self.config, runner=runner)
        self.netdata = NetdataMCP(config=self.config)
        self.mysql = MySQLMCP(config=self.config, runner=runner)
        self.logs = LogsMCP(config=self.config, runner=runner)
        self.git = GitMCP(config=self.config, runner=runner, guardrails=self.guardrails)
        self.filesystem = FilesystemMCP(config=self.config, guardrails=self.guardrails)
        self.shell = ShellMCP(config=self.config, runner=runner, guardrails=self.guardrails)
        self.deploy = DeployMCP(config=self.config, runner=runner, guardrails=self.guardrails)
        self.iteration = IterationMCP(config=self.config)
        self.pprotein = PproteinMCP(config=self.config)
        self.apm = APMMCP()
        self.history = HistoryMCP(config=self.config)
        self.registry = SkillRegistry()

    def run_skill(self, skill_name: str, **kwargs: Any) -> Dict[str, Any]:
        skill = self.registry.get(skill_name)
        if skill_name == "baseline":
            result = self.collect_baseline(**kwargs)
            return {"skill": skill.name, "result": result}
        if skill_name == "monitor":
            snapshot = self.netdata.get_snapshot(host=kwargs["host"], window_seconds=300)
            apm = self.apm.get_slow_endpoints(host=kwargs["host"], limit=5)
            return {"skill": skill.name, "result": {"snapshot": snapshot.to_dict(), "apm": apm.to_dict()}}
        if skill_name == "trace_analysis":
            trace_summary = self.apm.summarize_traces(host=kwargs["host"])
            db_hotspots = self.apm.get_db_hotspots(host=kwargs["host"], limit=5)
            return {"skill": skill.name, "result": {"traces": trace_summary.to_dict(), "db_hotspots": db_hotspots.to_dict()}}
        if skill_name == "sql_tune":
            result = self.mysql.get_slow_queries(host=kwargs["host"], limit=10)
            return {"skill": skill.name, "result": result.to_dict()}
        if skill_name == "record_improvement":
            result = self.history.record_run(
                run_id=kwargs.get("run_id", "r-new"),
                before_score=kwargs.get("before_score", 1200),
                after_score=kwargs.get("after_score", 1500),
                hypothesis=kwargs.get("hypothesis", "trace reduction"),
                changed_files=kwargs.get("changed_files", ["app.go"]),
                evidence=kwargs.get("evidence"),
                rollback_status=kwargs.get("rollback_status", "not_needed"),
                before_report=kwargs.get("before_report"),
                after_report=kwargs.get("after_report"),
                commit=kwargs.get("commit"),
            )
            return {"skill": skill.name, "result": result.to_dict()}
        if skill_name == "deploy":
            result = self.deploy.deploy(
                host=kwargs.get("host", "app"),
                allow_dirty=kwargs.get("allow_dirty", False),
                dry_run=kwargs.get("dry_run", False),
            )
            return {"skill": skill.name, "result": result.to_dict()}
        if skill_name == "analyze_iteration":
            result = self.iteration.compare_reports(
                before_report=kwargs["before_report"],
                after_report=kwargs["after_report"],
                output_dir=kwargs.get("output_dir", "reports/iterations"),
            )
            return {"skill": skill.name, "result": result.to_dict()}
        if skill_name == "rollback":
            return {"skill": skill.name, "result": {"status": "ok", "rollback": True, "from_history": self.history.list_runs().to_dict()}}
        raise ValueError(f"Unsupported skill: {skill_name}")

    def collect_baseline(
        self,
        host: str | None = None,
        command: str = "make bench",
        report_dir: str | None = None,
        run_benchmark: bool = True,
        collect_observability: bool | None = None,
    ) -> Dict[str, Any]:
        app_host = host or self.config.get("hosts", {}).get("app", {}).get("name", "localhost")
        repo_path = self.config.get("git", {}).get("app_repo_path", ".")
        timestamp = datetime.now(timezone.utc).isoformat()
        should_collect = (
            self.config.get("pprotein", {}).get("collection", {}).get("mode") == "agent"
            if collect_observability is None
            else collect_observability
        )
        pprotein_collection = self.pprotein.collect(force=should_collect).to_dict()

        benchmark_result = (
            self.benchmark.run(host="bench", command=command).to_dict()
            if run_benchmark
            else {"status": "skipped", "data": None, "message": "Benchmark run skipped."}
        )
        slow_queries = self.mysql.get_slow_queries(host=app_host, limit=10).to_dict()
        git_status = self.git.status(repo_path=repo_path).to_dict()
        git_diff = self.git.diff(repo_path=repo_path).to_dict()
        resource_snapshot = self.netdata.get_snapshot(host=app_host, window_seconds=300).to_dict()
        route_summary = self.logs.summarize_routes(host=app_host, limit=20).to_dict()
        recent_logs = self.logs.collect_recent(host=app_host, patterns=["ERROR", "WARN", "error", "panic", "slow"]).to_dict()

        report = {
            "kind": "baseline",
            "environment": self.config.get("environment", "unknown"),
            "generated_at": timestamp,
            "app_host": app_host,
            "pprotein": {
                "collection": pprotein_collection,
                "dashboard": self.pprotein.dashboard().to_dict(),
            },
            "benchmark": benchmark_result,
            "git": {
                "status": git_status,
                "diff": git_diff,
            },
            "resources": resource_snapshot,
            "mysql": {
                "slow_queries": slow_queries,
            },
            "logs": {
                "routes": route_summary,
                "recent": recent_logs,
            },
        }

        path = self._write_report(report, report_dir=report_dir)
        return {
            "status": "ok",
            "report_path": str(path),
            "report": report,
        }

    def _write_report(self, report: Dict[str, Any], report_dir: str | None = None) -> Path:
        root = Path(report_dir) if report_dir else Path.cwd() / "reports"
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = root / f"baseline-{report.get('environment', 'unknown')}-{stamp}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return path

    def plan(self) -> List[str]:
        return ["baseline", "monitor", "trace_analysis", "sql_tune", "record_improvement", "deploy", "analyze_iteration", "rollback"]
