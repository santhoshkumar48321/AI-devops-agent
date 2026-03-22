"""
agent/executor.py - Executes plans produced by the Planner.

Responsibilities:
- Route each PlanStep to the correct tool
- Enforce safety gates (confirmation for destructive actions)
- Write an audit log entry for every action taken
- Return structured results keyed by step description
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from agent.planner import ExecutionPlan, PlanStep, SafetyLevel
from config import get_settings

logger = logging.getLogger(__name__)


class ConfirmationRequired(Exception):
    """Raised when a destructive action requires human confirmation."""


class Executor:
    """
    Executes an ExecutionPlan step-by-step.

    Each step is routed to the appropriate tool module.  Destructive steps
    are skipped with a ConfirmationRequired exception unless
    *auto_confirm=True* is passed (only for non-interactive API usage with
    explicit user consent).
    """

    def __init__(self, auto_confirm: bool = False) -> None:
        self._settings = get_settings()
        self._auto_confirm = auto_confirm
        self._audit_path = Path(self._settings.audit_log_path)
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

    async def execute_plan(self, plan: ExecutionPlan) -> dict[str, Any]:
        """
        Execute all steps in *plan*.

        Returns a dict mapping step descriptions to their output/result.
        """
        results: dict[str, Any] = {}

        for step in plan.steps:
            result = await self._execute_step(step)
            results[f"Step {step.index}: {step.description}"] = result
            self._audit(plan.goal, step, result)

        return results

    async def execute_step(self, step: PlanStep) -> Any:
        """Public single-step execution (used by the API)."""
        return await self._execute_step(step)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _execute_step(self, step: PlanStep) -> Any:
        # Safety gate
        if step.safety == SafetyLevel.DESTRUCTIVE and not self._auto_confirm:
            if self._settings.require_confirmation:
                raise ConfirmationRequired(
                    f"Step '{step.description}' is destructive. "
                    "Set auto_confirm=True or confirm via the API to proceed."
                )

        tool = step.tool.lower()
        try:
            if tool == "kubernetes":
                from tools.kubernetes_tool import KubernetesTool
                return await KubernetesTool().run(step.command)
            elif tool == "ansible":
                from tools.ansible_tool import AnsibleTool
                return await AnsibleTool().run(step.command)
            elif tool == "linux":
                from tools.linux_tool import LinuxTool
                return await LinuxTool().run(step.command)
            elif tool == "cloud":
                from tools.cloud_tool import CloudTool
                return await CloudTool().run(step.command)
            else:
                # Default: run as a shell command
                from tools.linux_tool import LinuxTool
                return await LinuxTool().run(step.command)
        except ConfirmationRequired:
            raise
        except Exception as exc:
            logger.error("Step %d failed: %s", step.index, exc)
            return {"error": str(exc), "step": step.description}

    def _audit(self, goal: str, step: PlanStep, result: Any) -> None:
        """Append an audit log entry to the configured audit log file."""
        import datetime
        entry = {
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "goal": goal,
            "step_index": step.index,
            "step_description": step.description,
            "tool": step.tool,
            "command": step.command,
            "safety": step.safety.value,
            "result_summary": str(result)[:500],
        }
        with open(self._audit_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
