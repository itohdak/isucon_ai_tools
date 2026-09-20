from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class ToolResult:
    status: str
    data: Dict[str, Any] | List[Any] | None = None
    message: str | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "data": self.data,
            "message": self.message,
        }


class BaseMCP:
    """Base class for tool servers exposing functions to the AI agent."""

    name: str = "base"

    def __init__(self, config: Dict[str, Any] | None = None):
        self.config = config or {}

    def call(self, method: str, **kwargs: Any) -> ToolResult:
        handler = getattr(self, method, None)
        if handler is None:
            return ToolResult(status="error", message=f"Unknown method: {method}")
        try:
            result = handler(**kwargs)
            if isinstance(result, ToolResult):
                return result
            return ToolResult(status="ok", data=result)
        except Exception as exc:  # pragma: no cover - defensive path
            return ToolResult(status="error", message=str(exc))
