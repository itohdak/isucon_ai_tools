from __future__ import annotations

import json

from isucon_ai_tools.agents.orchestrator import Orchestrator


def main() -> None:
    orchestrator = Orchestrator()
    print("Available skills:")
    print(orchestrator.plan())
    print()

    scenarios = [
        {
            "skill": "baseline",
            "kwargs": {"host": "localhost", "command": "make bench"},
        },
        {
            "skill": "monitor",
            "kwargs": {"host": "localhost"},
        },
        {
            "skill": "trace_analysis",
            "kwargs": {"host": "localhost"},
        },
        {
            "skill": "record_improvement",
            "kwargs": {
                "run_id": "demo-run-001",
                "before_score": 1200,
                "after_score": 1500,
                "hypothesis": "index patch and endpoint reduction",
                "changed_files": ["app.go", "schema.sql"],
            },
        },
    ]

    for scenario in scenarios:
        skill_name = scenario["skill"]
        result = orchestrator.run_skill(skill_name, **scenario["kwargs"])
        print(f"Skill: {skill_name}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("-" * 80)


if __name__ == "__main__":
    main()
