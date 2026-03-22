"""
services/log_parser.py - Log analysis and pattern extraction.

Parses logs from various sources (kubectl, journalctl, file tails)
and extracts meaningful signals:
- Error patterns
- Stack traces
- OOMKill / CrashLoopBackOff indicators
- Frequency analysis
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# Common error pattern definitions
_ERROR_PATTERNS: list[tuple[str, str]] = [
    (r"OOMKilled|OOM|Out of memory|Killed process", "OOMKill"),
    (r"CrashLoopBackOff", "CrashLoopBackOff"),
    (r"ImagePullBackOff|ErrImagePull|image.*not found", "ImagePullError"),
    (r"ConnectionRefused|connection refused", "ConnectionRefused"),
    (r"Readiness probe failed|Liveness probe failed", "ProbeFailure"),
    (r"Pending.*Insufficient|Insufficient (cpu|memory)", "ResourceInsufficient"),
    (r"Error: (.*)", "GenericError"),
    (r"FATAL|CRITICAL|PANIC|panic:", "FatalError"),
    (r"Exception|Traceback|Error:|ERROR:", "ApplicationError"),
    (r"disk.*full|no space left|ENOSPC", "DiskFull"),
    (r"timeout|timed out|ETIMEDOUT", "Timeout"),
    (r"permission denied|EACCES|forbidden|403", "PermissionDenied"),
    (r"certificate.*expired|x509:", "CertificateError"),
]


@dataclass
class LogMatch:
    """A single pattern match found in a log."""
    pattern_name: str
    line: str
    line_number: int


@dataclass
class LogAnalysisResult:
    """Result of analysing one or more log blocks."""
    matches: list[LogMatch] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    top_errors: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def has_critical_errors(self) -> bool:
        critical = {"OOMKill", "CrashLoopBackOff", "FatalError", "DiskFull"}
        return any(m.pattern_name in critical for m in self.matches)


class LogParser:
    """
    Analyse log text and produce structured LogAnalysisResult objects.
    """

    def parse(self, log_text: str, source: str = "unknown") -> LogAnalysisResult:
        """
        Parse *log_text* and return a LogAnalysisResult.

        Parameters
        ----------
        log_text:
            Raw log content as a single string.
        source:
            Label for the log source (e.g. pod name, service name).
        """
        result = LogAnalysisResult()
        lines = log_text.splitlines()

        for i, line in enumerate(lines, start=1):
            # Count warnings and errors by log level keywords
            lower = line.lower()
            if any(kw in lower for kw in ("error", "fatal", "critical", "panic")):
                result.error_count += 1
            elif any(kw in lower for kw in ("warn", "warning")):
                result.warning_count += 1

            # Check for known patterns
            for pattern, name in _ERROR_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    result.matches.append(LogMatch(pattern_name=name, line=line.strip(), line_number=i))
                    break  # Only match one pattern per line

        # Build top_errors list (deduplicated, most frequent first)
        freq: dict[str, int] = {}
        for m in result.matches:
            freq[m.pattern_name] = freq.get(m.pattern_name, 0) + 1
        result.top_errors = sorted(freq, key=lambda k: -freq[k])

        result.summary = self._build_summary(source, result, freq)
        return result

    def parse_kubectl_output(self, output: dict[str, Any]) -> LogAnalysisResult:
        """Parse the output dict returned by KubernetesTool."""
        text = output.get("stdout", "") + "\n" + output.get("stderr", "")
        return self.parse(text, source="kubectl")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_summary(source: str, result: LogAnalysisResult, freq: dict[str, int]) -> str:
        if not result.matches:
            return f"No known error patterns detected in logs from `{source}`."

        parts = [f"**Log analysis for `{source}`:**"]
        parts.append(f"- Total errors: {result.error_count}")
        parts.append(f"- Total warnings: {result.warning_count}")
        if freq:
            top = ", ".join(f"`{k}` ({v}x)" for k, v in list(freq.items())[:5])
            parts.append(f"- Detected patterns: {top}")
        if result.has_critical_errors:
            parts.append("\n⚠️ **Critical errors detected** — immediate attention required.")
        return "\n".join(parts)

    def extract_stack_traces(self, log_text: str) -> list[str]:
        """
        Extract Python / Java / Go stack traces from log text.

        Returns a list of trace strings.
        """
        traces: list[str] = []
        # Python traceback
        py_pattern = re.compile(
            r"(Traceback \(most recent call last\):.*?)(?=\n\S|\Z)", re.DOTALL
        )
        traces.extend(m.group(0) for m in py_pattern.finditer(log_text))
        # Generic "at " Java-style traces
        java_block: list[str] = []
        for line in log_text.splitlines():
            if re.match(r"\s+at [\w.$]+\(", line):
                java_block.append(line)
            else:
                if java_block:
                    traces.append("\n".join(java_block))
                    java_block = []
        return traces
