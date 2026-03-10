#!/bin/bash
# MM-9: One-time Let's Encrypt SSL certificate setup for musicmigration.site
#
# Usage:
#   bash scripts/setup-ssl.sh <your@email.com>
#
# Prerequisites:
#   - DNS A-record: musicmigration.site → this server's IP
#   - Run from /root/Music-Migration on the EU server
#
# What it does:
#   1. Stops nginx (frees port 80)
#   2. Runs certbot standalone to get the first certificate
#   3. Starts full stack (nginx now has the cert)
#   4. Adds monthly renewal cron (certbot renew + nginx reload)

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
echo "[0/4] Checking DNS for $DOMAIN..."
RESOLVED=$(dig +short "$DOMAIN" 2>/dev/null | head -1 || true)
if [ -z "$RESOLVED" ]; then
    echo "WARNING: Could not resolve $DOMAIN. Make sure A-record is set."
    read -rp "Continue anyway? [y/N] " yn
    [[ $yn =~ ^[Yy]$ ]] || exit 1
else
    echo "         Resolved to: $RESOLVED"
fi

# Stop nginx to free port 80
echo "[1/4] Stopping nginx..."
docker compose stop nginx 2>/dev/null || true

# Create webroot dir for future renewals
mkdir -p /var/www/certbot

# First-time cert via standalone (nginx is down, port 80 is free)
echo "[2/4] Obtaining certificate from Let's Encrypt..."
docker run --rm \
    -v "${COMPOSE_PROJECT}_nginx_certs:/etc/letsencrypt" \
    -p 80:80 \
    certbot/certbot certonly \
    --standalone \
    -d "$DOMAIN" \
    --email "$EMAIL" \
    --agree-tos \
    --non-interactive

echo "[3/4] Starting nginx with SSL..."
docker compose up -d nginx

# Add monthly renewal to crontab
echo "[4/4] Adding monthly renewal cron..."
CRON_LINE="0 3 1 * * bash ${PROJECT_DIR}/scripts/renew-ssl.sh >> /var/log/certbot-renew.log 2>&1"
if crontab -l 2>/dev/null | grep -qF "renew-ssl.sh"; then
    echo "         (already in crontab, skipping)"
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "         Added: runs 1st of each month at 03:00."
fi

echo ""
echo "✓ Done! https://$DOMAIN is now live."
echo ""
echo "Next steps:"
echo "  1. Add to .env:"
echo "       WEB_BASE_URL=https://$DOMAIN"
echo "  2. Update Spotify app (developer.spotify.com):"
echo "       Redirect URI: https://$DOMAIN/auth/spotify/callback"
echo "  3. docker compose up -d  (apply .env changes)"
