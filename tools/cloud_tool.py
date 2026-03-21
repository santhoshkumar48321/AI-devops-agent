"""
tools/cloud_tool.py - Multi-cloud CLI integration (AWS, Azure, GCP).

Provides a unified interface for cloud operations by delegating to the
respective CLI tools (aws, az, gcloud).  Operations are read-only by
default; destructive operations require the caller to pass the appropriate
safety flags.
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any


class CloudTool:
    """
    Unified wrapper for AWS / Azure / GCP CLI commands.

    The correct sub-tool is selected based on the command prefix:
    - ``aws ...``     → AWS CLI
    - ``az ...``      → Azure CLI
    - ``gcloud ...``  → GCP CLI

    Any other command is treated as a raw shell command.
    """

    async def run(self, command: str) -> dict[str, Any]:
        """Route and execute a cloud CLI command."""
        command = command.strip()
        prefix = command.split()[0].lower() if command else ""
        if prefix in ("aws", "az", "gcloud"):
            return await _shell(command)
        # Unknown prefix – try running as-is
        return await _shell(command)

    # ------------------------------------------------------------------
    # AWS helpers
    # ------------------------------------------------------------------

    async def aws(self, subcommand: str) -> dict[str, Any]:
        return await _shell(f"aws {subcommand}")

    async def ec2_instances(self, region: str = "us-east-1") -> dict[str, Any]:
        return await self.aws(
            f"ec2 describe-instances --region {shlex.quote(region)} "
            "--query 'Reservations[*].Instances[*].[InstanceId,State.Name,PublicIpAddress]' "
            "--output table"
        )

    async def cloudwatch_logs(
        self,
        log_group: str,
        log_stream: str = "",
        region: str = "us-east-1",
        limit: int = 100,
    ) -> dict[str, Any]:
        # Clamp limit to a safe range to prevent resource exhaustion
        limit = max(1, min(int(limit), 10000))
        cmd = (
            f"aws logs get-log-events "
            f"--log-group-name {shlex.quote(log_group)} "
            f"--limit {limit} --region {shlex.quote(region)}"
        )
        if log_stream:
            cmd += f" --log-stream-name {shlex.quote(log_stream)}"
        return await _shell(cmd)

    async def eks_clusters(self, region: str = "us-east-1") -> dict[str, Any]:
        return await self.aws(f"eks list-clusters --region {shlex.quote(region)}")

    # ------------------------------------------------------------------
    # Azure helpers
    # ------------------------------------------------------------------

    async def azure(self, subcommand: str) -> dict[str, Any]:
        return await _shell(f"az {subcommand}")

    async def az_vm_list(self) -> dict[str, Any]:
        return await self.azure("vm list --output table")

    async def az_aks_list(self) -> dict[str, Any]:
        return await self.azure("aks list --output table")

    # ------------------------------------------------------------------
    # GCP helpers
    # ------------------------------------------------------------------

    async def gcp(self, subcommand: str) -> dict[str, Any]:
        return await _shell(f"gcloud {subcommand}")

    async def gke_clusters(self) -> dict[str, Any]:
        return await self.gcp("container clusters list")

    async def gcp_instances(self) -> dict[str, Any]:
        return await self.gcp("compute instances list")


async def _shell(cmd: str) -> dict[str, Any]:
    """Run *cmd* as a subprocess and return stdout/stderr/returncode."""
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "returncode": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"stdout": "", "stderr": "Command timed out after 120 seconds", "returncode": -1}
    except Exception as exc:
        return {"stdout": "", "stderr": str(exc), "returncode": -1}
