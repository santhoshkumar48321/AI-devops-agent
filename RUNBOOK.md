# AI DevOps Agent — Deployment Runbook

**Environment:** RHEL 9.6 on VMware · Kubernetes (kubeadm) · containerd  
**Scope:** Local testing / development cluster (1 Control Plane + 1 Worker Node)  
**Audience:** DevOps engineers deploying the agent for the first time

---

## Table of Contents

1. [Infrastructure Requirements](#1-infrastructure-requirements)
2. [Base System Preparation](#2-base-system-preparation)
3. [Container Runtime Setup (containerd)](#3-container-runtime-setup)
4. [Kubernetes Cluster Setup](#4-kubernetes-cluster-setup)
5. [Networking Setup](#5-networking-setup)
6. [Application Containerisation](#6-application-containerisation)
7. [Kubernetes Deployment](#7-kubernetes-deployment)
8. [Agent Integration](#8-agent-integration)
9. [Testing the Setup](#9-testing-the-setup)
10. [Observability](#10-observability)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Infrastructure Requirements

### VM Specifications (Testing Level)

| Role | CPU | RAM | Disk | OS |
|---|---|---|---|---|
| Control Plane | 2 vCPU | 4 GB | 40 GB | RHEL 9.6 |
| Worker Node | 2 vCPU | 4 GB | 40 GB | RHEL 9.6 |

> **Minimum host machine:** 16 GB RAM · 8-core CPU · 100 GB free disk  
> A mid-range developer laptop or workstation is sufficient.

### Network

| Setting | Value |
|---|---|
| VM Network Mode | **Bridged** (recommended) or NAT with port-forwarding |
| Control Plane IP | `192.168.1.10` (example – use your actual subnet) |
| Worker Node IP | `192.168.1.11` |
| Pod Network CIDR | `10.244.0.0/16` (Flannel) |
| Service CIDR | `10.96.0.0/12` (kubeadm default) |

> Bridged mode lets both VMs and your host share the same LAN, making
> it easy to hit the NodePort service from your laptop.

### Required Open Ports

| Port | Protocol | Direction | Purpose |
|---|---|---|---|
| 6443 | TCP | Inbound (CP) | kube-apiserver |
| 2379-2380 | TCP | Internal | etcd |
| 10250 | TCP | Inbound (both) | kubelet API |
| 10259 | TCP | Internal (CP) | kube-scheduler |
| 10257 | TCP | Internal (CP) | kube-controller |
| 8472 | UDP | All nodes | Flannel VXLAN |
| 30800 | TCP | Inbound (all) | Agent NodePort |

---

## 2. Base System Preparation

> **Run on both VMs.** Use the automation script or follow the manual steps below.

```bash
# Automated (recommended)
sudo bash scripts/01-base-setup.sh k8s-control 192.168.1.10 192.168.1.11
# On worker:
sudo bash scripts/01-base-setup.sh k8s-worker 192.168.1.10 192.168.1.11
```

### Manual Steps

#### 2.1 System Update

```bash
sudo dnf update -y
```

#### 2.2 Set Hostname

```bash
# Control plane
sudo hostnamectl set-hostname k8s-control

# Worker node
sudo hostnamectl set-hostname k8s-worker
```

#### 2.3 Configure /etc/hosts (both VMs)

```bash
sudo tee -a /etc/hosts <<EOF

# Kubernetes cluster nodes
192.168.1.10    k8s-control
192.168.1.11    k8s-worker
EOF
```

#### 2.4 Install Required Packages

```bash
sudo dnf install -y \
    curl wget git vim net-tools bash-completion \
    iproute-tc socat conntrack ipset
```

#### 2.5 Disable SELinux (permissive)

```bash
sudo setenforce 0
sudo sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config
```

#### 2.6 Disable Swap

```bash
sudo swapoff -a
sudo sed -i '/\bswap\b/s/^/#/' /etc/fstab
```

Verify:

```bash
free -h | grep -i swap
# Expected: Swap: 0B 0B 0B
```

#### 2.7 Load Kernel Modules

```bash
sudo tee /etc/modules-load.d/k8s.conf <<EOF
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter
```

#### 2.8 Kernel Networking Parameters

```bash
sudo tee /etc/sysctl.d/k8s.conf <<EOF
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF

sudo sysctl --system
```

---

## 3. Container Runtime Setup

> **Run on both VMs.** We use **containerd** (not Docker) because it is the
> CRI-native runtime required by kubeadm 1.24+.

```bash
# Automated
sudo bash scripts/02-container-runtime.sh
```

### Manual Steps

#### 3.1 Add Docker CE Repository

```bash
sudo dnf config-manager --add-repo \
    https://download.docker.com/linux/rhel/docker-ce.repo
```

#### 3.2 Install containerd

```bash
sudo dnf install -y containerd.io
```

#### 3.3 Configure SystemdCgroup

```bash
sudo mkdir -p /etc/containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml

# Enable SystemdCgroup driver (required by kubelet)
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' \
    /etc/containerd/config.toml
```

#### 3.4 Enable and Start containerd

```bash
sudo systemctl enable --now containerd
sudo systemctl status containerd
```

#### 3.5 Validate

```bash
sudo ctr version
# Expected: Client/Server version output
```

---

## 4. Kubernetes Cluster Setup

### 4.1 Control Plane

```bash
# Automated
sudo bash scripts/03-k8s-control-plane.sh 192.168.1.10
```

#### Manual: Add the Kubernetes Repository

```bash
K8S_VERSION="1.30"

sudo tee /etc/yum.repos.d/kubernetes.repo <<EOF
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v${K8S_VERSION}/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v${K8S_VERSION}/rpm/repodata/repomd.xml.key
exclude=kubelet kubeadm kubectl cri-tools kubernetes-cni
EOF
```

#### Manual: Install kubeadm, kubelet, kubectl

```bash
sudo dnf install -y --disableexcludes=kubernetes kubelet kubeadm kubectl
sudo systemctl enable --now kubelet
```

#### Manual: Initialise the Cluster

```bash
sudo kubeadm init \
    --apiserver-advertise-address=192.168.1.10 \
    --pod-network-cidr=10.244.0.0/16 \
    --cri-socket=unix:///run/containerd/containerd.sock \
    | tee ~/kubeadm-init.log
```

Expected output includes `Your Kubernetes control-plane has initialized successfully!`

#### Manual: Set Up kubeconfig

```bash
mkdir -p $HOME/.kube
sudo cp /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```

#### Manual: Install Flannel CNI

```bash
kubectl apply -f \
    https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
```

Wait ~60 s then verify the control plane is Ready:

```bash
kubectl get nodes -o wide
# NAME           STATUS   ROLES           AGE   VERSION
# k8s-control    Ready    control-plane   2m    v1.30.x
```

---

### 4.2 Worker Node

```bash
# Get the join command from the control plane
kubeadm token create --print-join-command

# On the WORKER NODE:
sudo bash scripts/04-k8s-worker.sh "kubeadm join 192.168.1.10:6443 --token <token> --discovery-token-ca-cert-hash sha256:<hash>"
```

#### Verify Both Nodes Are Ready (on Control Plane)

```bash
kubectl get nodes -o wide
# NAME           STATUS   ROLES           AGE   VERSION
# k8s-control    Ready    control-plane   5m    v1.30.x
# k8s-worker     Ready    <none>          2m    v1.30.x
```

---

## 5. Networking Setup

### Pod Network

Flannel uses VXLAN and the `10.244.0.0/16` CIDR. No extra configuration is
needed after `kubectl apply` in step 4.1.

### Firewall Rules

```bash
# Control Plane
sudo firewall-cmd --permanent --add-port=6443/tcp
sudo firewall-cmd --permanent --add-port=2379-2380/tcp
sudo firewall-cmd --permanent --add-port=10250/tcp
sudo firewall-cmd --permanent --add-port=10259/tcp
sudo firewall-cmd --permanent --add-port=10257/tcp
sudo firewall-cmd --reload

# Worker Node
sudo firewall-cmd --permanent --add-port=10250/tcp
sudo firewall-cmd --permanent --add-port=30000-32767/tcp   # NodePort range
sudo firewall-cmd --reload

# Both nodes – Flannel VXLAN
sudo firewall-cmd --permanent --add-port=8472/udp
sudo firewall-cmd --reload
```

### Verify Pod-to-Pod Connectivity

```bash
kubectl run test-pod --image=busybox --restart=Never -- sleep 600
kubectl exec -it test-pod -- ping 8.8.8.8
kubectl delete pod test-pod
```

---

## 6. Application Containerisation

### 6.1 Build the Docker Image

Run from the repository root on the **Control Plane VM** (where Docker is
available after installing `docker-ce` in addition to containerd):

```bash
# Install Docker CLI (optional – only needed to build images)
sudo dnf install -y docker-ce docker-ce-cli
sudo systemctl enable --now docker

# Build
docker build \
    --file docker/Dockerfile \
    --tag ai-devops-agent:1.0.0 \
    .
```

### 6.2 Import into containerd (no registry needed)

Since we are not using a private registry, import the image directly into
the containerd namespace used by Kubernetes:

```bash
docker save ai-devops-agent:1.0.0 \
    | sudo ctr --namespace k8s.io images import -

# Verify
sudo ctr --namespace k8s.io images list | grep ai-devops-agent
```

### 6.3 (Optional) Use a Local Registry

```bash
# Start a local registry container
docker run -d -p 5000:5000 --name registry registry:2

# Tag and push
docker tag ai-devops-agent:1.0.0 localhost:5000/ai-devops-agent:1.0.0
docker push localhost:5000/ai-devops-agent:1.0.0

# Update k8s/deployment.yaml image field to:
#   image: localhost:5000/ai-devops-agent:1.0.0
#   imagePullPolicy: Always
```

---

## 7. Kubernetes Deployment

### 7.1 Deploy Everything at Once (Automated)

```bash
export OPENAI_API_KEY="sk-your-real-key"
bash scripts/05-deploy-app.sh
```

### 7.2 Manual Step-by-Step

#### Encode the OpenAI API Key

```bash
echo -n "sk-your-real-key" | base64
# Copy the output and replace <base64-encoded-api-key> in k8s/secret.yaml
```

#### Apply Manifests in Order

```bash
# 1. Namespace
kubectl apply -f k8s/namespace.yaml

# 2. RBAC
kubectl apply -f k8s/rbac.yaml

# 3. ConfigMap
kubectl apply -f k8s/configmap.yaml

# 4. Secret
kubectl apply -f k8s/secret.yaml

# 5. Deployment
kubectl apply -f k8s/deployment.yaml

# 6. Service
kubectl apply -f k8s/service.yaml
```

#### Verify

```bash
kubectl get all -n ai-devops-agent
# NAME                                   READY   STATUS    RESTARTS   AGE
# pod/ai-devops-agent-xxxxxxxxx-xxxxx    1/1     Running   0          60s
#
# NAME                        TYPE       CLUSTER-IP      PORT(S)          AGE
# service/ai-devops-agent-svc NodePort   10.96.x.x       8000:30800/TCP   60s
#
# NAME                              READY   UP-TO-DATE   AVAILABLE
# deployment.apps/ai-devops-agent   1/1     1            1
```

---

## 8. Agent Integration

### How the Agent Interacts with kubectl

The agent runs `kubectl` commands as subprocesses from inside the pod.
The `ServiceAccount` (`ai-devops-agent-sa`) is bound to a `ClusterRole`
that allows reading pods/logs/events and deleting pods (for remediation).
The kubeconfig is **not** mounted – instead the pod uses its service-account
token at `/var/run/secrets/kubernetes.io/serviceaccount/`.

kubectl automatically picks up the in-cluster config when `KUBECONFIG` is
not set, so no additional configuration is needed.

### How the Agent Interacts with Ansible

Ansible playbooks are placed in `data/ansible/` inside the pod (or mounted
via a ConfigMap/PVC for persistent playbooks). The agent calls
`ansible-runner` or the `ansible-playbook` CLI subprocess.

For ad-hoc remote execution, SSH keys must be mounted as a Secret:

```bash
kubectl create secret generic ansible-ssh-key \
    --from-file=id_rsa=$HOME/.ssh/id_rsa \
    -n ai-devops-agent
```

Then mount it in `k8s/deployment.yaml` under `volumeMounts`.

### How the Agent Interacts with Linux Tools

Linux diagnostic commands (`ps`, `free`, `df`, `journalctl`, etc.) run
directly on the Kubernetes node only if the pod has host-level access. For
testing purposes the agent runs these commands on the container itself.

For real host diagnostics, use the Ansible integration to SSH to target hosts.

---

## 9. Testing the Setup

### 9.1 Health Check

```bash
NODE_IP="192.168.1.11"   # or 192.168.1.10 on a single-node cluster

curl -s http://${NODE_IP}:30800/health
# Expected: {"status":"ok","service":"AI DevOps Agent"}
```

### 9.2 Swagger UI

Open in a browser: `http://192.168.1.11:30800/docs`

### 9.3 Ask the Agent (API)

```bash
curl -s -X POST http://${NODE_IP}:30800/ask \
     -H "Content-Type: application/json" \
     -d '{"query": "Pod is crashing in namespace default"}' \
     | python3 -m json.tool
```

Expected output excerpt:

```json
{
  "answer": "## Root Cause Analysis\n\n...",
  "plan_summary": "**Goal:** Diagnose and fix crashing pod\n\n1. ...",
  "exec_results": {},
  "rca_path": null,
  "memory_id": "..."
}
```

### 9.4 Diagnose a Pod Failure

```bash
curl -s -X POST http://${NODE_IP}:30800/diagnose \
     -H "Content-Type: application/json" \
     -d '{"issue": "Pod stuck in CrashLoopBackOff", "namespace": "default"}' \
     | python3 -m json.tool
```

### 9.5 Generate a Runbook

```bash
curl -s -X POST http://${NODE_IP}:30800/runbook \
     -H "Content-Type: application/json" \
     -d '{"task": "Restart failing pods and clear cache", "dry_run": true}' \
     | python3 -m json.tool
```

### 9.6 kubectl Verification

```bash
# Pod logs
kubectl logs -f deployment/ai-devops-agent -n ai-devops-agent

# Pod events
kubectl describe pod -l app=ai-devops-agent -n ai-devops-agent

# Resource usage
kubectl top pod -n ai-devops-agent
```

---

## 10. Observability

### Basic Logging

```bash
# Stream real-time logs
kubectl logs -f deployment/ai-devops-agent -n ai-devops-agent

# Last 100 lines
kubectl logs --tail=100 deployment/ai-devops-agent -n ai-devops-agent
```

### Kubernetes Events

```bash
kubectl get events -n ai-devops-agent --sort-by='.lastTimestamp'
```

### Resource Monitoring

```bash
# Requires metrics-server
kubectl top pods -n ai-devops-agent
kubectl top nodes
```

Install metrics-server (if not present):

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

For single-node or self-signed-cert clusters, add `--kubelet-insecure-tls`:

```bash
kubectl patch deployment metrics-server \
    -n kube-system \
    --type=json \
    -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
```

### (Optional) Prometheus + Grafana

For a lightweight monitoring stack:

```bash
# Install kube-prometheus-stack via Helm
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install monitoring prometheus-community/kube-prometheus-stack \
    --namespace monitoring --create-namespace \
    --set prometheus.prometheusSpec.resources.requests.memory=256Mi \
    --set grafana.resources.requests.memory=128Mi
```

Access Grafana:

```bash
kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring
# Open: http://localhost:3000  (admin / prom-operator)
```

---

## 11. Troubleshooting

### kubeadm init Fails

| Symptom | Likely Cause | Fix |
|---|---|---|
| `[ERROR Swap]` | Swap still enabled | `swapoff -a && sed -i '/swap/s/^/#/' /etc/fstab` |
| `[ERROR CRI]` | containerd not running | `systemctl start containerd` |
| `[ERROR FileContent--proc-sys-net-bridge]` | Kernel module missing | `modprobe br_netfilter && sysctl --system` |
| `port 6443 already in use` | Previous cluster still running | `kubeadm reset -f && reboot` |

**Full reset and retry:**

```bash
sudo kubeadm reset -f
sudo rm -rf /etc/cni/net.d /var/lib/etcd $HOME/.kube
sudo systemctl restart containerd
sudo kubeadm init ...
```

---

### CNI (Flannel) Not Working

**Pods stuck in `Init:0/1` or `Pending`:**

```bash
# Check Flannel pods
kubectl get pods -n kube-flannel
kubectl describe pod -n kube-flannel <flannel-pod>

# Re-apply Flannel
kubectl delete -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
kubectl apply  -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
```

Ensure the `--pod-network-cidr` passed to `kubeadm init` matches Flannel's
default (`10.244.0.0/16`).

---

### Pod Stuck in Pending

```bash
kubectl describe pod <pod-name> -n ai-devops-agent
```

| Event Message | Cause | Fix |
|---|---|---|
| `0/1 nodes are available: Insufficient cpu` | Resource requests too high | Lower `resources.requests.cpu` in deployment.yaml |
| `0/1 nodes are available: node(s) had untolerated taint` | Control plane taint | Add toleration in deployment.yaml (already included) |
| `no nodes available to schedule pods` | Only control plane, no workers | Join worker node or remove CP taint |

Remove control-plane taint (single-node only):

```bash
kubectl taint nodes k8s-control node-role.kubernetes.io/control-plane:NoSchedule-
```

---

### Image Pull Issues

```bash
# Verify image is in containerd
sudo ctr --namespace k8s.io images list | grep ai-devops-agent

# Re-import if missing
docker save ai-devops-agent:1.0.0 \
    | sudo ctr --namespace k8s.io images import -
```

Ensure `imagePullPolicy: IfNotPresent` in `k8s/deployment.yaml` so
Kubernetes uses the local image and does not attempt to pull from Docker Hub.

---

### Agent Pod CrashLoopBackOff

```bash
# Check logs for the error
kubectl logs deployment/ai-devops-agent -n ai-devops-agent --previous

# Common causes:
# 1. Missing OPENAI_API_KEY in secret
kubectl get secret ai-devops-agent-secret -n ai-devops-agent -o yaml

# 2. Port conflict
kubectl describe pod -l app=ai-devops-agent -n ai-devops-agent
```

---

### Kubernetes API Unreachable from Pod

```bash
# Verify service account token is mounted
kubectl exec -it <pod> -n ai-devops-agent -- \
    ls /var/run/secrets/kubernetes.io/serviceaccount/

# Test in-cluster API call
kubectl exec -it <pod> -n ai-devops-agent -- \
    curl -s --cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
    -H "Authorization: Bearer $(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
    https://kubernetes.default.svc/api/v1/namespaces/default/pods
```

---

*Runbook version 1.0 — AI DevOps Agent*
