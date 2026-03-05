# MM — Music Migration

Универсальный сервис переноса музыкальных библиотек между стриминговыми платформами.
Доступен через Telegram-бот и веб-интерфейс. Единый бэкенд обрабатывает задачи от обоих клиентов.

---

## Стек

- **API**: FastAPI + Jinja2 + HTMX
- **БД**: PostgreSQL + SQLAlchemy 2.x async + Alembic
- **Очередь**: arq (Redis)
- **Бот**: aiogram 3.x
- **Инфра**: Docker + docker-compose + Nginx
- **Прокси**: Dante SOCKS5 на RU сервере (для Яндекс Музыки)

---

## Архитектура

```
┌──────────────────┐     ┌──────────────────┐
│  Telegram Bot    │     │  Web UI          │
│  (aiogram 3.x)   │     │  (Jinja2 + HTMX) │
└────────┬─────────┘     └────────┬─────────┘
         │ HTTP (internal API)    │ HTTP
         └────────────┬───────────┘
                      ▼
         ┌────────────────────────┐
         │    FastAPI Server      │
         │  /api/* + /web/*       │
         │  /admin/*              │
         └──────┬─────────────────┘
                │
        ┌───────┼───────────┐
        ▼       ▼           ▼
  [PostgreSQL] [Redis]  [Redis pub/sub]
                │            │ (progress events)
                ▼            │
     ┌─────────────────┐     │
     │   Worker Pool   │─────┘
     │   (arq workers) │
     └────────┬────────┘
              │
    ┌─────────┼──────────┐
    ▼         ▼          ▼
[YM Adapter] [SC Adapter] [File Adapter]
(RU proxy)   (EU server)  (CSV/JSON)
```

---

## Реестр сервисов

```
Capability:
  READ_LIKED_TRACKS      WRITE_LIKED_TRACKS
  READ_PLAYLISTS         WRITE_PLAYLISTS
  READ_LIKED_ARTISTS     WRITE_LIKED_ARTISTS
  EXPORT_FILE            IMPORT_FILE

Сервисы:
  yandex_music:   READ_LIKED_TRACKS, READ_PLAYLISTS, READ_LIKED_ARTISTS
  soundcloud:     WRITE_LIKED_TRACKS, WRITE_PLAYLISTS, WRITE_LIKED_ARTISTS
  file_csv:       EXPORT_FILE, IMPORT_FILE
  spotify:        (в будущем)
```

```
FROM \ TO     | SoundCloud | File CSV
--------------|------------|----------
Yandex Music  |     ✓      |    ✓
File CSV      |     ✓      |    –
SoundCloud    |     –      |    ✓  (в будущем)
```

---

## Задачи

### ✅ MM-1 — Ядро (треки, плейлисты, артисты)
- [x] YandexMusicClient — треки, плейлисты, артисты (батчинг по 150, uid fallback)
- [x] SoundCloudClient — search + write, rate limit 429
- [x] Matcher — rapidfuzz + iuliia транслитерация
- [x] Migration pipeline — resumable через БД (pending/liked/not_found/error)
- [x] Шифрование токенов (Fernet)

---

### ✅ MM-2 — Telegram бот (базовый)
- [x] FSM auth: Yandex OAuth + SoundCloud токен
- [x] Прогресс миграции, /status, /cancel
- [x] Сессии в SQLite

---

### ✅ MM-3 — FastAPI + разделение бота от сервера
- [x] FastAPI сервер — роутеры, deps
- [x] POST /api/migrations, GET /api/migrations/{id}
- [x] POST /api/auth/yandex/token, POST /api/auth/soundcloud/validate
- [x] GET/PUT /api/sessions/{user_id}
- [x] bot/api_client.py — бот как тонкий клиент
- [x] PostgreSQL модели (SQLAlchemy 2.x) + Alembic

---

### ✅ MM-4 — Worker + очередь задач
- [x] arq worker, WorkerSettings
- [x] run_migration job — читает из БД, выполняет пайплайн
- [x] Redis pub/sub прогресс → polling endpoint
- [x] Отмена задачи (arq job abort)
- [x] Ограничение параллельных задач

---

### ✅ MM-5 — Service Registry
- [x] Capability Flag enum + MusicServiceAdapter ABC
- [x] ServiceRegistry — register/all/get/matrix
- [x] YandexMusicAdapter, SoundCloudAdapter, FileAdapter
- [x] GET /api/services, GET /api/services/matrix

---

### ✅ MM-6 — Веб-интерфейс (пользователи)
- [x] base.html, index.html, auth.html, progress.html, result.html, history.html
- [x] HTMX polling прогресса
- [x] Экспорт CSV/JSON
- [x] SessionMiddleware (cookie-сессии)

---

### ✅ MM-7 — Веб-интерфейс (админка)
- [x] /admin/login, /admin/dashboard, /admin/migrations, /admin/users, /admin/services
- [x] Отмена и перезапуск миграции
- [x] Детальная страница миграции с таблицей треков

---

### ✅ MM-8 — Инфраструктура и деплой
- [x] Dockerfile.api/bot/worker + docker-compose.yml
- [x] Nginx reverse proxy
- [x] entrypoint.sh — alembic upgrade head перед стартом
- [x] healthcheck для api, .dockerignore
- [x] RU сервер — Dante SOCKS5 прокси → YM_PROXY_URL
- [x] EU сервер — полный стек запущен

---

### 🔲 MM-9 — SSL / HTTPS
- [ ] Домен → A-запись на EU сервер
- [ ] certbot + Let's Encrypt через docker
- [ ] Раскомментировать SSL-секцию в nginx/nginx.conf
- [ ] Редирект HTTP → HTTPS

---

### 🔲 MM-10 — CI/CD и среды
- [ ] GitHub Actions: lint (ruff) + build + deploy
- [ ] Разделение конфигов: .env.local / .env.prod
- [ ] Деплой: ssh → git pull → docker compose up --build -d

---

### 🔲 MM-11 — Улучшенный поиск треков
- [ ] Обработка составных авторов: "A feat. B" → несколько вариантов поиска
- [ ] Fallback поиск: по title only, by artist only
- [ ] Пропуск трека если не найден — не останавливать миграцию
- [ ] Список ненайденных треков пользователю по итогам

---

### 🔲 MM-12 — Список треков и статусы (веб)
- [ ] Страница /migrate/{id}/tracks — таблица с статусами
- [ ] Фильтрация по статусу (liked/not_found/error)
- [ ] Пагинация

---

### 🔲 MM-13 — Обновление Telegram бота
- [ ] Прогресс миграции в боте (аналог веб-UI)
- [ ] Список треков и статусы через бота
- [ ] Inline-кнопки для управления

---

### 🔲 MM-14 — Импорт из файла
- [ ] Загрузка CSV/JSON через веб-UI
- [ ] Предпросмотр перед импортом
- [ ] Настройки маппинга полей в админке

---

### 🔲 MM-15 — Ролевая модель
- [ ] Роли: user / admin в БД
- [ ] Админка доступна пользователям с ролью admin
- [ ] Управление ролями через интерфейс

---

### 🔲 MM-16 — Безопасность и rate limiting
- [ ] Лимит запросов per-user
- [ ] Защита от брутфорса на /admin/login
- [ ] ALLOWED_USERS enforcement через middleware

---

### 🔲 MM-17 — Уведомления
- [ ] Telegram уведомление когда миграция завершена
- [ ] Уведомление когда SC токен скоро истечёт

---

### 🔲 MM-18 — Улучшение интерфейса
- [ ] Редизайн веб-UI
- [ ] Мобильная адаптация
- [ ] Анимации прогресса

---

### 🔲 MM-19 — Централизованное логирование
- [ ] Structured logging (JSON) в api/worker/bot через loguru
- [ ] Ротация логов docker (max-size, max-file)
- [ ] Loki + Promtail + Grafana в docker-compose
- [ ] Фильтрация по сервису/уровню/migration_id в Grafana

---

### 🔲 MM-20 — Тесты и ревью
- [ ] Покрытие тестами ключевых пайплайнов
- [ ] Integration tests (API + DB)
- [ ] Нагрузочное тестирование (20-30 параллельных пользователей)
- [ ] Кодревью и рефакторинг

---

### 🔲 MM-21 — Мультиязычность
- [ ] EN/RU интерфейс (веб + бот)
- [ ] Автоопределение языка по браузеру/Telegram

---

### 🔲 MM-22 — Spotify
- [ ] SpotifyAdapter в ServiceRegistry
- [ ] OAuth для Spotify
- [ ] Миграция Spotify → SoundCloud

---

### 🔲 MM-23 — Telegram плейлисты (отложено)

> API не стандартизован. Реализовать когда появится ясность.

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| SoundCloud rate limit | sleep(2) + 429 backoff с reset_time |
| Трек не найден (кириллица) | iuliia транслитерация + dual-path scoring |
| Обрыв задачи | arq retry + resumable пайплайн |
| Yandex Music недоступен с EU IP | SOCKS5 прокси через RU сервер ✅ |
| SoundCloud недоступен с RU IP | Воркер на EU сервере |
| 20-30 параллельных пользователей | arq max_jobs, asyncpg pool, per-user rate limit |
| Истёкший токен во время миграции | Проверка при старте + graceful fail |
| SC токен (cookie) — короткий срок | Уведомление + инструкция по обновлению |
