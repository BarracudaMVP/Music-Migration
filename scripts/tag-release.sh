#!/bin/bash
# tag-release.sh — создать тег релиза и запушить
#
# Использование:
#   bash scripts/tag-release.sh v1.0-mm48            # тег на текущий коммит
#   bash scripts/tag-release.sh v1.0-mm48 "Сообщение"  # с аннотацией
#   bash scripts/tag-release.sh --list               # посмотреть все теги
#   bash scripts/tag-release.sh --history            # теги + коммиты
#   bash scripts/tag-release.sh --delete v1.0-mm48   # удалить тег

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}▶${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}!${NC} $*"; }

# ── Режим просмотра ───────────────────────────────────────────────────────────
if [ "${1:-}" = "--list" ]; then
    echo "Все теги:"
    git tag -l --sort=-version:refname | head -20
    exit 0
fi

if [ "${1:-}" = "--history" ]; then
    echo "Теги и коммиты:"
    git log --oneline --decorate | head -30
    exit 0
fi

# ── Режим удаления ────────────────────────────────────────────────────────────
if [ "${1:-}" = "--delete" ]; then
    TAG="${2:?Укажи тег: bash scripts/tag-release.sh --delete v1.0-mm48}"
    git tag -d "$TAG"
    git push origin --delete "$TAG" 2>/dev/null && ok "Тег '${TAG}' удалён локально и на remote" || \
        warn "Тег '${TAG}' удалён локально (на remote не было)"
    exit 0
fi

# ── Создание тега ─────────────────────────────────────────────────────────────
TAG="${1:?Укажи имя тега: bash scripts/tag-release.sh v1.0-mm48}"
MESSAGE="${2:-Release ${TAG}}"

COMMIT=$(git rev-parse --short HEAD)
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")

log "Создаю тег '${TAG}' на коммите ${COMMIT} (${BRANCH})"
log "Сообщение: ${MESSAGE}"

# Проверяем, нет ли уже такого тега
if git tag -l | grep -q "^${TAG}$"; then
    echo -e "${YELLOW}Тег '${TAG}' уже существует. Перезаписать? [y/N]${NC} \c"
    read -r CONFIRM
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
        echo "Отменено."
        exit 0
    fi
    git tag -d "$TAG"
    git push origin --delete "$TAG" 2>/dev/null || true
fi

# Аннотированный тег (лучше чем lightweight — хранит автора и дату)
git tag -a "$TAG" -m "$MESSAGE"
git push origin "$TAG"

ok "Тег '${TAG}' создан и запушен"
echo ""
echo "  Задеплоить на сервере:"
echo "    bash scripts/deploy.sh ${TAG}"
