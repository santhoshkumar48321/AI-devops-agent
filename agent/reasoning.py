"""
agent/reasoning.py - High-level reasoning engine: the "brain" of the DevOps agent.

Implements the Plan → Execute → Observe → Improve loop:
1. Retrieve relevant memories
2. Ask LLM to analyse the issue and produce an answer + execution plan
3. Optionally execute the plan
4. Store the interaction in memory
5. Generate an RCA document if an incident was handled
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from agent.memory import AgentMemory, MemoryEntry
from agent.planner import Planner
from config import get_settings

logger = logging.getLogger(__name__)

# System prompt for the reasoning / diagnosis pass
_REASONING_SYSTEM_PROMPT = """
You are an expert DevOps engineer and SRE (Site Reliability Engineer).
Your job is to help diagnose infrastructure issues, provide root cause analysis,
and suggest concrete fixes.

When answering:
1. Summarise the likely root cause in 1-2 sentences
2. Provide a numbered step-by-step remediation guide
3. Note any risks or caveats
4. If the issue is Kubernetes-related, include relevant kubectl commands
5. Format your response in Markdown

Be concise but complete. Prefer actionable steps over theory.
""".strip()


class ReasoningEngine:
    """
    Orchestrates the full Plan → Execute → Observe → Improve loop.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._memory = AgentMemory()
        self._planner = Planner()

    async def reason(
        self,
        query: str,
        auto_fix: bool = False,
        auto_confirm: bool = False,
    ) -> dict[str, Any]:
        """
        Main entry point.

        Parameters
        ----------
        query:
            Natural language DevOps question or issue description.
        auto_fix:
            If True, execute the generated plan automatically.
        auto_confirm:
            If True, skip confirmation for destructive steps (use with care).

        Returns
        -------
        dict with keys:
            answer      - Markdown-formatted diagnosis/answer
            plan        - ExecutionPlan object
            exec_results - Step results if auto_fix=True, else {}
            rca_path    - Path to generated RCA doc (str or None)
            memory_id   - ID of stored memory entry
        """
        # 1. Retrieve relevant past incidents
        past = self._memory.search(query)
        context = self._build_context(past)

        # 2. Generate a natural-language answer (diagnosis)
        answer = await self._ask_llm(query, context)

        # 3. Build an execution plan
        plan = await self._planner.create_plan(query, context=context)

        # 4. Optionally execute
        exec_results: dict[str, Any] = {}
        if auto_fix:
            from agent.executor import Executor
            executor = Executor(auto_confirm=auto_confirm)
            exec_results = await executor.execute_plan(plan)

        # 5. Generate RCA if execution happened or it looks like an incident
        rca_path: str | None = None
        if exec_results or _is_incident(query):
            from services.rca_generator import RCAGenerator
            rca_gen = RCAGenerator()
            rca_path = await rca_gen.generate(
                issue=query,
                diagnosis=answer,
                plan_summary=plan.summary(),
                exec_results=exec_results,
            )

        # 6. Store in memory
        entry_id = str(uuid.uuid4())
        self._memory.add(
            MemoryEntry(
                id=entry_id,
                query=query,
                answer=answer,
                metadata={
                    "plan_goal": plan.goal,
                    "auto_fix": auto_fix,
                    "rca_path": rca_path,
                },
                timestamp=time.time(),
            )
        )

        return {
            "answer": answer,
            "plan": plan,
            "exec_results": exec_results,
            "rca_path": rca_path,
            "memory_id": entry_id,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ask_llm(self, query: str, context: str) -> str:
        """Send a query + context to the LLM and return the Markdown answer."""
        user_msg = query
        if context:
            user_msg = f"{query}\n\n---\nRelevant past incidents:\n{context}"
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self._settings.openai_api_key)
            response = await client.chat.completions.create(
                model=self._settings.openai_model,
                messages=[
                    {"role": "system", "content": _REASONING_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=2000,
            )
            return response.choices[0].message.content or "No response from LLM."
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return (
                f"## LLM Unavailable\n\nCould not reach OpenAI API: `{exc}`\n\n"
                "Please check your `OPENAI_API_KEY` and network connectivity."
            )

    @staticmethod
    def _build_context(entries: list[MemoryEntry]) -> str:
        if not entries:
            return ""
        parts = []
        for e in entries[-3:]:  # Use at most 3 recent relevant memories
            parts.append(f"**Past query:** {e.query}\n**Answer:** {e.answer[:300]}...")
        return "\n\n".join(parts)


def _is_incident(query: str) -> bool:
    """Heuristic: does this query describe an incident that needs an RCA?"""
    keywords = [
        "crash", "crashing", "down", "error", "fail", "failing", "failed",
        "outage", "unavailable", "restart", "oom", "kill", "evict",
        "high cpu", "high memory", "disk full", "timeout", "latency",
    ]
    q = query.lower()
    return any(kw in q for kw in keywords)
