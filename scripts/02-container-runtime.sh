#!/usr/bin/env bash
# =============================================================================
# scripts/02-container-runtime.sh
# Install containerd as the container runtime – run on BOTH nodes
#
# containerd is preferred over Docker for Kubernetes 1.24+ because:
#   - It's the CRI-compliant runtime used natively by kubeadm
#   - Lower overhead than the full Docker daemon
#   - No need for the deprecated dockershim layer
# =============================================================================
set -euo pipefail

CONTAINERD_VERSION="1.7.18"

echo "==> [1/5] Removing any old container packages"
dnf remove -y docker docker-client docker-client-latest docker-common \
    docker-latest docker-latest-logrotate docker-logrotate docker-engine \
    podman runc 2>/dev/null || true

echo "==> [2/5] Installing containerd ${CONTAINERD_VERSION} from Docker CE repo"
dnf config-manager --add-repo \
    https://download.docker.com/linux/rhel/docker-ce.repo

# Install containerd only (not the full Docker daemon)
dnf install -y containerd.io

echo "==> [3/5] Configuring containerd"
# Generate the default config
mkdir -p /etc/containerd
containerd config default > /etc/containerd/config.toml

# Enable SystemdCgroup – REQUIRED for kubeadm/kubelet to work correctly
sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' \
    /etc/containerd/config.toml

echo "==> [4/5] Enabling and starting containerd"
systemctl enable --now containerd
systemctl status containerd --no-pager

echo "==> [5/5] Verifying containerd"
ctr version

echo ""
echo "✅  containerd installed and running."
