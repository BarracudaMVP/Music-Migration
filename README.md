# Music Migration

Сервис для переноса музыкальных библиотек между стриминговыми платформами.

Поддерживает перенос лайкнутых треков, плейлистов и подписок на артистов.

## Поддерживаемые платформы

| Откуда → Куда | SoundCloud | Файл (CSV/JSON) | Яндекс Музыка | Spotify |
|---|:---:|:---:|:---:|:---:|
| Яндекс Музыка | ✓ | ✓ | — | ✓ |
| Spotify | ✓ | ✓ | ✓ | — |
| Файл (CSV/JSON) | ✓ | — | ✓ | ✓ |
| SoundCloud | — | ✓ | ✓ | ✓ |

## Запуск через Docker (production)

**Требования:** Docker, docker compose, домен с настроенным DNS.

1. Клонировать репозиторий:

```bash
git clone <repo-url> && cd Music-Migration
```

2. Создать `.env` на основе раздела [Переменные окружения](#переменные-окружения).

3. Запустить стек:

```bash
docker compose up --build -d
```

Запустятся: PostgreSQL, Redis, FastAPI, Telegram-бот, ARQ-воркер, nginx.

4. (Один раз) настроить SSL:

```bash
bash scripts/setup-ssl.sh admin@yourdomain.com
```

5. Задеплоить конкретный тег:

```bash
bash scripts/deploy.sh v1.0-mm49
```

### Локальная разработка

```bash
# Только API + БД + Redis (без nginx/бота/воркера)
docker compose -f docker-compose.dev.yml up --build

# API доступен на http://localhost:8000
# SPA фронтенд на http://localhost:3000
```

Подробнее: `LOCAL_SETUP.md`.

## Переменные окружения

Создать файл `.env` в корне проекта:

```env
# Telegram
TELEGRAM_BOT_TOKEN=        # токен от @BotFather
ALLOWED_USERS=             # Telegram user ID через запятую (пусто = открыт для всех)

# Яндекс OAuth
YANDEX_CLIENT_ID=          # из oauth.yandex.ru
YANDEX_CLIENT_SECRET=
YANDEX_REDIRECT_URI=       # https://yourdomain.com/api/v1/auth/yandex/callback
YM_PROXY_URL=              # SOCKS5 прокси для Яндекс API (socks5://user:pass@host:port)

# Spotify OAuth
SPOTIFY_CLIENT_ID=         # из developer.spotify.com
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=      # https://yourdomain.com/api/v1/auth/spotify/callback

# SoundCloud OAuth
SC_CLIENT_ID=              # из soundcloud.com/you/apps
SC_CLIENT_SECRET=
SC_REDIRECT_URI=           # https://yourdomain.com/api/v1/auth/soundcloud/callback

# База данных
DATABASE_URL=              # postgresql+asyncpg://user:pass@host/db
DB_ENCRYPTION_KEY=         # ключ Fernet: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Redis
REDIS_URL=redis://localhost:6379

# API
API_BASE_URL=http://localhost:8000
WEB_BASE_URL=              # публичный URL сайта (https://yourdomain.com)
API_INTERNAL_TOKEN=        # общий секрет бот↔API
SECRET_KEY=                # секрет сессий: python -c "import secrets; print(secrets.token_hex(32))"
ADMIN_PASSWORD=            # пароль для /admin

# SPA / JWT
CORS_ORIGINS=http://localhost:3000
JWT_SECRET_KEY=            # openssl rand -hex 32

# Доступ к веб-интерфейсу
WEB_ENABLED=true           # false = отключить веб UI и админку (API и бот работают всегда)
```

## Telegram-бот

### Как найти

Задать `TELEGRAM_BOT_TOKEN` (получить у [@BotFather](https://t.me/BotFather)) и запустить `run.py` или контейнер `bot`.

### Команды

| Команда | Действие |
|---|---|
| `/start` | Приветствие |
| `/migrate` | Запустить перенос библиотеки |
| `/status` | Статус последней миграции |

### Флоу авторизации в боте

- **Яндекс Музыка** — бот выдаёт ссылку на OAuth, пользователь вставляет код.
- **Spotify** — требует предварительной авторизации через веб-интерфейс.
- **SoundCloud** — OAuth через веб-интерфейс (при настроенном `SC_CLIENT_ID`), иначе вставка cookie-токена вручную.

## Веб-интерфейс

Открыть `https://yourdomain.com` (или `http://localhost:8000` локально).

### Разделы

- **Главная (`/`)** — выбор платформы-источника и платформы-назначения, авторизация, запуск переноса.
- **Прогресс (`/migrate/<id>`)** — отслеживание текущей миграции: статус, обработанные треки, ETA.
- **Результаты** — итог переноса: найденные / не найденные треки, экспорт в CSV/JSON.
- **История (`/history`)** — список всех прошлых миграций.
- **Админка (`/admin`)** — список пользователей и миграций, отмена/рестарт задач.

### Авторизация

- **Яндекс Музыка** — OAuth кнопка → подтвердить на oauth.yandex.ru.
- **Spotify** — OAuth кнопка → автоматический редирект.
- **SoundCloud** — OAuth кнопка (при настроенных `SC_*` переменных).

Токены сохраняются в БД в зашифрованном виде (Fernet).

## FAQ

**Как получить токен Яндекс Музыки?**
Нажмите кнопку «Войти через Яндекс» — сервис проведёт через стандартный OAuth. Вручную вставлять ничего не нужно.

**Как получить токен Spotify?**
Нажмите «Войти через Spotify» в веб-интерфейсе. Бот потребует сначала авторизоваться на сайте.

**Трек не найден — что делать?**
Сервис использует нечёткое сопоставление (fuzzy match). Треки со score < 60 помечаются как `not_found` — это норма для редких или локализованных релизов. Скачать список ненайденных треков можно через кнопку «Экспорт» на странице результатов.

**Яндекс Музыка недоступна — нужен ли прокси?**
Да, для серверов за пределами РФ требуется SOCKS5 прокси. Указать в `YM_PROXY_URL=socks5://user:pass@host:port`.

**Сколько треков можно перенести?**
Без ограничений. При переносе в SoundCloud треки помещаются в плейлисты «YM Liked #1», «YM Liked #2» и т.д. батчами по 500 (настраивается через `SC_PLAYLIST_BATCH_SIZE`).

**Безопасно ли хранить токены?**
Все токены хранятся зашифрованными через Fernet (`DB_ENCRYPTION_KEY`). Без ключа расшифровать невозможно.
