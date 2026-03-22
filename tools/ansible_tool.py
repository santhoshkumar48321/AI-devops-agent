"""
tools/ansible_tool.py - Ansible integration via ansible-runner.

Allows the agent to run Ansible playbooks, ad-hoc commands, and roles
as part of automated remediation workflows.
"""

from __future__ import annotations

import asyncio
import shlex
import os
import tempfile
from pathlib import Path
from typing import Any

from config import get_settings


class AnsibleTool:
    """
    Execute Ansible playbooks and ad-hoc commands via ansible-runner.

    When ansible-runner is not installed or the playbook directory is not
    configured, falls back to a shell ``ansible`` / ``ansible-playbook``
    invocation so the agent remains functional.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._private_data_dir = Path(self._settings.ansible_private_data_dir)
        self._private_data_dir.mkdir(parents=True, exist_ok=True)

    async def run(self, command: str) -> dict[str, Any]:
        """
        Run an Ansible command string.

        Supports:
        - ``ansible-playbook <playbook>`` or just ``<playbook.yml>``
        - ``ansible -m <module> -a <args> <hosts>``
        """
        command = command.strip()
        if command.endswith(".yml") or command.endswith(".yaml"):
            return await self.run_playbook(command)
        return await self._run_shell(command)

    async def run_playbook(
        self,
        playbook: str,
        inventory: str = "localhost,",
        extra_vars: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Run an Ansible playbook using ansible-runner if available,
        otherwise fall back to ansible-playbook CLI.
        """
        try:
            import ansible_runner  # type: ignore

            r = await asyncio.to_thread(
                ansible_runner.run,
                private_data_dir=str(self._private_data_dir),
                playbook=playbook,
                inventory=inventory,
                extravars=extra_vars or {},
                quiet=True,
            )
            return {
                "status": r.status,
                "rc": r.rc,
                "stdout": "\n".join(r.stdout.read().splitlines()),
                "stderr": "",
                "stats": r.stats,
            }
        except ImportError:
            cmd = f"ansible-playbook {shlex.quote(playbook)}"
            if inventory:
                cmd += f" -i {shlex.quote(inventory)}"
            if extra_vars:
                ev = " ".join(f"{shlex.quote(k)}={shlex.quote(str(v))}" for k, v in extra_vars.items())
                cmd += f" -e {shlex.quote(ev)}"
            return await self._run_shell(cmd)

    async def run_adhoc(
        self,
        hosts: str,
        module: str,
        args: str = "",
        inventory: str = "localhost,",
    ) -> dict[str, Any]:
        """Run an Ansible ad-hoc command."""
        cmd = f"ansible {shlex.quote(hosts)} -i {shlex.quote(inventory)} -m {shlex.quote(module)}"
        if args:
            cmd += f" -a {shlex.quote(args)}"
        return await self._run_shell(cmd)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_shell(self, cmd: str) -> dict[str, Any]:
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            return {
                "status": "successful" if proc.returncode == 0 else "failed",
                "rc": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        except asyncio.TimeoutError:
            return {"status": "timeout", "rc": -1, "stdout": "", "stderr": "Timed out after 300s"}
        except Exception as exc:
            return {"status": "error", "rc": -1, "stdout": "", "stderr": str(exc)}
