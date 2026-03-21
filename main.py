"""
AI DevOps Agent - Main entry point.

Supports two modes:
  - API server:  python main.py serve
  - CLI:         python main.py ask "Your question here"
"""

import typer
import uvicorn
from rich.console import Console
from rich.markdown import Markdown

app = typer.Typer(help="AI-powered DevOps Assistant")
console = Console()


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Host to bind the API server"),
    port: int = typer.Option(8000, help="Port for the API server"),
    reload: bool = typer.Option(False, help="Enable auto-reload (development)"),
):
    """Start the FastAPI server."""
    console.print(f"[bold green]Starting AI DevOps Agent API on {host}:{port}[/bold green]")
    uvicorn.run("api.routes:app", host=host, port=port, reload=reload)


@app.command()
def ask(
    query: str = typer.Argument(..., help="Natural language DevOps question"),
    auto_fix: bool = typer.Option(False, "--auto-fix", help="Attempt automatic remediation"),
):
    """Ask the agent a DevOps question via CLI."""
    import asyncio
    from agent.reasoning import ReasoningEngine

    async def _run():
        engine = ReasoningEngine()
        result = await engine.reason(query, auto_fix=auto_fix)
        console.print(Markdown(result.get("answer", "No answer returned.")))
        if result.get("rca_path"):
            console.print(f"\n[bold]RCA document saved to:[/bold] {result['rca_path']}")

    asyncio.run(_run())


@app.command()
def diagnose(
    issue: str = typer.Argument(..., help="Issue description (e.g. 'pod crashing in namespace X')"),
    namespace: str = typer.Option("default", help="Kubernetes namespace"),
):
    """Diagnose a specific Kubernetes or infrastructure issue."""
    import asyncio
    from agent.reasoning import ReasoningEngine

    async def _run():
        engine = ReasoningEngine()
        prompt = f"Diagnose: {issue}. Kubernetes namespace: {namespace}"
        result = await engine.reason(prompt, auto_fix=False)
        console.print(Markdown(result.get("answer", "No diagnosis returned.")))

    asyncio.run(_run())


@app.command()
def runbook(
    task: str = typer.Argument(..., help="Task description (e.g. 'restart failing pods and clear cache')"),
    dry_run: bool = typer.Option(True, help="Preview steps without executing"),
):
    """Generate and optionally execute a runbook for a DevOps task."""
    import asyncio
    from agent.planner import Planner

    async def _run():
        planner = Planner()
        plan = await planner.create_runbook(task)
        console.print(Markdown(f"## Runbook: {task}\n\n" + "\n".join(f"- {step}" for step in plan.steps)))
        if not dry_run:
            from agent.executor import Executor
            executor = Executor()
            results = await executor.execute_plan(plan)
            for step, output in results.items():
                console.print(f"\n[bold]{step}[/bold]\n{output}")

    asyncio.run(_run())


if __name__ == "__main__":
    app()
