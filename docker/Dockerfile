# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 – Build / dependency install
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install OS-level build deps (needed by faiss-cpu, numpy wheel builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgfortran5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only the dependency manifest first to leverage Docker layer cache.
COPY requirements.txt .

# Install into a local prefix so we can copy it cleanly to the final stage.
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 – Runtime image (minimal footprint)
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# kubectl – needed by the agent to interact with the cluster
ARG KUBECTL_VERSION=v1.30.2
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        ansible \
    && curl -fsSL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
       -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash agent
USER agent
WORKDIR /app

# Copy application source
COPY --chown=agent:agent . .

# Runtime data directories (memory, docs, ansible)
RUN mkdir -p data/memory data/ansible docs/incidents

# Expose the FastAPI port
EXPOSE 8000

# Health-check so Kubernetes knows when the container is ready
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

# Default command – can be overridden in the K8s Deployment
CMD ["python", "main.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
