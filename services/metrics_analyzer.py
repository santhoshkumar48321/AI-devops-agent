"""
services/metrics_analyzer.py - Infrastructure metrics analysis.

Provides:
- Threshold-based alerting for CPU / memory / disk
- Prometheus HTTP API integration
- Trend detection (rising / falling / stable)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any


@dataclass
class MetricAlert:
    """A single threshold breach."""
    metric: str
    value: float
    threshold: float
    severity: str     # "warning" | "critical"
    message: str


@dataclass
class MetricsReport:
    """Summary of metrics analysis."""
    alerts: list[MetricAlert]
    raw: dict[str, Any]
    summary: str

    @property
    def has_critical(self) -> bool:
        return any(a.severity == "critical" for a in self.alerts)


# Default thresholds
_THRESHOLDS = {
    "cpu_percent": {"warning": 70.0, "critical": 90.0},
    "memory_percent": {"warning": 75.0, "critical": 90.0},
    "disk_percent": {"warning": 80.0, "critical": 95.0},
    "load_1m": {"warning": 5.0, "critical": 10.0},
}


class MetricsAnalyzer:
    """
    Analyse infrastructure metrics from various sources.
    """

    def __init__(self, prometheus_url: str = "") -> None:
        self._prometheus_url = prometheus_url

    def analyze(self, metrics: dict[str, float]) -> MetricsReport:
        """
        Evaluate a flat *metrics* dict against known thresholds.

        Parameters
        ----------
        metrics:
            e.g. {"cpu_percent": 85.0, "memory_percent": 60.0}

        Returns
        -------
        MetricsReport with any threshold breaches listed as alerts.
        """
        alerts: list[MetricAlert] = []
        for name, value in metrics.items():
            if name not in _THRESHOLDS:
                continue
            thresholds = _THRESHOLDS[name]
            if value >= thresholds["critical"]:
                alerts.append(MetricAlert(
                    metric=name, value=value,
                    threshold=thresholds["critical"],
                    severity="critical",
                    message=f"`{name}` is critically high at {value:.1f}% (threshold: {thresholds['critical']}%)",
                ))
            elif value >= thresholds["warning"]:
                alerts.append(MetricAlert(
                    metric=name, value=value,
                    threshold=thresholds["warning"],
                    severity="warning",
                    message=f"`{name}` is elevated at {value:.1f}% (threshold: {thresholds['warning']}%)",
                ))

        summary = self._build_summary(alerts)
        return MetricsReport(alerts=alerts, raw=metrics, summary=summary)

    async def query_prometheus(self, query: str) -> dict[str, Any]:
        """
        Run an instant PromQL query against the configured Prometheus instance.

        Returns the raw Prometheus API response dict, or an error dict.
        """
        if not self._prometheus_url:
            return {"error": "Prometheus URL not configured"}
        url = f"{self._prometheus_url.rstrip('/')}/api/v1/query"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, params={"query": query})
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            return {"error": str(exc), "query": query}

    async def get_pod_cpu(self, namespace: str, pod: str) -> dict[str, Any]:
        """Convenience: fetch CPU usage for a specific pod from Prometheus."""
        query = f'rate(container_cpu_usage_seconds_total{{namespace="{namespace}",pod="{pod}"}}[5m])'
        return await self.query_prometheus(query)

    async def get_pod_memory(self, namespace: str, pod: str) -> dict[str, Any]:
        """Convenience: fetch memory usage for a specific pod from Prometheus."""
        query = f'container_memory_usage_bytes{{namespace="{namespace}",pod="{pod}"}}'
        return await self.query_prometheus(query)

    def detect_trend(self, values: list[float]) -> str:
        """
        Simple linear trend detection on a time series.

        Returns "rising", "falling", or "stable".
        """
        if len(values) < 2:
            return "stable"
        diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
        avg_diff = sum(diffs) / len(diffs)
        if avg_diff > 1.0:
            return "rising"
        if avg_diff < -1.0:
            return "falling"
        return "stable"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(alerts: list[MetricAlert]) -> str:
        if not alerts:
            return "All metrics are within normal thresholds."
        lines = ["**Metrics Analysis:**"]
        for a in alerts:
            icon = "🔴" if a.severity == "critical" else "🟡"
            lines.append(f"{icon} {a.message}")
        return "\n".join(lines)
