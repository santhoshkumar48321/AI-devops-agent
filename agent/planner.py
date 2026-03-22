"""
agent/planner.py - Task planner that converts natural language into structured execution plans.

The planner uses an LLM to:
1. Understand the intent of a DevOps request
2. Break it into ordered, executable steps
3. Annotate each step with the appropriate tool and safety level
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from config import get_settings


class SafetyLevel(str, Enum):
    """Risk classification for a plan step."""
    READ_ONLY = "read_only"       # Safe: only reads state
    MODIFYING = "modifying"       # Changes state but reversible
    DESTRUCTIVE = "destructive"   # Deletes/restarts resources - requires confirmation


@dataclass
class PlanStep:
    """A single step in an execution plan."""
    index: int
    description: str
    tool: str                          # e.g. "kubernetes", "linux", "ansible", "shell"
    command: str                       # concrete command / action string
    safety: SafetyLevel = SafetyLevel.READ_ONLY
    requires_confirmation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """Ordered list of steps produced by the planner."""
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    raw_llm_response: str = ""

    def requires_confirmation(self) -> bool:
        return any(s.requires_confirmation for s in self.steps)

    def summary(self) -> str:
        lines = [f"**Goal:** {self.goal}", ""]
        for s in self.steps:
            risk = f"[{s.safety.value}]"
            lines.append(f"{s.index}. `{s.command}` {risk} — {s.description}")
        return "\n".join(lines)


# System prompt that instructs the LLM how to produce plans
_PLANNER_SYSTEM_PROMPT = """
You are a senior DevOps engineer and AI planning assistant.
Given a user's DevOps task or issue description, produce a structured JSON execution plan.

Return ONLY valid JSON with this schema:
{
  "goal": "<one-line goal>",
  "steps": [
    {
      "index": 1,
      "description": "<human description>",
      "tool": "<kubernetes|linux|ansible|cloud|shell>",
      "command": "<exact command or action>",
      "safety": "<read_only|modifying|destructive>",
      "requires_confirmation": <true|false>
    }
  ]
}

Rules:
- Mark any delete/restart/drain/terminate action as "destructive" and set requires_confirmation=true
- Mark patch/update/apply as "modifying"
- Mark get/describe/logs/status as "read_only"
- Always start with diagnostic read_only steps before any modifying steps
- Prefer kubectl/ansible/bash over cloud CLI where possible
""".strip()


class Planner:
    """
    Converts natural language DevOps tasks into structured ExecutionPlans.
    Uses an LLM (OpenAI) for intelligent step generation.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def create_plan(self, task: str, context: str = "") -> ExecutionPlan:
        """Generate an ExecutionPlan for *task* with optional extra *context*."""
        prompt = task
        if context:
            prompt = f"{task}\n\nContext:\n{context}"

        raw = await self._call_llm(prompt)
        return self._parse_plan(task, raw)

    async def create_runbook(self, task: str) -> ExecutionPlan:
        """Alias for create_plan; used by the runbook CLI command."""
        return await self.create_plan(task)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        """Call the OpenAI chat API and return the raw text response."""
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self._settings.openai_api_key)
            response = await client.chat.completions.create(
                model=self._settings.openai_model,
                messages=[
                    {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=1500,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            # Return a minimal fallback plan so the agent remains functional
            return json.dumps({
                "goal": prompt,
                "steps": [
                    {
                        "index": 1,
                        "description": f"LLM unavailable ({exc}). Manual intervention required.",
                        "tool": "shell",
                        "command": "echo 'LLM unavailable'",
                        "safety": "read_only",
                        "requires_confirmation": False,
                    }
                ],
            })

    def _parse_plan(self, task: str, raw: str) -> ExecutionPlan:
        """Parse raw LLM JSON output into an ExecutionPlan."""
        # Strip markdown code fences if present
        json_str = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            data = {"goal": task, "steps": []}

        steps = [
            PlanStep(
                index=s.get("index", i + 1),
                description=s.get("description", ""),
                tool=s.get("tool", "shell"),
                command=s.get("command", ""),
                safety=SafetyLevel(s.get("safety", "read_only")),
                requires_confirmation=bool(s.get("requires_confirmation", False)),
                metadata=s.get("metadata", {}),
            )
            for i, s in enumerate(data.get("steps", []))
        ]

        return ExecutionPlan(
            goal=data.get("goal", task),
            steps=steps,
            raw_llm_response=raw,
        )
