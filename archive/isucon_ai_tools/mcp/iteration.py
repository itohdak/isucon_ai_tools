from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class IterationMCP(BaseMCP):
    name = "iteration"

    def compare_reports(
        self,
        before_report: str,
        after_report: str,
        output_dir: str = "reports/iterations",
    ) -> ToolResult:
        before = self._load_report(before_report)
        after = self._load_report(after_report)
        comparison = self._build_comparison(before, after, before_report, after_report)
        markdown_path = self._write_markdown_report(comparison, output_dir=output_dir)
        return ToolResult(
            status="ok",
            data={
                **comparison,
                "markdown_path": str(markdown_path),
            },
        )

    def _build_comparison(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
        before_report: str,
        after_report: str,
    ) -> Dict[str, Any]:
        before_score = self._score(before)
        after_score = self._score(after)
        score_delta = after_score - before_score if before_score is not None and after_score is not None else None
        before_errors = self._error_counts(before)
        after_errors = self._error_counts(after)
        new_errors = sorted(set(after_errors) - set(before_errors))
        resolved_errors = sorted(set(before_errors) - set(after_errors))
        slow_query_diff = self._diff_slow_queries(before, after)
        route_diff = self._diff_routes(before, after)
        suggestions = self._suggest_next_actions(after, score_delta, new_errors, slow_query_diff, route_diff)

        return {
            "kind": "iteration_comparison",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "before_report": before_report,
            "after_report": after_report,
            "score": {
                "before": before_score,
                "after": after_score,
                "delta": score_delta,
                "regression": score_delta is not None and score_delta < 0,
            },
            "errors": {
                "before": before_errors,
                "after": after_errors,
                "new": new_errors,
                "resolved": resolved_errors,
            },
            "slow_queries": slow_query_diff,
            "routes": route_diff,
            "suggestions": suggestions,
        }

    def _load_report(self, report_path: str) -> Dict[str, Any]:
        return json.loads(Path(report_path).read_text(encoding="utf-8"))

    def _score(self, report: Dict[str, Any]) -> int | None:
        return report.get("benchmark", {}).get("data", {}).get("score")

    def _error_counts(self, report: Dict[str, Any]) -> Dict[str, int]:
        raw_errors = report.get("benchmark", {}).get("data", {}).get("error_counts") or ""
        if raw_errors in ("map[]", "{}"):
            return {}
        if raw_errors.startswith("map[") and raw_errors.endswith("]"):
            body = raw_errors[4:-1]
            errors = {}
            for item in body.split():
                key, _, value = item.partition(":")
                if key and value.isdigit():
                    errors[key] = int(value)
            return errors
        return {"raw": 1}

    def _diff_slow_queries(self, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        before_queries = self._slow_query_map(before)
        after_queries = self._slow_query_map(after)
        changed = []
        for query, after_item in after_queries.items():
            before_item = before_queries.get(query)
            before_total = float(before_item.get("total_time_ms", 0.0)) if before_item else 0.0
            after_total = float(after_item.get("total_time_ms", 0.0))
            changed.append(
                {
                    "query": query,
                    "before_total_time_ms": before_total,
                    "after_total_time_ms": after_total,
                    "delta_total_time_ms": after_total - before_total,
                    "after_count": int(after_item.get("count", 0)),
                    "is_new": before_item is None,
                }
            )
        improved = []
        for query, before_item in before_queries.items():
            if query not in after_queries:
                improved.append(
                    {
                        "query": query,
                        "before_total_time_ms": float(before_item.get("total_time_ms", 0.0)),
                        "after_total_time_ms": 0.0,
                        "delta_total_time_ms": -float(before_item.get("total_time_ms", 0.0)),
                        "after_count": 0,
                        "is_resolved": True,
                    }
                )
        return {
            "new_or_worse_top": sorted(changed, key=lambda item: item["after_total_time_ms"], reverse=True)[:10],
            "resolved_or_better_top": sorted(improved, key=lambda item: item["before_total_time_ms"], reverse=True)[:10],
        }

    def _slow_query_map(self, report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        queries = report.get("mysql", {}).get("slow_queries", {}).get("data", {}).get("slow_queries", [])
        return {item["query"]: item for item in queries}

    def _diff_routes(self, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        before_routes = self._route_map(before)
        after_routes = self._route_map(after)
        routes = []
        for uri, after_count in after_routes.items():
            before_count = before_routes.get(uri, 0)
            routes.append(
                {
                    "uri": uri,
                    "before_count": before_count,
                    "after_count": after_count,
                    "delta_count": after_count - before_count,
                    "is_new": uri not in before_routes,
                }
            )
        return {
            "top_after": sorted(routes, key=lambda item: item["after_count"], reverse=True)[:10],
        }

    def _route_map(self, report: Dict[str, Any]) -> Dict[str, int]:
        routes = report.get("logs", {}).get("routes", {}).get("data", {}).get("routes", [])
        return {item["uri"]: int(item["count"]) for item in routes}

    def _suggest_next_actions(
        self,
        after: Dict[str, Any],
        score_delta: int | None,
        new_errors: List[str],
        slow_query_diff: Dict[str, Any],
        route_diff: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        suggestions = []
        if score_delta is not None and score_delta < 0:
            suggestions.append(
                {
                    "priority": "high",
                    "area": "rollback",
                    "reason": f"Score regressed by {abs(score_delta)}.",
                }
            )
        if new_errors:
            suggestions.append(
                {
                    "priority": "high",
                    "area": "benchmark_errors",
                    "reason": f"New benchmark error categories appeared: {', '.join(new_errors)}.",
                }
            )

        top_query = next(iter(slow_query_diff.get("new_or_worse_top", [])), None)
        if top_query:
            suggestions.append(
                {
                    "priority": "medium",
                    "area": "slow_query",
                    "reason": f"Inspect query with {top_query['after_total_time_ms']:.1f}ms total slow-log time: {top_query['query'][:160]}",
                }
            )

        top_route = next(iter(route_diff.get("top_after", [])), None)
        if top_route:
            suggestions.append(
                {
                    "priority": "medium",
                    "area": "endpoint",
                    "reason": f"Highest request count after run is {top_route['uri']} ({top_route['after_count']} requests).",
                }
            )

        load_average = after.get("resources", {}).get("data", {}).get("metrics", {}).get("load_average", {})
        if load_average.get("load1") is not None and load_average["load1"] >= 2:
            suggestions.append(
                {
                    "priority": "low",
                    "area": "resource",
                    "reason": f"Load average was high after the run: {load_average['load1']}.",
                }
            )
        return suggestions

    def _write_markdown_report(self, comparison: Dict[str, Any], output_dir: str) -> Path:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = root / f"iteration-{stamp}.md"
        score = comparison["score"]
        lines = [
            "# Iteration Comparison",
            "",
            f"- Generated at: `{comparison['generated_at']}`",
            f"- Before report: `{comparison['before_report']}`",
            f"- After report: `{comparison['after_report']}`",
            f"- Score: `{score['before']}` -> `{score['after']}` (`{score['delta']}`)",
            f"- Regression: `{score['regression']}`",
            "",
            "## Suggestions",
            "",
            *[f"- **{item['priority']}** `{item['area']}`: {item['reason']}" for item in comparison["suggestions"]],
            "",
            "## New Or Worse Slow Queries",
            "",
            *[
                f"- `{item['after_total_time_ms']:.1f}ms` count `{item['after_count']}`: `{item['query']}`"
                for item in comparison["slow_queries"]["new_or_worse_top"][:5]
            ],
            "",
            "## Top Routes After",
            "",
            *[
                f"- `{item['after_count']}` `{item['uri']}`"
                for item in comparison["routes"]["top_after"][:5]
            ],
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
        return path
