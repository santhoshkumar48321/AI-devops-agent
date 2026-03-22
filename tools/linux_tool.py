"""
tools/linux_tool.py - Linux system diagnostics and remediation.

Provides helpers for:
- System resource inspection (CPU, memory, disk, network)
- Service management (systemd)
- Log retrieval (journalctl, /var/log/*)
- Process management
- General shell command execution
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any


class LinuxTool:
    """
    Execute Linux diagnostic and remediation commands.

    All commands run as subprocesses on the local machine.
    Remote execution should be delegated to the AnsibleTool.
    """

    async def run(self, command: str) -> dict[str, Any]:
        """Execute an arbitrary shell command and return structured output."""
        return await _shell(command)

    # ------------------------------------------------------------------
    # Diagnostic helpers
    # ------------------------------------------------------------------

    async def cpu_usage(self) -> dict[str, Any]:
        """Return top CPU consumers."""
        return await _shell("ps aux --sort=-%cpu | head -20")

    async def memory_usage(self) -> dict[str, Any]:
        """Return memory usage summary."""
        return await _shell("free -h && echo '---' && ps aux --sort=-%mem | head -10")

    async def disk_usage(self) -> dict[str, Any]:
        """Return disk usage per mount point."""
        return await _shell("df -h")

    async def network_connections(self) -> dict[str, Any]:
        """Return active network connections and listening ports."""
        return await _shell("ss -tulnp 2>/dev/null || netstat -tulnp 2>/dev/null")

    async def service_status(self, service: str) -> dict[str, Any]:
        """Return systemd service status."""
        return await _shell(f"systemctl status {shlex.quote(service)} --no-pager -l")

    async def journalctl(
        self,
        service: str = "",
        lines: int = 100,
        since: str = "1 hour ago",
    ) -> dict[str, Any]:
        """Retrieve journal logs, optionally filtered by service."""
        cmd = f"journalctl --no-pager -n {lines} --since '{since}'"
        if service:
            cmd += f" -u {shlex.quote(service)}"
        return await _shell(cmd)

    async def tail_log(self, path: str, lines: int = 100) -> dict[str, Any]:
        """Tail a log file."""
        safe_path = shlex.quote(path)
        return await _shell(f"tail -n {lines} {safe_path}")

    async def restart_service(self, service: str) -> dict[str, Any]:
        """Restart a systemd service. Caller must enforce safety gate."""
        return await _shell(f"systemctl restart {shlex.quote(service)}")

    async def kill_process(self, pid: int, signal: str = "TERM") -> dict[str, Any]:
        """Send *signal* to *pid*. Caller must enforce safety gate."""
        return await _shell(f"kill -{signal} {int(pid)}")

    async def uptime(self) -> dict[str, Any]:
        return await _shell("uptime")

    async def load_average(self) -> dict[str, Any]:
        return await _shell("cat /proc/loadavg")


async def _shell(cmd: str) -> dict[str, Any]:
    """Run *cmd* as a subprocess and return stdout/stderr/returncode."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "returncode": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"stdout": "", "stderr": "Command timed out after 60 seconds", "returncode": -1}
    except Exception as exc:
        return {"stdout": "", "stderr": str(exc), "returncode": -1}
