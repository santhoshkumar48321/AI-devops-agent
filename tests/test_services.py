"""
tests/test_services.py - Unit tests for service modules.
"""

import os
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# services/log_parser.py
# ---------------------------------------------------------------------------

class TestLogParser:
    """Tests for LogParser."""

    def test_parse_detects_crash_loop(self):
        """Parser should detect CrashLoopBackOff pattern."""
        from services.log_parser import LogParser

        parser = LogParser()
        log = "Pod my-app-123 is in CrashLoopBackOff state after 5 restarts."
        result = parser.parse(log, source="kubectl")

        assert any(m.pattern_name == "CrashLoopBackOff" for m in result.matches)
        assert result.has_critical_errors

    def test_parse_detects_oom(self):
        """Parser should detect OOMKill."""
        from services.log_parser import LogParser

        parser = LogParser()
        result = parser.parse("Container OOMKilled due to memory limit", source="k8s")
        assert any(m.pattern_name == "OOMKill" for m in result.matches)
        assert result.has_critical_errors

    def test_parse_no_errors(self):
        """Parser should produce no matches for clean logs."""
        from services.log_parser import LogParser

        parser = LogParser()
        result = parser.parse("2024-01-01 INFO Application started successfully")
        assert result.matches == []
        assert not result.has_critical_errors

    def test_parse_counts_errors_and_warnings(self):
        """Parser should count error and warning lines correctly."""
        from services.log_parser import LogParser

        parser = LogParser()
        log = "\n".join([
            "INFO normal log",
            "ERROR something bad happened",
            "WARN disk almost full",
            "WARN another warning",
            "FATAL process died",
        ])
        result = parser.parse(log)
        assert result.error_count >= 2  # ERROR + FATAL
        assert result.warning_count >= 2

    def test_parse_image_pull_error(self):
        """Parser should detect ImagePullBackOff."""
        from services.log_parser import LogParser

        parser = LogParser()
        result = parser.parse("Failed to pull image: ImagePullBackOff")
        assert any(m.pattern_name == "ImagePullError" for m in result.matches)

    def test_parse_kubectl_output(self):
        """parse_kubectl_output should handle the tool output dict format."""
        from services.log_parser import LogParser

        parser = LogParser()
        output = {"stdout": "pod-abc   CrashLoopBackOff   5", "stderr": ""}
        result = parser.parse_kubectl_output(output)
        assert any(m.pattern_name == "CrashLoopBackOff" for m in result.matches)

    def test_top_errors_ordered_by_frequency(self):
        """top_errors should list the most frequent pattern first."""
        from services.log_parser import LogParser

        parser = LogParser()
        log = "\n".join([
            "OOMKilled",
            "CrashLoopBackOff",
            "OOMKilled",
            "OOMKilled",
        ])
        result = parser.parse(log)
        assert result.top_errors[0] == "OOMKill"

    def test_extract_stack_traces_python(self):
        """extract_stack_traces should find Python tracebacks."""
        from services.log_parser import LogParser

        parser = LogParser()
        log = (
            "Traceback (most recent call last):\n"
            "  File 'app.py', line 10, in main\n"
            "    raise ValueError('oops')\n"
            "ValueError: oops\n"
            "Normal log line\n"
        )
        traces = parser.extract_stack_traces(log)
        assert len(traces) >= 1
        assert "ValueError" in traces[0]

    def test_summary_no_errors(self):
        """Summary should mention no patterns when log is clean."""
        from services.log_parser import LogParser

        parser = LogParser()
        result = parser.parse("Everything is fine", source="myapp")
        assert "No known error patterns" in result.summary


# ---------------------------------------------------------------------------
# services/metrics_analyzer.py
# ---------------------------------------------------------------------------

class TestMetricsAnalyzer:
    """Tests for MetricsAnalyzer."""

    def test_no_alerts_when_within_thresholds(self):
        """No alerts should be produced for healthy metrics."""
        from services.metrics_analyzer import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        report = analyzer.analyze({"cpu_percent": 40.0, "memory_percent": 50.0})
        assert len(report.alerts) == 0
        assert not report.has_critical

    def test_warning_alert(self):
        """A warning alert should be triggered at 75% memory."""
        from services.metrics_analyzer import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        report = analyzer.analyze({"memory_percent": 80.0})
        assert any(a.severity == "warning" for a in report.alerts)

    def test_critical_alert(self):
        """A critical alert should be triggered at 95% disk."""
        from services.metrics_analyzer import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        report = analyzer.analyze({"disk_percent": 95.0})
        assert report.has_critical
        assert any(a.severity == "critical" for a in report.alerts)

    def test_unknown_metric_ignored(self):
        """Unknown metrics should not produce alerts."""
        from services.metrics_analyzer import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        report = analyzer.analyze({"some_unknown_metric": 999.0})
        assert len(report.alerts) == 0

    def test_detect_trend_rising(self):
        """Trend detection should identify rising series."""
        from services.metrics_analyzer import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        assert analyzer.detect_trend([10, 15, 20, 30, 45]) == "rising"

    def test_detect_trend_falling(self):
        """Trend detection should identify falling series."""
        from services.metrics_analyzer import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        assert analyzer.detect_trend([80, 70, 60, 50, 40]) == "falling"

    def test_detect_trend_stable(self):
        """Trend detection should identify a stable series."""
        from services.metrics_analyzer import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        assert analyzer.detect_trend([50, 51, 50, 49, 50]) == "stable"

    def test_detect_trend_single_value(self):
        """Trend detection should return stable for a single value."""
        from services.metrics_analyzer import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        assert analyzer.detect_trend([42]) == "stable"

    def test_summary_has_critical_icon(self):
        """Summary should contain 🔴 for critical alerts."""
        from services.metrics_analyzer import MetricsAnalyzer

        analyzer = MetricsAnalyzer()
        report = analyzer.analyze({"cpu_percent": 95.0})
        assert "🔴" in report.summary


# ---------------------------------------------------------------------------
# services/rca_generator.py
# ---------------------------------------------------------------------------

class TestRCAGenerator:
    """Tests for RCAGenerator."""

    def test_generate_creates_file(self, tmp_path):
        """generate() should create a Markdown file."""
        import asyncio
        os.environ["DOCS_OUTPUT_DIR"] = str(tmp_path)
        from config import get_settings
        get_settings.cache_clear()

        from services.rca_generator import RCAGenerator

        gen = RCAGenerator()
        path = asyncio.get_event_loop().run_until_complete(
            gen.generate(
                issue="Pod crashing in namespace X",
                diagnosis="CrashLoopBackOff due to OOMKill",
                plan_summary="1. Get logs\n2. Delete pod",
            )
        )
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "Pod crashing in namespace X" in content
        assert "CrashLoopBackOff" in content

    def test_generate_includes_exec_results(self, tmp_path):
        """generate() should include execution results in the doc."""
        import asyncio
        os.environ["DOCS_OUTPUT_DIR"] = str(tmp_path)
        from config import get_settings
        get_settings.cache_clear()

        from services.rca_generator import RCAGenerator

        gen = RCAGenerator()
        path = asyncio.get_event_loop().run_until_complete(
            gen.generate(
                issue="High memory usage",
                diagnosis="Memory leak in app",
                plan_summary="Restart service",
                exec_results={"Step 1: Restart": "service restarted"},
            )
        )
        content = Path(path).read_text()
        assert "Execution Results" in content
        assert "service restarted" in content

    def test_generate_runbook_creates_file(self, tmp_path):
        """generate_runbook() should create a runbook Markdown file."""
        os.environ["DOCS_OUTPUT_DIR"] = str(tmp_path)
        from config import get_settings
        get_settings.cache_clear()

        from services.rca_generator import RCAGenerator

        gen = RCAGenerator()
        path = gen.generate_runbook(
            task="Restart failing pods",
            steps=["kubectl get pods", "kubectl delete pod foo"],
        )
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "kubectl get pods" in content

    def test_slugify(self):
        """_slugify should produce safe filesystem names."""
        from services.rca_generator import _slugify

        assert _slugify("Pod is crashing!") == "pod_is_crashing"
        assert _slugify("  High CPU @ 95%  ") == "high_cpu_95"
        assert len(_slugify("a" * 100)) <= 40
