#!/usr/bin/env bash
# =============================================================================
# scripts/03-k8s-control-plane.sh
# Install kubeadm/kubelet/kubectl and initialise the Control Plane
# Run ONLY on the Control Plane VM
#
# Usage: sudo bash scripts/03-k8s-control-plane.sh <control-plane-ip>
#   e.g. sudo bash scripts/03-k8s-control-plane.sh 192.168.1.10
# =============================================================================
set -euo pipefail

K8S_VERSION="1.30"
CP_IP="${1:-$(hostname -I | awk '{print $1}')}"
POD_CIDR="10.244.0.0/16"   # Flannel default – must match CNI config

echo "==> [1/8] Adding Kubernetes ${K8S_VERSION} yum repository"
cat > /etc/yum.repos.d/kubernetes.repo <<EOF
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v${K8S_VERSION}/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v${K8S_VERSION}/rpm/repodata/repomd.xml.key
exclude=kubelet kubeadm kubectl cri-tools kubernetes-cni
EOF

echo "==> [2/8] Installing kubeadm, kubelet, kubectl"
dnf install -y --disableexcludes=kubernetes \
    kubelet \
    kubeadm \
    kubectl

echo "==> [3/8] Enabling kubelet"
systemctl enable --now kubelet

echo "==> [4/8] Opening firewall ports for the control plane"
firewall-cmd --permanent --add-port=6443/tcp   # kube-apiserver
firewall-cmd --permanent --add-port=2379-2380/tcp # etcd
firewall-cmd --permanent --add-port=10250/tcp  # kubelet API
firewall-cmd --permanent --add-port=10259/tcp  # kube-scheduler
firewall-cmd --permanent --add-port=10257/tcp  # kube-controller-manager
firewall-cmd --reload

echo "==> [5/8] Initialising the Kubernetes cluster"
echo "     Control Plane IP : ${CP_IP}"
echo "     Pod network CIDR  : ${POD_CIDR}"
kubeadm init \
    --apiserver-advertise-address="${CP_IP}" \
    --pod-network-cidr="${POD_CIDR}" \
    --cri-socket="unix:///run/containerd/containerd.sock" \
    | tee /root/kubeadm-init.log

echo "==> [6/8] Setting up kubeconfig for root"
mkdir -p /root/.kube
cp -f /etc/kubernetes/admin.conf /root/.kube/config
chown root:root /root/.kube/config

# Also set up for any sudo-capable user that runs this script
if [[ -n "${SUDO_USER:-}" ]]; then
    USER_HOME=$(getent passwd "${SUDO_USER}" | cut -d: -f6)
    mkdir -p "${USER_HOME}/.kube"
    cp -f /etc/kubernetes/admin.conf "${USER_HOME}/.kube/config"
    chown "${SUDO_USER}:${SUDO_USER}" "${USER_HOME}/.kube/config"
fi

echo "==> [7/8] Installing Flannel CNI (lightweight, matches ${POD_CIDR})"
kubectl apply -f \
    https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml

echo "==> [8/8] Verifying cluster nodes (may take ~60 s to become Ready)"
sleep 30
kubectl get nodes -o wide

echo ""
echo "✅  Control Plane is up."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  WORKER NODE JOIN COMMAND (copy this to the worker node):"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
# Extract and display the join command from the init log
grep -A1 "kubeadm join" /root/kubeadm-init.log | tail -3
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Alternatively, regenerate the join command at any time with:"
echo "  kubeadm token create --print-join-command"
