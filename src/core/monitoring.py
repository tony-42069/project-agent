"""Monitoring module for Project Agent."""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..core.config import get_config
from ..core.logging_ import get_logger

logger = get_logger(__name__)

config = get_config()


@dataclass
class HealthStatus:
    """Health status information."""
    status: str
    version: str
    uptime_seconds: float
    components: Dict[str, Dict[str, Any]]
    timestamp: datetime


@dataclass
class Metric:
    """A single metric."""
    name: str
    value: float
    labels: Dict[str, str]
    timestamp: datetime
    metric_type: str


class MetricsCollector:
    """Collects and manages application metrics."""

    def __init__(self):
        self._start_time = time.time()
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._component_health: Dict[str, Dict[str, Any]] = {}

    def counter(self, name: str, value: float = 1, labels: Optional[Dict[str, str]] = None) -> None:
        """Increment a counter."""
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Set a gauge value."""
        key = self._make_key(name, labels)
        self._gauges[key] = value

    def histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a histogram value."""
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)

    def _make_key(self, name: str, labels: Optional[Dict[str, str]] = None) -> str:
        """Create a unique key for a metric."""
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name

    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get a counter value."""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get a gauge value."""
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0)

    def get_histogram_percentile(
        self, name: str, percentile: float, labels: Optional[Dict[str, str]] = None
    ) -> float:
        """Get a histogram percentile value."""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])
        if not values:
            return 0.0

        values.sort()
        index = int(len(values) * percentile / 100)
        return values[min(index, len(values) - 1)]

    def get_all_metrics(self) -> List[Metric]:
        """Get all metrics in Prometheus format."""
        metrics = []

        for key, value in self._counters.items():
            name, labels = self._parse_key(key)
            metrics.append(Metric(
                name=name,
                value=value,
                labels=labels,
                timestamp=datetime.utcnow(),
                metric_type="counter",
            ))

        for key, value in self._gauges.items():
            name, labels = self._parse_key(key)
            metrics.append(Metric(
                name=name,
                value=value,
                labels=labels,
                timestamp=datetime.utcnow(),
                metric_type="gauge",
            ))

        for key, values in self._histograms.items():
            name, labels = self._parse_key(key)
            metrics.append(Metric(
                name=name,
                value=sum(values) / len(values),
                labels=labels,
                timestamp=datetime.utcnow(),
                metric_type="histogram",
            ))

        return metrics

    def _parse_key(self, key: str) -> tuple:
        """Parse a metric key into name and labels."""
        if "{" in key:
            name = key.split("{")[0]
            label_str = key.split("{")[1].rstrip("}")
            labels = {}
            for part in label_str.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    labels[k] = v
            return name, labels
        return key, {}

    def format_prometheus(self) -> str:
        """Format metrics for Prometheus."""
        lines = ["# Project Agent Metrics", f"# Generated: {datetime.utcnow().isoformat()}", ""]

        metrics = self.get_all_metrics()

        for metric in metrics:
            if metric.metric_type == "counter":
                lines.append(f"# TYPE {metric.name} counter")
            elif metric.metric_type == "gauge":
                lines.append(f"# TYPE {metric.name} gauge")
            elif metric.metric_type == "histogram":
                lines.append(f"# TYPE {metric.name} histogram")

            if metric.metric_type == "histogram":
                labels_str = self._format_labels(metric.labels)
                lines.append(f"{metric.name}{labels_str} {{le=\"{1.0}\"}} {sum(1 for v in self._histograms.get(self._make_key(metric.name, metric.labels), []) if v <= 1.0)}")
                lines.append(f"{metric.name}{labels_str} {{le=\"+Inf\"}} {len(self._histograms.get(self._make_key(metric.name, metric.labels), []))}")
            else:
                labels_str = self._format_labels(metric.labels)
                lines.append(f"{metric.name}{labels_str} {metric.value}")

        return "\n".join(lines)

    def _format_labels(self, labels: Dict[str, str]) -> str:
        """Format labels for Prometheus."""
        if not labels:
            return ""
        return "{" + ",".join(f'{k}="{v}"' for k, v in sorted(labels.items())) + "}"


class HealthChecker:
    """Checks health of application components."""

    def __init__(self):
        self._start_time = time.time()
        self._component_status: Dict[str, Dict[str, Any]] = {}

    def register_component(
        self,
        name: str,
        check_func: callable,
        critical: bool = True,
    ) -> None:
        """Register a component for health checks."""
        self._component_status[name] = {
            "check_func": check_func,
            "critical": critical,
            "last_check": None,
            "status": "unknown",
            "details": {},
        }

    async def check_all(self) -> Dict[str, Dict[str, Any]]:
        """Run all health checks."""
        results = {}

        for name, component in self._component_status.items():
            try:
                result = await component["check_func"]()
                component["last_check"] = datetime.utcnow()
                component["status"] = "healthy" if result.get("healthy", True) else "unhealthy"
                component["details"] = result
                results[name] = component.copy()
            except Exception as e:
                component["last_check"] = datetime.utcnow()
                component["status"] = "error"
                component["details"] = {"error": str(e)}
                results[name] = component.copy()

        return results

    def get_overall_status(self, results: Dict[str, Dict[str, Any]]) -> str:
        """Determine overall health status."""
        if not results:
            return "healthy"

        critical_unhealthy = [
            name for name, result in results.items()
            if result.get("critical") and result.get("status") in ["unhealthy", "error"]
        ]

        if critical_unhealthy:
            return "unhealthy"

        any_unhealthy = [
            name for name, result in results.items()
            if result.get("status") in ["unhealthy", "error"]
        ]

        if any_unhealthy:
            return "degraded"

        return "healthy"

    def get_health_status(self, version: str = "0.1.0") -> HealthStatus:
        """Get complete health status."""
        import asyncio

        results = asyncio.run(self.check_all())
        status = self.get_overall_status(results)

        uptime = time.time() - self._start_time

        return HealthStatus(
            status=status,
            version=version,
            uptime_seconds=uptime,
            components=results,
            timestamp=datetime.utcnow(),
        )


class UptimeMonitor:
    """Monitors application uptime and availability."""

    def __init__(self):
        self._start_time = time.time()
        self._last_downtime: Optional[datetime] = None
        self._total_downtime: float = 0.0
        self._checkpoints: List[Dict[str, Any]] = []

    def record_checkpoint(self, status: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Record an uptime checkpoint."""
        self._checkpoints.append({
            "timestamp": datetime.utcnow(),
            "status": status,
            "details": details or {},
        })

        if len(self._checkpoints) > 1000:
            self._checkpoints = self._checkpoints[-500:]

    def get_uptime_report(self) -> Dict[str, Any]:
        """Generate an uptime report."""
        now = datetime.utcnow()
        total_seconds = (now - datetime.fromtimestamp(self._start_time)).total_seconds()

        checkpoints = [c for c in self._checkpoints if c["status"] == "healthy"]
        healthy_count = len(checkpoints)
        total_checks = len(self._checkpoints)

        availability = (healthy_count / total_checks * 100) if total_checks > 0 else 100.0

        return {
            "started_at": datetime.fromtimestamp(self._start_time).isoformat(),
            "total_seconds": total_seconds,
            "total_checks": total_checks,
            "healthy_checks": healthy_count,
            "availability_percent": availability,
            "current_status": self._checkpoints[-1]["status"] if self._checkpoints else "unknown",
        }


metrics = MetricsCollector()
health_checker = HealthChecker()
uptime_monitor = UptimeMonitor()


def setup_default_checks() -> None:
    """Set up default health checks."""
    async def check_database():
        try:
            from ..core.database import Database
            db = Database()
            await db.connect()
            await db.close()
            return {"healthy": True, "message": "Database connected"}
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    async def check_github():
        try:
            from ..github import GitHubClient
            client = GitHubClient()
            rate = client.get_rate_limit_info()
            return {"healthy": True, "remaining": rate.remaining if rate else "unknown"}
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    async def check_openai():
        try:
            from ..openai import OpenAIClient
            client = OpenAIClient()
            usage = client.get_token_usage()
            return {"healthy": True, "tokens_used": usage.get("total_tokens", 0)}
        except Exception as e:
            return {"healthy": False, "message": str(e)}

    health_checker.register_component("database", check_database, critical=True)
    health_checker.register_component("github", check_github, critical=False)
    health_checker.register_component("openai", check_openai, critical=False)


setup_default_checks()
