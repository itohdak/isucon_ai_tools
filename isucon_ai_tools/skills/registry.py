from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class SkillSpec:
    name: str
    description: str
    required_tools: list[str]


class SkillRegistry:
    def __init__(self):
        self.skills: Dict[str, SkillSpec] = {
            "baseline": SkillSpec(
                name="baseline",
                description="Measure the initial benchmark and capture the environment state.",
                required_tools=["benchmark", "netdata", "logs"],
            ),
            "monitor": SkillSpec(
                name="monitor",
                description="Collect telemetry and identify likely bottlenecks.",
                required_tools=["netdata", "apm", "logs"],
            ),
            "trace_analysis": SkillSpec(
                name="trace_analysis",
                description="Analyze per-route and per-query latency to isolate expensive paths and hotspots.",
                required_tools=["apm", "mysql", "logs"],
            ),
            "sql_tune": SkillSpec(
                name="sql_tune",
                description="Analyze slow queries and optimize database access.",
                required_tools=["mysql", "logs", "filesystem"],
            ),
            "record_improvement": SkillSpec(
                name="record_improvement",
                description="Persist before/after benchmark results and the hypothesis that produced the change.",
                required_tools=["benchmark", "history"],
            ),
            "deploy": SkillSpec(
                name="deploy",
                description="Apply fix and deploy the updated artifact.",
                required_tools=["filesystem", "git", "shell"],
            ),
            "rollback": SkillSpec(
                name="rollback",
                description="Restore the last known good state when a hypothesis worsens the score.",
                required_tools=["git", "filesystem", "shell", "history"],
            ),
        }

    def list(self) -> Dict[str, SkillSpec]:
        return self.skills

    def get(self, name: str) -> SkillSpec:
        return self.skills[name]
