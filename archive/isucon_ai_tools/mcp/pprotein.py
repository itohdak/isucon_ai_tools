from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict
from urllib.error import URLError
from urllib.request import urlopen

import yaml

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult


HttpGet = Callable[[str, int], Any]


class PproteinMCP(BaseMCP):
    name = "pprotein"

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        config_path: str | None = None,
        http_get: HttpGet | None = None,
    ):
        if config is None and config_path is not None:
            config = yaml.safe_load(Path(config_path).read_text()) or {}
        super().__init__(config=config)
        self.http_get = http_get or self._default_http_get

    def collect(self, force: bool = False) -> ToolResult:
        pprotein_config = self.config.get("pprotein", {})
        collection_config = pprotein_config.get("collection", {})
        if not pprotein_config.get("enabled", False):
            return ToolResult(status="skipped", data={"enabled": False}, message="pprotein is disabled.")

        mode = collection_config.get("mode", "manual")
        if mode != "agent" and not force:
            return ToolResult(
                status="skipped",
                data={"enabled": True, "mode": mode},
                message="pprotein collection is configured for manual control.",
            )

        base_url = pprotein_config["base_url"].rstrip("/")
        endpoint = collection_config.get("collect_endpoint", "/api/group/collect")
        url = f"{base_url}{endpoint}"
        timeout_seconds = int(collection_config.get("timeout_seconds", 10))
        try:
            response = self.http_get(url, timeout_seconds)
        except URLError as exc:
            return ToolResult(status="error", data={"url": url}, message=str(exc))
        except OSError as exc:
            return ToolResult(status="error", data={"url": url}, message=str(exc))

        return ToolResult(
            status="ok",
            data={
                "url": url,
                "status_code": response.get("status_code"),
                "body": response.get("body"),
            },
            message="pprotein collection started.",
        )

    def dashboard(self) -> ToolResult:
        pprotein_config = self.config.get("pprotein", {})
        base_url = pprotein_config.get("base_url")
        if not base_url:
            return ToolResult(status="error", message="pprotein.base_url is not configured.")
        return ToolResult(
            status="ok",
            data={
                "dashboard_url": pprotein_config.get("dashboard_url", f"{base_url.rstrip('/')}/#/group/"),
                "base_url": base_url,
                "mode": pprotein_config.get("collection", {}).get("mode", "manual"),
            },
        )

    def targets(self) -> ToolResult:
        pprotein_config = self.config.get("pprotein", {})
        target_file = pprotein_config.get("targets_file")
        if target_file and Path(target_file).exists():
            return ToolResult(status="ok", data={"targets": json.loads(Path(target_file).read_text())})
        return ToolResult(
            status="ok",
            data={
                "targets_file": target_file,
                "targets": pprotein_config.get("targets", []),
            },
        )

    def _default_http_get(self, url: str, timeout_seconds: int) -> Dict[str, Any]:
        with urlopen(url, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {"status_code": response.status, "body": body}
