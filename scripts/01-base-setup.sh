#!/usr/bin/env bash
# =============================================================================
# scripts/01-base-setup.sh
# RHEL 9.6 Base System Preparation – run on BOTH Control Plane and Worker Node
#
# Usage: sudo bash scripts/01-base-setup.sh <hostname> <cp-ip> <worker-ip>
#   e.g. sudo bash scripts/01-base-setup.sh k8s-control 192.168.1.10 192.168.1.11
# =============================================================================
set -euo pipefail

HOSTNAME="${1:-k8s-node}"
CP_IP="${2:-192.168.1.10}"
WORKER_IP="${3:-192.168.1.11}"

echo "==> [1/8] Setting hostname to: ${HOSTNAME}"
hostnamectl set-hostname "${HOSTNAME}"

echo "==> [2/8] Updating /etc/hosts"
cat >> /etc/hosts <<EOF

# Kubernetes cluster nodes
${CP_IP}    k8s-control
${WORKER_IP} k8s-worker
EOF

echo "==> [3/8] Full system update (this may take a few minutes)"
dnf update -y

echo "==> [4/8] Installing base packages"
dnf install -y \
    curl \
    wget \
    git \
    vim \
    net-tools \
    bash-completion \
    iproute-tc \
    socat \
    conntrack \
    ipset

echo "==> [5/8] Disabling SELinux (set to permissive for testing)"
# Permissive – still logs denials but does not enforce, safer than disabled
setenforce 0 || true
sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config
echo "     SELinux status: $(getenforce)"

echo "==> [6/8] Disabling swap (required by kubelet)"
swapoff -a
# Comment out any swap entries in fstab so they don't re-enable on boot
sed -i '/\bswap\b/s/^/#/' /etc/fstab
echo "     Swap status:"
free -h | grep -i swap

echo "==> [7/8] Loading required kernel modules"
cat > /etc/modules-load.d/k8s.conf <<EOF
overlay
br_netfilter
EOF
modprobe overlay
modprobe br_netfilter

echo "==> [8/8] Configuring kernel networking parameters"
cat > /etc/sysctl.d/k8s.conf <<EOF
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sysctl --system

echo ""
echo "✅  Base setup complete on ${HOSTNAME}."
echo "    Reboot recommended before proceeding: sudo reboot"
