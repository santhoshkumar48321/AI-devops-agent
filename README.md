# AI DevOps Agent

> **Autonomous Troubleshooter · Runbook Assistant · RCA Generator**  
> Powered by FastAPI · OpenAI · Kubernetes · Ansible

---

## Project Overview

The **AI DevOps Agent** is a production-grade, AI-powered assistant that
helps platform engineers diagnose infrastructure issues, automate remediation
runbooks, and generate incident documentation — all through a simple natural
language interface.

Point the agent at a failing Kubernetes namespace and it will collect logs,
detect patterns, suggest a fix, optionally execute it, and write an RCA doc
automatically.

---

## Features

| Capability | Description |
|---|---|
| 🔍 **AI Troubleshooter** | Natural language → root cause analysis via LLM |
| 📋 **Runbook Executor** | Plain-English tasks → structured kubectl/ansible/bash plans |
| 🧠 **Incident Memory** | FAISS vector store remembers past incidents for context |
| 📄 **RCA Generator** | Auto-generates Markdown incident reports and runbooks |
| ☸️ **Kubernetes Native** | kubectl integration, live log/event collection |
| 🔧 **Ansible Ready** | ansible-runner support for multi-host remediation |
| 🖥️ **Linux Diagnostics** | CPU, memory, disk, journalctl, process management |
| ☁️ **Multi-Cloud** | AWS, Azure, GCP CLI wrappers |
| 🔐 **Safety Controls** | Confirmation gates, RBAC, audit logging |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                             │
│          CLI (typer)          REST API (FastAPI)                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      Agent Core (agent/)                        │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────┐  ┌─────────┐ │
│  │  reasoning  │→ │   planner    │→ │ executor │  │ memory  │ │
│  │  (LLM loop) │  │ (JSON plan)  │  │ (safety) │  │ (FAISS) │ │
│  └─────────────┘  └──────────────┘  └──────────┘  └─────────┘ │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                  Tool Layer (tools/)                            │
│                                                                 │
│  kubernetes_tool   ansible_tool   linux_tool   cloud_tool      │
│      (kubectl)    (ansible-runner)  (shell)   (aws/az/gcloud)  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                 Services Layer (services/)                      │
│                                                                 │
│      log_parser        metrics_analyzer      rca_generator     │
│  (pattern matching)   (threshold alerts)   (Markdown docs)     │
└─────────────────────────────────────────────────────────────────┘

Infrastructure:  RHEL 9.6 VMs · containerd · Kubernetes (kubeadm)
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, FastAPI, uvicorn |
| LLM | OpenAI API (gpt-4o) |
| Memory | FAISS + OpenAI text-embedding-3-small |
| Container Runtime | containerd 1.7 |
| Orchestration | Kubernetes 1.30 (kubeadm) |
| CNI | Flannel |
| Infra Tools | kubectl, ansible-runner, AWS/Azure/GCP CLI |
| OS | RHEL 9.6 |

---

## Repository Structure

```
AI-devops-agent/
├── agent/                  # Agent core modules
│   ├── planner.py          # LLM → ExecutionPlan
│   ├── executor.py         # Safe plan runner + audit log
│   ├── memory.py           # FAISS vector memory
│   └── reasoning.py        # Plan→Execute→Observe→Improve loop
├── tools/                  # Infrastructure tool wrappers
│   ├── kubernetes_tool.py  # kubectl integration
│   ├── ansible_tool.py     # ansible-runner integration
│   ├── linux_tool.py       # Linux diagnostics
│   └── cloud_tool.py       # AWS / Azure / GCP
├── services/               # Business-logic services
│   ├── log_parser.py       # Pattern-based log analysis
│   ├── metrics_analyzer.py # Threshold alerts + Prometheus
│   └── rca_generator.py    # Markdown RCA / runbook writer
├── api/
│   └── routes.py           # FastAPI: /ask /runbook /diagnose /memory
├── k8s/                    # Kubernetes manifests
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── deployment.yaml
│   ├── service.yaml
│   └── rbac.yaml
├── docker/
│   ├── Dockerfile          # Multi-stage image build
│   └── .dockerignore
├── scripts/                # Automation shell scripts
│   ├── 01-base-setup.sh    # RHEL 9.6 base preparation
│   ├── 02-container-runtime.sh  # containerd install
│   ├── 03-k8s-control-plane.sh  # kubeadm init + Flannel
│   ├── 04-k8s-worker.sh    # Join worker node
│   └── 05-deploy-app.sh    # Build image + kubectl apply
├── tests/                  # Unit tests (55 tests, all passing)
├── docs/incidents/         # Auto-generated RCA documents
├── main.py                 # CLI entry point
├── config.py               # Pydantic settings
├── requirements.txt
├── .env.example
├── RUNBOOK.md              # Detailed deployment runbook ← Start here
└── README.md
```

---

## Setup Instructions

### Prerequisites

- 2 × RHEL 9.6 VMs (2 vCPU / 4 GB RAM / 40 GB disk each)
- VMware Workstation / Fusion (Bridged networking)
- An OpenAI API key

### Quick Start

```bash
# Step 1 – Clone the repository
git clone https://github.com/santhoshkumar48321/AI-devops-agent.git
cd AI-devops-agent

# Step 2 – Configure environment
cp .env.example .env
# Edit .env: set OPENAI_API_KEY=sk-your-key

# Step 3 – Run locally (no Kubernetes needed)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python main.py serve
# API available at http://localhost:8000
# Swagger UI at http://localhost:8000/docs
```

### Deploy to Kubernetes (RHEL 9.6 VMs)

See **[RUNBOOK.md](RUNBOOK.md)** for the complete step-by-step guide, or run:

```bash
# On Control Plane VM
sudo bash scripts/01-base-setup.sh k8s-control 192.168.1.10 192.168.1.11
sudo bash scripts/02-container-runtime.sh
sudo bash scripts/03-k8s-control-plane.sh 192.168.1.10

# On Worker Node VM
sudo bash scripts/01-base-setup.sh k8s-worker 192.168.1.10 192.168.1.11
sudo bash scripts/02-container-runtime.sh
sudo bash scripts/04-k8s-worker.sh "kubeadm join ..."

# Deploy the agent (back on Control Plane)
export OPENAI_API_KEY="sk-your-key"
bash scripts/05-deploy-app.sh
```

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Liveness check |
| `/ask` | POST | Natural language question → diagnosis + plan |
| `/diagnose` | POST | Deep-diagnose with live kubectl log collection |
| `/runbook` | POST | Generate (and optionally execute) a runbook |
| `/memory` | GET | List all stored incident memories |

Swagger UI: `http://<node-ip>:30800/docs`

---

## Example Usage

### CLI

```bash
# Ask a question
python main.py ask "Pods in namespace production are crashing"

# Diagnose a Kubernetes issue
python main.py diagnose "CrashLoopBackOff" --namespace production

# Generate a runbook (dry-run – no execution)
python main.py runbook "Restart failing pods and clear cache"

# Execute a runbook
python main.py runbook "Restart failing pods" --no-dry-run
```

### REST API

```bash
NODE_IP="192.168.1.11"

# Health check
curl http://${NODE_IP}:30800/health

# Ask the agent
curl -X POST http://${NODE_IP}:30800/ask \
     -H "Content-Type: application/json" \
     -d '{"query": "Pod is crashing in namespace default"}'

# Diagnose with live log collection
curl -X POST http://${NODE_IP}:30800/diagnose \
     -H "Content-Type: application/json" \
     -d '{"issue": "OOMKill in production", "namespace": "production"}'

# Generate a runbook
curl -X POST http://${NODE_IP}:30800/runbook \
     -H "Content-Type: application/json" \
     -d '{"task": "Restart failing pods and clear cache", "dry_run": true}'
```

---

## Runbook Reference

👉 See **[RUNBOOK.md](RUNBOOK.md)** for the complete deployment guide:

- Infrastructure requirements (VM specs, network)
- RHEL 9.6 base system preparation
- containerd + kubeadm cluster setup
- Application containerisation and deployment
- Integration details (kubectl, Ansible, Linux tools)
- Test cases and verification steps
- Observability setup (metrics-server, Prometheus/Grafana)
- Troubleshooting guide

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
# 55 tests — all passing
```

---

## Security

- All shell parameters sanitised with `shlex.quote()` to prevent injection
- Destructive actions (pod delete/restart) require explicit `auto_confirm=true`
- RBAC via `X-Role` header; roles configured in `ALLOWED_ROLES` env var
- Every action appended to an audit log (`AUDIT_LOG_PATH`)
- Non-root container user (`uid 1000`)
- Kubernetes `ClusterRole` follows principle of least privilege

---

## Future Improvements

- [ ] Persistent memory (PVC instead of emptyDir)
- [ ] Slack / Teams webhook notifications
- [ ] Helm chart for one-command deployment
- [ ] OpenShift (`oc` CLI) support
- [ ] Auto-healing workflows (watch + act loop)
- [ ] CI/CD pipeline integration (GitHub Actions / Tekton)
- [ ] Web UI (React dashboard)
- [ ] Voice command interface
- [ ] Multi-cluster support

---

## Author

<!-- Replace with your name and contact -->
**Author:** _Your Name_  
**GitHub:** _your-github-handle_  
**LinkedIn:** _your-linkedin_

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
