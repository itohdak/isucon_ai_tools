from __future__ import annotations

from typing import Any, Dict, List

from isucon_ai_tools.mcp.apm import APMMCP
from isucon_ai_tools.mcp.benchmark import BenchmarkMCP
from isucon_ai_tools.mcp.history import HistoryMCP
from isucon_ai_tools.mcp.logs import LogsMCP
from isucon_ai_tools.mcp.mysql import MySQLMCP
from isucon_ai_tools.mcp.netdata import NetdataMCP
from isucon_ai_tools.skills.registry import SkillRegistry


class Orchestrator:
    def __init__(self):
        self.benchmark = BenchmarkMCP()
        self.netdata = NetdataMCP()
        self.mysql = MySQLMCP()
        self.logs = LogsMCP()
        self.apm = APMMCP()
        self.history = HistoryMCP()
        self.registry = SkillRegistry()

    def run_skill(self, skill_name: str, **kwargs: Any) -> Dict[str, Any]:
        skill = self.registry.get(skill_name)
        if skill_name == "baseline":
            result = self.benchmark.run(host=kwargs["host"], command=kwargs["command"])
            return {"skill": skill.name, "result": result.to_dict()}
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
            )
            return {"skill": skill.name, "result": result.to_dict()}
        if skill_name == "rollback":
            return {"skill": skill.name, "result": {"status": "ok", "rollback": True, "from_history": self.history.list_runs().to_dict()}}
        raise ValueError(f"Unsupported skill: {skill_name}")

    def plan(self) -> List[str]:
        return ["baseline", "monitor", "trace_analysis", "sql_tune", "record_improvement", "rollback"]
