# AI DevOps Agent

A **production-grade AI-powered DevOps assistant** built with FastAPI and OpenAI.

---

## 🎯 Features

| Capability | Description |
|---|---|
| **AI Troubleshooter** | Natural language diagnosis of Kubernetes, Linux, and cloud issues |
| **Runbook Executor** | Convert plain-English tasks into kubectl/ansible/bash runbooks |
| **Documentation Generator** | Auto-generate RCA docs and runbooks as Markdown files |
| **Multi-Platform Support** | Kubernetes, OpenShift, Linux, Ansible, AWS, Azure, GCP |
| **Memory** | Vector-backed incident history (FAISS) for context-aware responses |
| **Audit Log** | Every action is logged for compliance |

---

## 🏗️ Architecture

```
AI-devops-agent/
├── agent/
│   ├── planner.py       # LLM-powered task planner
│   ├── executor.py      # Safe plan executor with audit log
│   ├── memory.py        # FAISS vector memory store
│   └── reasoning.py     # Plan→Execute→Observe→Improve loop
├── tools/
│   ├── kubernetes_tool.py  # kubectl wrapper
│   ├── ansible_tool.py     # ansible-runner wrapper
│   ├── linux_tool.py       # Linux diagnostics
│   └── cloud_tool.py       # AWS / Azure / GCP CLI
├── services/
│   ├── log_parser.py        # Pattern-based log analysis
│   ├── metrics_analyzer.py  # Threshold alerts + Prometheus
│   └── rca_generator.py     # RCA / runbook Markdown generator
├── api/
│   └── routes.py        # FastAPI: /ask /runbook /diagnose /memory
├── docs/incidents/      # Auto-generated RCA documents
├── main.py              # CLI entry point (typer)
├── config.py            # Pydantic settings
└── requirements.txt
```

---

## 🚀 Quick Start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

### 3. Start the API server

```bash
python main.py serve
# API available at http://localhost:8000
# Docs at http://localhost:8000/docs
```

### 4. Use the CLI

```bash
# Ask a question
python main.py ask "Pods in namespace X are crashing"

# Diagnose a Kubernetes issue
python main.py diagnose "CrashLoopBackOff" --namespace production

# Generate a runbook (dry-run)
python main.py runbook "Restart failing pods and clear cache"

# Execute a runbook
python main.py runbook "Restart failing pods" --no-dry-run
```

---

## 🌐 API Reference

### `POST /ask`
Ask the agent a natural language DevOps question.

```json
{
  "query": "Pods in namespace X are crashing",
  "auto_fix": false,
  "auto_confirm": false
}
```

### `POST /runbook`
Generate (and optionally execute) a DevOps runbook.

```json
{
  "task": "Restart failing pods and clear cache",
  "dry_run": true
}
```

### `POST /diagnose`
Deep-diagnose a Kubernetes issue with live log collection.

```json
{
  "issue": "High memory usage causing OOMKill",
  "namespace": "production",
  "collect_logs": true
}
```

### `GET /memory`
List all stored incident memories.

### `GET /health`
Service health check.

---

## 🔐 Security

- **Confirmation gates**: destructive actions (delete/restart) require explicit `auto_confirm=true`
- **RBAC**: pass `X-Role: admin` header; allowed roles configured via `ALLOWED_ROLES` env var
- **Audit log**: every executed action is appended to `AUDIT_LOG_PATH`

---

## 🧪 Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

---

## 📋 Example Workflow

**User:** "Pods in namespace production are crashing"

**Agent:**
1. Searches memory for similar past incidents
2. Calls OpenAI to diagnose the issue
3. Generates a plan: `kubectl get pods` → `kubectl logs` → `kubectl describe` → optional `kubectl delete pod`
4. Executes read-only steps automatically
5. Prompts for confirmation before deleting pods
6. Generates an RCA document in `docs/incidents/`
7. Stores the interaction in memory for future reference

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | Model to use |
| `API_HOST` | `0.0.0.0` | API server host |
| `API_PORT` | `8000` | API server port |
| `MEMORY_DIR` | `./data/memory` | FAISS index directory |
| `DOCS_OUTPUT_DIR` | `./docs/incidents` | RCA output directory |
| `AUDIT_LOG_PATH` | `./data/audit.log` | Audit log file |
| `REQUIRE_CONFIRMATION` | `true` | Gate destructive actions |
| `ALLOWED_ROLES` | `admin,operator` | RBAC role allowlist |
