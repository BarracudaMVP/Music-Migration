#!/bin/bash
# =============================================================================
# Create/update Dante proxy user (MM-25)
# Dante uses Linux system users for username auth.
#
# Run on RU server as root:
#   ./add-proxy-user.sh <username> <password>
# =============================================================================

set -euo pipefail

USERNAME="${1:-proxyuser}"
PASSWORD="${2:-}"

if [[ -z "$PASSWORD" ]]; then
    echo "Usage: $0 <username> <password>"
    exit 1
fi

# Create user without home dir and shell (service account)
if id "$USERNAME" &>/dev/null; then
    echo "==> User $USERNAME already exists, updating password"
else
    echo "==> Creating user $USERNAME"
    useradd -r -s /bin/false -M "$USERNAME"
fi

echo "$USERNAME:$PASSWORD" | chpasswd
echo "==> Done. Update YM_PROXY_URL: socks5://$USERNAME:<password>@<RU_SERVER_IP>:1080"
