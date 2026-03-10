#!/bin/bash
# MM-9: One-time Let's Encrypt SSL certificate setup for musicmigration.site
#
# Usage:
#   bash scripts/setup-ssl.sh <your@email.com>
#
# Prerequisites:
#   - DNS A-record: musicmigration.site → this server's IP (wait ~5 min for propagation)
#   - Run from /root/Music-Migration on the EU server
#   - Stack not yet running (or nginx stopped)
#
# What it does:
#   1. Creates certbot webroot volume dir
#   2. Stops nginx (frees port 80)
#   3. Runs certbot standalone to get the first certificate
#   4. Starts the full stack (nginx + certbot service for auto-renewal)
#   5. Adds nginx daily reload to crontab (so nginx picks up renewed certs)

set -euo pipefail

DOMAIN="musicmigration.site"
EMAIL="${1:?ERROR: email required. Usage: $0 <your@email.com>}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_PROJECT="music-migration"

echo "=== MM-9: SSL Setup for $DOMAIN ==="
echo "    Email: $EMAIL"
echo ""

cd "$PROJECT_DIR"

# Check DNS
echo "[0/5] Checking DNS for $DOMAIN..."
RESOLVED=$(dig +short "$DOMAIN" 2>/dev/null | head -1 || true)
if [ -z "$RESOLVED" ]; then
    echo "WARNING: Could not resolve $DOMAIN. Make sure A-record is set."
    read -rp "Continue anyway? [y/N] " yn
    [[ $yn =~ ^[Yy]$ ]] || exit 1
else
    echo "         Resolved to: $RESOLVED"
fi

# Stop nginx to free port 80
echo "[1/5] Stopping nginx..."
docker compose stop nginx 2>/dev/null || true

# First-time cert — use standalone (nginx is down, port 80 is free)
echo "[2/5] Obtaining certificate from Let's Encrypt (standalone)..."
docker run --rm \
    -v "${COMPOSE_PROJECT}_nginx_certs:/etc/letsencrypt" \
    -p 80:80 \
    certbot/certbot certonly \
    --standalone \
    -d "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --non-interactive

echo "[3/5] Certificate obtained."

# Start full stack (nginx with SSL + certbot renewal service)
echo "[4/5] Starting full stack with SSL..."
docker compose up -d

# Add nginx daily reload to crontab (so nginx picks up renewed certs)
echo "[5/5] Adding daily nginx reload to crontab..."
CRON_LINE="0 4 * * * docker compose -f ${PROJECT_DIR}/docker-compose.yml exec -T nginx nginx -s reload >> /var/log/nginx-reload.log 2>&1"
# Add only if not already present
if crontab -l 2>/dev/null | grep -qF "nginx -s reload"; then
    echo "         (already in crontab, skipping)"
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "         Added."
fi

echo ""
echo "✓ Done! https://$DOMAIN is now live."
echo ""
echo "Next steps:"
echo "  1. Add to .env on this server:"
echo "       WEB_BASE_URL=https://$DOMAIN"
echo ""
echo "  2. Update Spotify app at developer.spotify.com:"
echo "       Redirect URI: https://$DOMAIN/auth/spotify/callback"
echo ""
echo "  3. Apply .env changes:"
echo "       docker compose up -d"
echo ""
echo "Auto-renewal: certbot service runs every 12h inside docker."
echo "Nginx picks up new certs daily at 04:00 via crontab."
