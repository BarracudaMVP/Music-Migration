#!/bin/bash
# MM-9: One-time Let's Encrypt SSL certificate setup for musicmigration.site
#
# Usage:
#   bash scripts/setup-ssl.sh <your@email.com>
#
# Prerequisites:
#   - DNS A-record: musicmigration.site → this server's IP
#   - docker compose stack already built (docker compose build)
#   - Run from /root/Music-Migration on the EU server
#
# What it does:
#   1. Stops nginx (to free port 80)
#   2. Runs certbot standalone to obtain the certificate
#   3. Starts nginx back with full SSL config
#   4. Prints next steps (update .env, Spotify redirect URI)

set -euo pipefail

DOMAIN="musicmigration.site"
EMAIL="${1:?ERROR: email required. Usage: $0 <your@email.com>}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_PROJECT="music-migration"  # docker compose project name (dir lowercase)

echo "=== MM-9: SSL Setup for $DOMAIN ==="
echo "    Email: $EMAIL"
echo "    Project: $PROJECT_DIR"
echo ""

cd "$PROJECT_DIR"

# Verify A-record is set before continuing
echo "[0/4] Checking DNS for $DOMAIN..."
RESOLVED=$(dig +short "$DOMAIN" 2>/dev/null || host "$DOMAIN" 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1 || echo "")
if [ -z "$RESOLVED" ]; then
    echo "WARNING: Could not resolve $DOMAIN. Make sure A-record is set before running this script."
    read -p "Continue anyway? [y/N] " -n 1 -r; echo
    [[ $REPLY =~ ^[Yy]$ ]] || exit 1
else
    echo "         Resolved to: $RESOLVED"
fi

# Stop nginx to free port 80 for certbot standalone
echo "[1/4] Stopping nginx container..."
docker compose stop nginx

# Run certbot standalone — binds to port 80 directly
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

echo "[3/4] Certificate obtained."

# Start nginx with the SSL config
echo "[4/4] Starting nginx with SSL..."
docker compose up -d nginx

echo ""
echo "✓ Done! nginx is now serving HTTPS."
echo ""
echo "Next steps:"
echo "  1. Add to .env on this server:"
echo "       WEB_BASE_URL=https://$DOMAIN"
echo ""
echo "  2. Update Spotify app at developer.spotify.com:"
echo "       Redirect URI: https://$DOMAIN/auth/spotify/callback"
echo "       (remove old http:// URI)"
echo ""
echo "  3. Apply .env changes:"
echo "       docker compose up -d"
echo ""
echo "Certificate renewal (run monthly via cron):"
echo "  bash scripts/renew-ssl.sh"
