#!/bin/bash
# =============================================================================
# RU Server — ufw firewall setup for Dante SOCKS5 proxy (MM-25)
#
# Run on the RU server as root:
#   chmod +x setup-firewall.sh
#   ./setup-firewall.sh <EU_SERVER_IP> [DEV_IP]
#
# Example:
#   ./setup-firewall.sh 1.2.3.4
#   ./setup-firewall.sh 1.2.3.4 88.99.10.11    # also allow dev machine
# =============================================================================

set -euo pipefail

EU_IP="${1:-}"
DEV_IP="${2:-}"

if [[ -z "$EU_IP" ]]; then
    echo "Usage: $0 <EU_SERVER_IP> [DEV_IP]"
    exit 1
fi

echo "==> Setting up ufw rules"
echo "    EU server:  $EU_IP"
[[ -n "$DEV_IP" ]] && echo "    Dev machine: $DEV_IP"

# Reset to clean state (keeps SSH rule)
ufw --force reset

# Default policy: deny all incoming, allow outgoing
ufw default deny incoming
ufw default allow outgoing

# SSH — always allow (don't lock yourself out)
ufw allow 22/tcp comment "SSH"

# Dante SOCKS5 — only from EU server (and optionally dev machine)
ufw allow from "$EU_IP" to any port 1080 proto tcp comment "Dante SOCKS5 — EU server"
[[ -n "$DEV_IP" ]] && ufw allow from "$DEV_IP" to any port 1080 proto tcp comment "Dante SOCKS5 — dev machine"

# Enable firewall
ufw --force enable

echo ""
echo "==> ufw status:"
ufw status verbose
