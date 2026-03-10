#!/bin/bash
# deploy.sh — переключение версии и перезапуск стека
#
# Использование:
#   bash scripts/deploy.sh                  # обновить до последнего main
#   bash scripts/deploy.sh v1.0-mm48        # переключиться на тег
#   bash scripts/deploy.sh 6e1b8ad          # переключиться на коммит
#   bash scripts/deploy.sh main             # переключиться на main
#
# Создать тег и задеплоить:
#   git tag v1.0-mm48 && git push origin --tags
#   bash scripts/deploy.sh v1.0-mm48

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-main}"

# ── Цвета ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] !${NC} $*"; }
fail() { echo -e "${RED}[$(date '+%H:%M:%S')] ✗${NC} $*"; exit 1; }

# ── Переходим в директорию проекта ───────────────────────────────────────────
cd "$PROJECT_DIR"
log "Проект: $PROJECT_DIR"

# ── Текущее состояние ─────────────────────────────────────────────────────────
CURRENT_COMMIT=$(git rev-parse --short HEAD)
CURRENT_REF=$(git describe --tags --exact-match 2>/dev/null || git symbolic-ref --short HEAD 2>/dev/null || echo "$CURRENT_COMMIT")
log "Текущая версия: ${CURRENT_REF} (${CURRENT_COMMIT})"

# ── Получаем свежие данные с remote ──────────────────────────────────────────
log "Получаю обновления (git fetch)..."
git fetch --all --tags --quiet

# ── Переключаемся на нужную версию ───────────────────────────────────────────
log "Переключаюсь на: ${VERSION}"

if ! git checkout "$VERSION" 2>/dev/null; then
    fail "Версия '${VERSION}' не найдена. Проверь: git tag -l  или  git log --oneline"
fi

# Если это ветка (не тег и не хеш) — подтягиваем последние коммиты
if git symbolic-ref --short HEAD 2>/dev/null | grep -q .; then
    BRANCH=$(git symbolic-ref --short HEAD)
    log "Ветка '${BRANCH}' — обновляю до HEAD..."
    git pull origin "$BRANCH" --quiet
fi

NEW_COMMIT=$(git rev-parse --short HEAD)
NEW_REF=$(git describe --tags --exact-match 2>/dev/null || git symbolic-ref --short HEAD 2>/dev/null || echo "$NEW_COMMIT")

if [ "$CURRENT_COMMIT" = "$NEW_COMMIT" ]; then
    warn "Версия не изменилась (${NEW_COMMIT}) — всё равно перезапускаю контейнеры"
else
    ok "Переключился: ${CURRENT_REF} → ${NEW_REF} (${NEW_COMMIT})"
fi

# ── Применяем миграции БД ────────────────────────────────────────────────────
log "Применяю миграции БД (alembic upgrade head)..."
docker compose run --rm --no-deps api alembic upgrade head 2>/dev/null \
    && ok "Миграции применены" \
    || warn "Миграции: нет изменений или контейнер api не запущен"

# ── Пересобираем и перезапускаем стек ────────────────────────────────────────
log "Пересобираю образы и перезапускаю контейнеры..."
docker compose up --build -d

ok "Задеплоено: ${NEW_REF} (${NEW_COMMIT})"
echo ""
echo -e "  Версия:  ${GREEN}${NEW_REF}${NC} (${NEW_COMMIT})"
echo -e "  Статус:  docker compose ps"
echo -e "  Логи:    docker compose logs -f --tail=50"
