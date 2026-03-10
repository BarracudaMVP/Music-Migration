#!/bin/bash
# MM-9: Let's Encrypt certificate renewal
#
# Usage:
#   bash scripts/renew-ssl.sh
#
# Add to crontab for automatic renewal (twice a month):
#   0 3 1,15 * * /root/Music-Migration/scripts/renew-ssl.sh >> /var/log/certbot-renew.log 2>&1

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_PROJECT="music-migration"

echo "[$(date -Iseconds)] Renewing Let's Encrypt certificate..."
cd "$PROJECT_DIR"

docker run --rm \
    -v "${COMPOSE_PROJECT}_nginx_certs:/etc/letsencrypt" \
    -v /var/www/certbot:/var/www/certbot \
    certbot/certbot renew \
    --webroot -w /var/www/certbot \
    --non-interactive

# Reload nginx to pick up renewed cert
docker compose exec nginx nginx -s reload

echo "[$(date -Iseconds)] Renewal complete."
