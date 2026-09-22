from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List

import yaml

from isucon_ai_tools.mcp.base import BaseMCP, ToolResult

# Charts queried for a resource snapshot, keyed by the metric group name
# used in the returned data.
_SNAPSHOT_CHARTS: Dict[str, str] = {
    "cpu": "system.cpu",
    "load": "system.load",
    "memory": "system.ram",
    "disk_io": "system.io",
}


class NetdataMCP(BaseMCP):
    """Reads resource metrics from a Netdata parent that other ISUCON
    instances stream their metrics to (see isucon_ansible/roles/general).
    """

    name = "netdata"

    def __init__(
        self,
        config: Dict[str, Any] | None = None,
        config_path: str | None = None,
        fetcher: Callable[[str], Dict[str, Any]] | None = None,
    ):
        if config is None and config_path is not None:
            config = yaml.safe_load(Path(config_path).read_text()) or {}
        super().__init__(config=config)
        self.fetcher = fetcher or self._default_fetcher

    def get_snapshot(self, host: str, window_seconds: int = 300) -> ToolResult:
        if not self._has_real_resource_config():
            return ToolResult(
                status="ok",
                data={
                    "host": host,
                    "window_seconds": window_seconds,
                    "points": {
                        "cpu": [10, 15, 18, 20, 25],
                        "memory": [60, 63, 65, 64, 66],
                        "disk": [40, 42, 41, 43, 45],
                    },
                },
            )

        netdata_host = self._resolve_netdata_host(host)
        metrics: Dict[str, Any] = {}
        errors: List[str] = []
        for group, chart in _SNAPSHOT_CHARTS.items():
            try:
                metrics[group] = self._fetch_chart_average(netdata_host, chart, window_seconds)
            except Exception as exc:  # noqa: BLE001 - report per-chart failure, keep going
                errors.append(f"{chart}: {exc}")

        return ToolResult(
            status="ok" if metrics else "error",
            data={
                "host": host,
                "netdata_host": netdata_host,
                "window_seconds": window_seconds,
                "source": "netdata",
                "metrics": metrics,
            },
            message="; ".join(errors) if errors else None,
        )

    def get_alerts(self, host: str) -> ToolResult:
        if not self._has_real_resource_config():
            return ToolResult(
                status="ok",
                data={
                    "host": host,
                    "alerts": [
                        {"name": "cpu_usage", "status": "warning", "value": 78},
                        {"name": "memory_pressure", "status": "ok", "value": 64},
                    ],
                },
            )

        netdata_host = self._resolve_netdata_host(host)
        try:
            payload = self.fetcher(f"{self._parent_url()}/host/{netdata_host}/api/v1/alarms?active")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                status="error",
                data={"host": host, "netdata_host": netdata_host, "source": "netdata"},
                message=str(exc),
            )

        raw_alarms = payload.get("alarms", {})
        alerts = [
            {"name": name, "status": info.get("status"), "value": info.get("value")}
            for name, info in raw_alarms.items()
        ]
        return ToolResult(
            status="ok",
            data={"host": host, "netdata_host": netdata_host, "alerts": alerts, "source": "netdata"},
        )

    def _has_real_resource_config(self) -> bool:
        return bool(self.config.get("netdata", {}).get("parent"))

    def _resolve_netdata_host(self, host: str) -> str:
        return self.config.get("netdata", {}).get("hosts", {}).get(host, host)

    def _parent_url(self) -> str:
        parent = self.config["netdata"]["parent"]
        url = parent.get("url")
        if url:
            return url.rstrip("/")
        return f"http://{parent['private_ip']}:{parent.get('port', 19999)}"

    def _fetch_chart_average(self, netdata_host: str, chart: str, window_seconds: int) -> Dict[str, Any]:
        url = (
            f"{self._parent_url()}/host/{netdata_host}/api/v1/data"
            f"?chart={chart}&after=-{window_seconds}&points=1&group=average&format=json"
        )
        payload = self.fetcher(url)
        return self._latest_row_as_dict(payload)

    def _latest_row_as_dict(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = payload.get("result", payload)
        labels = result.get("labels") or []
        rows = result.get("data") or []
        if not labels or not rows:
            return {}
        row = rows[-1]
        return {label: value for label, value in zip(labels, row) if label != "time"}

    @staticmethod
    def _default_fetcher(url: str) -> Dict[str, Any]:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - internal Netdata API only
            return json.loads(response.read().decode("utf-8"))
