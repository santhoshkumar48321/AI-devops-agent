"""
tests/test_api.py - Integration tests for the FastAPI routes.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def client():
    """Return a TestClient for the FastAPI app."""
    from fastapi.testclient import TestClient
    from api.routes import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# /ask endpoint
# ---------------------------------------------------------------------------

class TestAskEndpoint:
    def _mock_reasoning_result(self):
        from agent.planner import ExecutionPlan
        plan = ExecutionPlan(goal="test goal")
        return {
            "answer": "## Diagnosis\n\nRestart the pod.",
            "plan": plan,
            "exec_results": {},
            "rca_path": None,
            "memory_id": "abc123",
        }

    def test_ask_returns_answer(self, client):
        with patch("agent.reasoning.ReasoningEngine.reason", new=AsyncMock(return_value=self._mock_reasoning_result())):
            resp = client.post("/ask", json={"query": "Pod is crashing"})

        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert "memory_id" in data

    def test_ask_short_query_fails(self, client):
        resp = client.post("/ask", json={"query": "hi"})
        assert resp.status_code == 422

    def test_ask_missing_query_fails(self, client):
        resp = client.post("/ask", json={})
        assert resp.status_code == 422

    def test_ask_forbidden_role(self, client):
        with patch("agent.reasoning.ReasoningEngine.reason", new=AsyncMock(return_value=self._mock_reasoning_result())):
            resp = client.post("/ask", json={"query": "Pod crashing"}, headers={"X-Role": "unknown-role"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /runbook endpoint
# ---------------------------------------------------------------------------

class TestRunbookEndpoint:
    def test_runbook_dry_run(self, client):
        from agent.planner import ExecutionPlan, PlanStep, SafetyLevel

        plan = ExecutionPlan(
            goal="Restart failing pods",
            steps=[
                PlanStep(
                    index=1, description="Get pods", tool="kubernetes",
                    command="kubectl get pods", safety=SafetyLevel.READ_ONLY,
                )
            ],
        )
        with patch("agent.planner.Planner.create_runbook", new=AsyncMock(return_value=plan)), \
             patch("services.rca_generator.RCAGenerator.generate_runbook", return_value="/tmp/rb.md"):
            resp = client.post("/runbook", json={"task": "Restart failing pods", "dry_run": True})

        assert resp.status_code == 200
        data = resp.json()
        assert data["goal"] == "Restart failing pods"
        assert len(data["steps"]) == 1
        assert data["exec_results"] == {}  # dry run – no execution


# ---------------------------------------------------------------------------
# /diagnose endpoint
# ---------------------------------------------------------------------------

class TestDiagnoseEndpoint:
    def test_diagnose_returns_diagnosis(self, client):
        from agent.planner import ExecutionPlan

        plan = ExecutionPlan(goal="Diagnose pod crash")
        mock_result = {
            "answer": "## Root Cause\n\nOOMKill.",
            "plan": plan,
            "exec_results": {},
            "rca_path": "/tmp/rca.md",
            "memory_id": "xyz",
        }
        with patch("agent.reasoning.ReasoningEngine.reason", new=AsyncMock(return_value=mock_result)), \
             patch("tools.kubernetes_tool.KubernetesTool.get_pods", new=AsyncMock(return_value={"stdout": "", "stderr": "", "returncode": 0})), \
             patch("tools.kubernetes_tool.KubernetesTool.get_events", new=AsyncMock(return_value={"stdout": "", "stderr": "", "returncode": 0})):
            resp = client.post("/diagnose", json={"issue": "Pod is OOMKilled", "namespace": "default"})

        assert resp.status_code == 200
        data = resp.json()
        assert "diagnosis" in data
        assert "plan_summary" in data

    def test_diagnose_without_log_collection(self, client):
        from agent.planner import ExecutionPlan

        plan = ExecutionPlan(goal="Diagnose network")
        mock_result = {
            "answer": "Network issue.",
            "plan": plan,
            "exec_results": {},
            "rca_path": None,
            "memory_id": "m1",
        }
        with patch("agent.reasoning.ReasoningEngine.reason", new=AsyncMock(return_value=mock_result)):
            resp = client.post(
                "/diagnose",
                json={"issue": "Network latency high", "collect_logs": False},
            )

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# /memory endpoint
# ---------------------------------------------------------------------------

class TestMemoryEndpoint:
    def test_memory_returns_list(self, client):
        from agent.memory import MemoryEntry

        entries = [
            MemoryEntry(id="m1", query="pod crash", answer="restart"),
            MemoryEntry(id="m2", query="disk full", answer="delete logs"),
        ]
        with patch("agent.memory.AgentMemory.all_entries", return_value=entries):
            resp = client.get("/memory")

        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["entries"]) == 2
