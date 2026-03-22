#!/usr/bin/env bash
# =============================================================================
# scripts/04-k8s-worker.sh
# Join a Worker Node to the existing Kubernetes cluster
# Run ONLY on the Worker Node VM
#
# Usage: sudo bash scripts/04-k8s-worker.sh "<kubeadm join command>"
#   e.g. sudo bash scripts/04-k8s-worker.sh \
#          "kubeadm join 192.168.1.10:6443 --token abc123 \
#           --discovery-token-ca-cert-hash sha256:xxxx"
#
# If no argument is given, you will be prompted to paste the join command.
# =============================================================================
set -euo pipefail

K8S_VERSION="1.30"

echo "==> [1/5] Adding Kubernetes ${K8S_VERSION} yum repository"
cat > /etc/yum.repos.d/kubernetes.repo <<EOF
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v${K8S_VERSION}/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v${K8S_VERSION}/rpm/repodata/repomd.xml.key
exclude=kubelet kubeadm kubectl cri-tools kubernetes-cni
EOF

echo "==> [2/5] Installing kubeadm + kubelet"
dnf install -y --disableexcludes=kubernetes kubelet kubeadm
systemctl enable --now kubelet

echo "==> [3/5] Opening firewall ports for worker node"
firewall-cmd --permanent --add-port=10250/tcp   # kubelet API
firewall-cmd --permanent --add-port=30000-32767/tcp  # NodePort services
firewall-cmd --reload

echo "==> [4/5] Joining the cluster"
if [[ -n "${1:-}" ]]; then
    JOIN_CMD="$1"
else
    echo ""
    echo "Paste the 'kubeadm join ...' command from the control plane:"
    read -r JOIN_CMD
fi

eval "${JOIN_CMD}" --cri-socket="unix:///run/containerd/containerd.sock"

echo "==> [5/5] Verifying (run on control plane: kubectl get nodes)"
echo ""
echo "✅  Worker node joined the cluster."
echo "   Run the following on the CONTROL PLANE to confirm:"
echo "   kubectl get nodes -o wide"
