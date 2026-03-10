#!/bin/bash
# MM-9: Let's Encrypt certificate renewal + nginx reload
#
# Runs via crontab every 10 days (added automatically by setup-ssl.sh):
#   0 3 */10 * * bash /root/Music-Migration/scripts/renew-ssl.sh >> /var/log/certbot-renew.log 2>&1
#
# certbot renew is a no-op if cert has > 30 days left, so running every 10 days is safe.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_PROJECT="music-migration"

echo "[$(date -Iseconds)] Renewing certificate..."

docker run --rm \
    -v "${COMPOSE_PROJECT}_nginx_certs:/etc/letsencrypt" \
    -v /var/www/certbot:/var/www/certbot \
    certbot/certbot renew \
    --webroot -w /var/www/certbot \
    --non-interactive \
    --quiet

echo "[$(date -Iseconds)] Reloading nginx..."
docker compose -f "${PROJECT_DIR}/docker-compose.yml" exec -T nginx nginx -s reload

echo "[$(date -Iseconds)] Done."
