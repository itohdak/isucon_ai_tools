from __future__ import annotations

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


class GitMCP(BaseMCP):
    name = "git"

    def diff(self, repo_path: str) -> ToolResult:
        return ToolResult(
            status="ok",
            data={
                "repo_path": repo_path,
                "diff": [
                    {"file": "app.go", "lines": ["+cache.Set(...)", "-db.Query(...) "]},
                ],
            },
        )

    def restore(self, repo_path: str) -> ToolResult:
        return ToolResult(status="ok", data={"repo_path": repo_path, "restored": True})
