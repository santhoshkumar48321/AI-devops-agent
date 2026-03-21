"""
tests/test_agent.py - Unit tests for the agent modules.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# agent/planner.py
# ---------------------------------------------------------------------------

class TestPlanner:
    """Tests for the Planner class."""

    def test_parse_plan_valid_json(self):
        """Planner._parse_plan should correctly map JSON to ExecutionPlan."""
        from agent.planner import Planner, SafetyLevel

        planner = Planner()
        raw = json.dumps({
            "goal": "Restart failing pods",
            "steps": [
                {
                    "index": 1,
                    "description": "List pods",
                    "tool": "kubernetes",
                    "command": "kubectl get pods -n default",
                    "safety": "read_only",
                    "requires_confirmation": False,
                },
                {
                    "index": 2,
                    "description": "Delete failing pod",
                    "tool": "kubernetes",
                    "command": "kubectl delete pod my-pod -n default",
                    "safety": "destructive",
                    "requires_confirmation": True,
                },
            ],
        })
        plan = planner._parse_plan("Restart failing pods", raw)

        assert plan.goal == "Restart failing pods"
        assert len(plan.steps) == 2
        assert plan.steps[0].tool == "kubernetes"
        assert plan.steps[1].safety == SafetyLevel.DESTRUCTIVE
        assert plan.steps[1].requires_confirmation is True

    def test_parse_plan_invalid_json(self):
        """Planner._parse_plan should return an empty plan on bad JSON."""
        from agent.planner import Planner

        planner = Planner()
        plan = planner._parse_plan("some task", "NOT JSON AT ALL")
        assert plan.goal == "some task"
        assert plan.steps == []

    def test_parse_plan_markdown_fences(self):
        """Planner._parse_plan should strip markdown code fences."""
        from agent.planner import Planner

        planner = Planner()
        raw = "```json\n" + json.dumps({"goal": "g", "steps": []}) + "\n```"
        plan = planner._parse_plan("g", raw)
        assert plan.goal == "g"

    def test_plan_summary_format(self):
        """ExecutionPlan.summary() should produce a Markdown string."""
        from agent.planner import Planner, SafetyLevel

        planner = Planner()
        raw = json.dumps({
            "goal": "Diagnose high CPU",
            "steps": [
                {
                    "index": 1,
                    "description": "Check CPU",
                    "tool": "linux",
                    "command": "top -bn1",
                    "safety": "read_only",
                    "requires_confirmation": False,
                }
            ],
        })
        plan = planner._parse_plan("Diagnose high CPU", raw)
        summary = plan.summary()
        assert "Diagnose high CPU" in summary
        assert "top -bn1" in summary
        assert "read_only" in summary

    @pytest.mark.asyncio
    async def test_create_plan_calls_llm(self):
        """create_plan should call the LLM and return a plan."""
        from agent.planner import Planner

        mock_response = json.dumps({
            "goal": "List pods",
            "steps": [
                {
                    "index": 1,
                    "description": "Get pods",
                    "tool": "kubernetes",
                    "command": "kubectl get pods",
                    "safety": "read_only",
                    "requires_confirmation": False,
                }
            ],
        })

        planner = Planner()
        with patch.object(planner, "_call_llm", new=AsyncMock(return_value=mock_response)):
            plan = await planner.create_plan("List all pods")

        assert len(plan.steps) == 1
        assert plan.steps[0].command == "kubectl get pods"

    @pytest.mark.asyncio
    async def test_llm_fallback_on_error(self):
        """Planner._call_llm should return a fallback JSON on API error."""
        from agent.planner import Planner

        planner = Planner()
        # AsyncOpenAI is imported inside _call_llm, so patch the openai module attribute
        with patch("openai.AsyncOpenAI", side_effect=Exception("network error")):
            raw = await planner._call_llm("some task")

        data = json.loads(raw)
        assert "steps" in data
        assert len(data["steps"]) >= 1


# ---------------------------------------------------------------------------
# agent/executor.py
# ---------------------------------------------------------------------------

class TestExecutor:
    """Tests for the Executor class."""

    @pytest.mark.asyncio
    async def test_destructive_step_raises_without_confirm(self):
        """Executor should raise ConfirmationRequired for destructive steps."""
        from agent.executor import Executor, ConfirmationRequired
        from agent.planner import PlanStep, SafetyLevel

        executor = Executor(auto_confirm=False)
        step = PlanStep(
            index=1,
            description="Delete pod",
            tool="kubernetes",
            command="kubectl delete pod foo",
            safety=SafetyLevel.DESTRUCTIVE,
            requires_confirmation=True,
        )
        with pytest.raises(ConfirmationRequired):
            await executor.execute_step(step)

    @pytest.mark.asyncio
    async def test_destructive_step_passes_with_auto_confirm(self):
        """With auto_confirm=True, destructive steps should be executed."""
        from agent.executor import Executor
        from agent.planner import PlanStep, SafetyLevel

        executor = Executor(auto_confirm=True)
        step = PlanStep(
            index=1,
            description="Delete pod",
            tool="kubernetes",
            command="kubectl delete pod foo",
            safety=SafetyLevel.DESTRUCTIVE,
            requires_confirmation=True,
        )
        with patch("tools.kubernetes_tool.KubernetesTool.run", new=AsyncMock(return_value={"stdout": "deleted", "stderr": "", "returncode": 0})):
            result = await executor.execute_step(step)
        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_plan_returns_results_for_each_step(self):
        """execute_plan should return a result for every step."""
        from agent.executor import Executor
        from agent.planner import ExecutionPlan, PlanStep, SafetyLevel

        plan = ExecutionPlan(
            goal="Check pods",
            steps=[
                PlanStep(
                    index=1,
                    description="Get pods",
                    tool="kubernetes",
                    command="kubectl get pods",
                    safety=SafetyLevel.READ_ONLY,
                ),
            ],
        )
        executor = Executor(auto_confirm=False)
        mock_result = {"stdout": "pod-1   Running", "stderr": "", "returncode": 0}
        with patch("tools.kubernetes_tool.KubernetesTool.run", new=AsyncMock(return_value=mock_result)):
            results = await executor.execute_plan(plan)

        assert len(results) == 1
        key = next(iter(results))
        assert "Get pods" in key


# ---------------------------------------------------------------------------
# agent/memory.py
# ---------------------------------------------------------------------------

class TestAgentMemory:
    """Tests for the AgentMemory class."""

    def test_add_and_search(self, tmp_path):
        """Memory should store and retrieve entries."""
        import os
        os.environ["MEMORY_DIR"] = str(tmp_path / "memory")

        # Invalidate lru_cache so new env var is picked up
        from config import get_settings
        get_settings.cache_clear()

        from agent.memory import AgentMemory, MemoryEntry

        mem = AgentMemory()
        entry = MemoryEntry(id="e1", query="pod crash", answer="Restart the pod")
        mem.add(entry)

        results = mem.search("pod crashing")
        assert len(results) >= 1
        assert any(e.id == "e1" for e in results)

    def test_clear(self, tmp_path):
        """Memory.clear() should remove all entries."""
        import os
        os.environ["MEMORY_DIR"] = str(tmp_path / "memory2")
        from config import get_settings
        get_settings.cache_clear()

        from agent.memory import AgentMemory, MemoryEntry

        mem = AgentMemory()
        mem.add(MemoryEntry(id="e2", query="disk full", answer="Delete old logs"))
        mem.clear()
        assert mem.all_entries() == []

    def test_persistence(self, tmp_path):
        """Entries added should survive a new AgentMemory instance."""
        import os
        os.environ["MEMORY_DIR"] = str(tmp_path / "memory3")
        from config import get_settings
        get_settings.cache_clear()

        from agent.memory import AgentMemory, MemoryEntry

        mem1 = AgentMemory()
        mem1.add(MemoryEntry(id="e3", query="high memory", answer="Restart service"))

        mem2 = AgentMemory()
        ids = [e.id for e in mem2.all_entries()]
        assert "e3" in ids
