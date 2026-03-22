"""
tools/kubernetes_tool.py - Kubernetes integration via kubectl.

Wraps common kubectl operations and provides structured output.
Supports both direct command execution and pattern-matched convenience methods.
"""

from __future__ import annotations

import asyncio
import shlex
from typing import Any

from config import get_settings


class KubernetesTool:
    """
    Run kubectl commands and return structured results.

    All commands are executed as subprocesses; no Python k8s client is
    required so this works with any kubeconfig / cloud auth setup.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._env_extra: dict[str, str] = {}
        if self._settings.kubeconfig:
            self._env_extra["KUBECONFIG"] = self._settings.kubeconfig

    async def run(self, command: str) -> dict[str, Any]:
        """
        Execute a kubectl command string.

        Parameters
        ----------
        command:
            Full kubectl command, e.g. ``kubectl get pods -n default``
            or a short form like ``get pods -n default``.

        Returns
        -------
        dict with keys: stdout, stderr, returncode
        """
        if not command.startswith("kubectl"):
            command = f"kubectl {command}"
        return await _shell(command, env_extra=self._env_extra)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    async def get_pods(self, namespace: str = "default") -> dict[str, Any]:
        return await self.run(f"kubectl get pods -n {shlex.quote(namespace)} -o wide")

    async def describe_pod(self, pod: str, namespace: str = "default") -> dict[str, Any]:
        return await self.run(f"kubectl describe pod {shlex.quote(pod)} -n {shlex.quote(namespace)}")

    async def get_logs(
        self,
        pod: str,
        namespace: str = "default",
        container: str = "",
        tail: int = 100,
        previous: bool = False,
    ) -> dict[str, Any]:
        cmd = f"kubectl logs {shlex.quote(pod)} -n {shlex.quote(namespace)} --tail={int(tail)}"
        if container:
            cmd += f" -c {shlex.quote(container)}"
        if previous:
            cmd += " --previous"
        return await self.run(cmd)

    async def delete_pod(self, pod: str, namespace: str = "default") -> dict[str, Any]:
        """Delete (restart) a pod. Marked destructive - caller must gate."""
        return await self.run(f"kubectl delete pod {shlex.quote(pod)} -n {shlex.quote(namespace)}")

    async def get_events(self, namespace: str = "default") -> dict[str, Any]:
        return await self.run(
            f"kubectl get events -n {shlex.quote(namespace)} --sort-by='.lastTimestamp'"
        )

    async def get_node_status(self) -> dict[str, Any]:
        return await self.run("kubectl get nodes -o wide")

    async def top_pods(self, namespace: str = "default") -> dict[str, Any]:
        return await self.run(f"kubectl top pods -n {shlex.quote(namespace)}")

    async def rollout_status(self, resource: str, namespace: str = "default") -> dict[str, Any]:
        return await self.run(f"kubectl rollout status {shlex.quote(resource)} -n {shlex.quote(namespace)}")

    async def rollout_restart(self, resource: str, namespace: str = "default") -> dict[str, Any]:
        """Trigger a rolling restart. Destructive - caller must gate."""
        return await self.run(f"kubectl rollout restart {shlex.quote(resource)} -n {shlex.quote(namespace)}")


async def _shell(cmd: str, env_extra: dict[str, str] | None = None) -> dict[str, Any]:
    """Run *cmd* as a subprocess and return stdout/stderr/returncode."""
    import os
    env = {**os.environ, **(env_extra or {})}
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
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
