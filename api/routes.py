"""
api/routes.py - FastAPI application with DevOps agent endpoints.

Endpoints:
  POST /ask       - Natural language DevOps question
  POST /runbook   - Generate (and optionally execute) a runbook
  POST /diagnose  - Diagnose a specific issue
  GET  /health    - Health check
  GET  /memory    - List stored incidents
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Header, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import get_settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI DevOps Agent",
    description=(
        "Production-grade AI-powered DevOps assistant. "
        "Troubleshoot, diagnose, and automate infrastructure operations."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    query: str = Field(..., description="Natural language DevOps question", min_length=3)
    auto_fix: bool = Field(False, description="Attempt automatic remediation")
    auto_confirm: bool = Field(
        False, description="Skip confirmation for destructive steps (use with care)"
    )


class AskResponse(BaseModel):
    answer: str
    plan_summary: str
    exec_results: dict[str, Any] = {}
    rca_path: str | None = None
    memory_id: str


class RunbookRequest(BaseModel):
    task: str = Field(..., description="Task description, e.g. 'Restart failing pods'", min_length=3)
    dry_run: bool = Field(True, description="If False, execute the generated runbook steps")
    auto_confirm: bool = Field(False, description="Skip confirmation for destructive steps")


class RunbookResponse(BaseModel):
    goal: str
    steps: list[dict[str, Any]]
    exec_results: dict[str, Any] = {}
    runbook_path: str | None = None


class DiagnoseRequest(BaseModel):
    issue: str = Field(..., description="Issue description", min_length=3)
    namespace: str = Field("default", description="Kubernetes namespace")
    collect_logs: bool = Field(True, description="Collect kubectl logs as part of diagnosis")


class DiagnoseResponse(BaseModel):
    diagnosis: str
    log_analysis: dict[str, Any] = {}
    metrics_summary: str = ""
    plan_summary: str
    rca_path: str | None = None


# ---------------------------------------------------------------------------
# RBAC helper
# ---------------------------------------------------------------------------

def _check_role(x_role: str | None) -> None:
    """Validate the caller's role against the allowlist."""
    settings = get_settings()
    if not x_role:
        # No role header supplied – allow in development, restrict in prod
        return
    if x_role not in settings.allowed_roles_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{x_role}' is not authorised. Allowed: {settings.allowed_roles_list}",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health() -> dict[str, str]:
    """Simple liveness check."""
    return {"status": "ok", "service": "AI DevOps Agent"}


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask(
    body: AskRequest,
    x_role: str | None = Header(None, alias="X-Role"),
) -> AskResponse:
    """
    Ask the AI DevOps agent a natural language question.

    The agent will:
    1. Search past incidents for context
    2. Diagnose the issue using an LLM
    3. Generate a structured execution plan
    4. Optionally execute the plan (auto_fix=true)
    5. Store the interaction in memory
    """
    _check_role(x_role)
    from agent.reasoning import ReasoningEngine
    engine = ReasoningEngine()
    result = await engine.reason(
        query=body.query,
        auto_fix=body.auto_fix,
        auto_confirm=body.auto_confirm,
    )
    return AskResponse(
        answer=result["answer"],
        plan_summary=result["plan"].summary(),
        exec_results=result["exec_results"],
        rca_path=result.get("rca_path"),
        memory_id=result["memory_id"],
    )


@app.post("/runbook", response_model=RunbookResponse, tags=["Runbook"])
async def runbook(
    body: RunbookRequest,
    x_role: str | None = Header(None, alias="X-Role"),
) -> RunbookResponse:
    """
    Generate a runbook for a DevOps task and optionally execute it.
    """
    _check_role(x_role)
    from agent.planner import Planner
    from services.rca_generator import RCAGenerator

    planner = Planner()
    plan = await planner.create_runbook(body.task)

    exec_results: dict[str, Any] = {}
    if not body.dry_run:
        from agent.executor import Executor
        executor = Executor(auto_confirm=body.auto_confirm)
        try:
            exec_results = await executor.execute_plan(plan)
        except Exception as exc:
            exec_results = {"error": str(exc)}

    # Save runbook doc
    rca_gen = RCAGenerator()
    runbook_path = rca_gen.generate_runbook(
        task=body.task,
        steps=[s.command for s in plan.steps],
    )

    return RunbookResponse(
        goal=plan.goal,
        steps=[
            {
                "index": s.index,
                "description": s.description,
                "tool": s.tool,
                "command": s.command,
                "safety": s.safety.value,
                "requires_confirmation": s.requires_confirmation,
            }
            for s in plan.steps
        ],
        exec_results=exec_results,
        runbook_path=runbook_path,
    )


@app.post("/diagnose", response_model=DiagnoseResponse, tags=["Diagnostics"])
async def diagnose(
    body: DiagnoseRequest,
    x_role: str | None = Header(None, alias="X-Role"),
) -> DiagnoseResponse:
    """
    Deep-diagnose a Kubernetes / infrastructure issue.

    Optionally collects live kubectl logs to enrich the LLM diagnosis.
    """
    _check_role(x_role)
    from agent.reasoning import ReasoningEngine
    from services.log_parser import LogParser

    log_analysis: dict[str, Any] = {}

    # Optionally gather live Kubernetes logs
    if body.collect_logs:
        try:
            from tools.kubernetes_tool import KubernetesTool
            k8s = KubernetesTool()
            pods_output = await k8s.get_pods(namespace=body.namespace)
            events_output = await k8s.get_events(namespace=body.namespace)

            parser = LogParser()
            pods_result = parser.parse_kubectl_output(pods_output)
            events_result = parser.parse_kubectl_output(events_output)

            log_analysis = {
                "pods_summary": pods_result.summary,
                "events_summary": events_result.summary,
                "critical_errors": pods_result.has_critical_errors or events_result.has_critical_errors,
                "top_errors": list(set(pods_result.top_errors + events_result.top_errors)),
            }
        except Exception as exc:
            log_analysis = {"error": f"Failed to collect logs: {exc}"}

    # Build enriched query for the reasoning engine
    enriched_query = body.issue
    if log_analysis:
        enriched_query += f"\n\nKubernetes namespace: {body.namespace}\nLog analysis: {log_analysis}"

    engine = ReasoningEngine()
    result = await engine.reason(enriched_query, auto_fix=False)

    return DiagnoseResponse(
        diagnosis=result["answer"],
        log_analysis=log_analysis,
        plan_summary=result["plan"].summary(),
        rca_path=result.get("rca_path"),
    )


@app.get("/memory", tags=["Agent"])
async def list_memory() -> dict[str, Any]:
    """Return all stored incident memories."""
    from agent.memory import AgentMemory
    mem = AgentMemory()
    entries = mem.all_entries()
    return {
        "count": len(entries),
        "entries": [
            {
                "id": e.id,
                "query": e.query,
                "answer_preview": e.answer[:200],
                "timestamp": e.timestamp,
                "metadata": e.metadata,
            }
            for e in entries
        ],
    }
