# MM — Progress by Task

Детальный лог что сделано в каждой задаче этой сессии и ранее.

---

## ✅ MM-98 — SPA UI: недостающие фичи — 2026-03-25

**Цель:** Закрыть gap между Jinja2 UI и SPA — перенести file import/export, content types, playlist name, lang switcher.

**Ключевые решения:**
- Язык хранится в `localStorage` (не в БД) — стандартный браузерный подход, нет бэкенд-endpoint
- File import: парсинг CSV/JSON в браузере → передача как `tracks_override` в JSON body → воркеры уже поддерживают
- Отдельный `POST /api/v1/migrations/file` endpoint не нужен

**Что сделано:**

**Бэкенд (`api/routes/api_v1.py`):**
- `StartMigrationRequest` + поле `tracks_override: list[dict] | None = None`
- `start_migration`: для file→SC → `run_file_migration_job(tracks=tracks_override)`, для file→YM/Spotify → `tracks_override` передаётся в существующие воркеры
- Убран dead import `from api.routes.migrations import _get_token` (не существовал, lazy import скрывал баг)

**Фронтенд:**
- `HomePage.tsx` — убраны auth-badge с карточек FROM/TO (статус остаётся в секции Авторизация)
- `MigratePage.tsx` — playlist name input (Spotify + playlist mode), content_types чекбоксы (tracks/playlists/artists, from!=file), file picker (from=file), error state для некорректного файла, `canStart` требует файл если from=file
- `ProgressPage.tsx` — кнопки CSV↓ / JSON↓ при to_service=file и status=done
- `migrations.ts` — `TrackImport` тип, `tracks_override` в `StartMigrationRequest`, `parseImportFile(file)` парсит CSV/JSON
- `App.tsx` — `LangContext`, `LangSwitcher` компонент (fixed top-right, RU/EN кнопки), `localStorage` persist
- `index.css` — `.setting-input`, `.setting-file`, `.setting-checkboxes`, `.setting-checkbox-label`, `.lang-switcher`, `.lang-btn`

**Тесты (`tests/test_mm98_spa_ui.py`):** 5 новых тестов (file→YM, file→Spotify, file→SC, SC без tracks_override→400, YM→SC без tracks_override)

**Итог:** 295 passed (было 290), 1 pre-existing fail (test_like_track_raises_on_404).

---

## 🔲 MM-99 — Code Review: безопасность и качество кода — 2026-03-25

**Цель:** провести полное ревью кодовой базы — безопасность, надёжность, архитектура.

**Что найдено (критические):**
- `db_encryption_key = ""` по умолчанию — токены хранятся plain text без валидатора для прода (`config.py`)
- `except Exception as e: return RedirectResponse(f"...{str(e)[:120]}")` — утечка деталей ошибок в OAuth redirects
- Нет валидации файловых загрузок (MIME, размер, magic bytes)
- `get_user_id_by_spa_refresh_token` — full table scan + Fernet decrypt, нет rate limit на `/auth/refresh`

**Что найдено (высокий приоритет):**
- Race condition: ARQ job стартует раньше чем `arq.set(migration_job:{id})` в Redis
- ARQ джобы без `job_timeout` — зависание на неограниченное время
- Spotify access token не обновляется в середине длинной миграции (только в начале)
- `decrypt_token` при ошибке: `return value` вместо raise (`core/crypto.py`)
- CORS: `allow_methods=["*"], allow_headers=["*"]` (`api/main.py`)
- Refresh token в `localStorage` SPA (`frontend/src/api/auth.ts:17`)

**Что найдено (средний приоритет):**
- Нет rate limit на `/auth/exchange` и `/auth/refresh`
- Нет exponential backoff при 429 от SC/Spotify
- Нет idempotency key при `POST /migrations`
- `uuid.uuid4().hex[:12]` для session ID (48 бит) — надо `secrets.token_hex(32)`
- `/health` не проверяет Redis/Postgres
- `tracks_override` без schema-валидации

**Что хорошо:** async I/O корректен, SQLAlchemy ORM (нет SQL injection), `AdapterWriteSession` ABC, resumable миграции, `guard_dev_mode`.

**Следующий шаг:** реализовывать фиксы по приоритету в рамках MM-99.

---

## ✅ MM-96 — SPA: фиксы auth URL, page_size, dev-mode авторизация — 2026-03-19

**Что сделано:**

1. `frontend/src/api/auth.ts` — `getOAuthStartUrl`: добавлен `SERVICE_AUTH_SLUG = {yandex_music: 'yandex'}`. Сервис ID `yandex_music` маппится на slug `yandex` → фиксит 404 на `GET /api/v1/auth/yandex_music`.
2. `api/routes/api_v1.py` — `get_migration_tracks`: исправлен вызов `get_tracks_page(..., page_size=50)` → `per_page=50` (имя параметра в crud-функции `per_page`, не `page_size`).
3. `api/security.py` — `get_current_user`: при `settings.dev_mode=True` сразу возвращает `"dev_user"` — все `/api/v1/` endpoints работают без JWT.
4. `frontend/src/api/auth.ts` — `refreshAccessToken`: при отсутствии refresh token в localStorage пробует `GET /auth/me` без токена. В DEV_MODE сервер отдаёт 200 → `accessToken = "dev"` (sentinel) → SPA продолжает. В проде → 401 → `return null` → обычный OAuth.

**Ключевые решения:**
- Dev-bypass без нового endpoint: backend игнорирует JWT, frontend зондирует существующий `/auth/me`.
- `soundcloud` и `spotify` slug не нуждаются в маппинге (совпадают с service ID).

---

## ✅ MM-83 — React SPA: страницы и полный флоу — 2026-03-19

**Цель:** реализовать все страницы React SPA на ветке `feature/spa`.

**Что сделано:**

1. `frontend/src/pages/HomePage.tsx` — выбор from/to сервисов из matrix API; auth-статус значки на карточках (✓/—); секция авторизации с OAuth кнопками (`window.location.href = getOAuthStartUrl(...)`); `canProceed` gate; кнопка "Далее →" → `/migrate?from=X&to=Y`; `?auth_error=1` banner; `useRef(false)` guard.
2. `frontend/src/pages/MigratePage.tsx` — читает `?from=X&to=Y`; настройки: limit (All/50/100/500), skip_already (скрыт для file), like_tracks (SC), spotify_playlist_mode (Spotify); `handleStart()` → `startMigration()` → navigate `/migrate/{id}/progress`; auth секция с OAuth кнопками.
3. `frontend/src/pages/ProgressPage.tsx` — polling `getMigration(id)` каждые 2с через `setInterval`; прогресс-бар `doneCount/total`; статистика (liked+in_playlist, not_found, errors, pending); `current_track` во время выполнения; terminal actions: "Открыть плейлист" (если `result_path`), "Новая миграция", "История".
4. `frontend/src/pages/HistoryPage.tsx` — redirect если нет токена; `listMigrations()` → кликабельные строки; статус-бейджи (running/pending/done/failed/cancelled); success count, not_found count; ссылка "Плейлист ↗" с `e.stopPropagation()`.
5. `frontend/src/api/migrations.ts` — обновлены типы: `TrackStats` (liked, in_playlist, not_found, error, pending); `Migration.stats`; `MigrationDetail`; `TracksPage`/`TrackRow`.
6. `frontend/src/api/services.ts` — добавлены `MatrixEntry`, `UserStatus`, `isConnected()`, `fetchUserStatus()`.
7. `frontend/src/index.css` — добавлены стили: layout (`.page`, `.container`, `.page-header`), service grid (`.service-card`, `.service-badge`), auth (`.auth-list`, `.auth-row`), settings (`.setting-row`, `.setting-select`), progress (`.progress-bar`, `.progress-fill`, `.stat-rows`), status badges, history (`.migration-list`, `.migration-row`, `.migration-meta`).

**Ключевые решения:**
- Polling вместо SSE (`EventSource` не поддерживает кастомные заголовки для JWT)
- `useRef(false)` guard против double-fetch в React Strict Mode
- `canStart = authServices.every(isAuth) && !starting` — кнопка disabled пока не авторизован

---

## ✅ MM-89 — Spotify playlist user-account fallback — 2026-03-18

**Цель:** расширить Spotify playlist mode (MM-88) — убрать зависимость от `SPOTIFY_BOT_TOKEN`, дать пользователю выбор режима в боте и SPA.

**Что сделано:**

1. `migration/to_spotify.py` — `_create_bot_playlist` → `_create_playlist(migration_id, name, user_token)`: использует `settings.spotify_bot_token or user_token`. Плейлист создаётся на боте если настроен, иначе на аккаунте пользователя.
2. `api/templates/fragments/flow_rest.html` — чекбокс "Создать плейлист" теперь отображается для ВСЕХ Spotify-назначений (убрана проверка `spotify_bot_configured`).
3. `api/routes/api_v1.py` — `StartMigrationRequest`: добавлены `spotify_playlist_mode: bool = False` + `spotify_playlist_name: str = "Music Migration"`, пробрасываются в `run_spotify_write_job`.
4. `bot/handlers/auth.py` — `_confirmation_kb(spotify_playlist_mode=False)`: кнопка `toggle_spotify_playlist` для Spotify-назначения; `on_toggle_spotify_playlist` handler; `on_toggle_skip_migrated`/`on_toggle_like_tracks` пробрасывают `spotify_playlist_mode`.
5. `bot/handlers/migration.py` — `_kb_result(playlist_url=None)`: кнопка "Открыть плейлист" если `playlist_url` задан; `on_start_migration` читает `spotify_playlist_mode` из state; `_poll_migration` пробрасывает `result_path`.
6. `bot/api_client.py` — `start_migration(spotify_playlist_mode=False)`.
7. `core/i18n.py` — `bot_spotify_playlist_on`, `bot_spotify_playlist_off`, `bot_btn_open_playlist`.
8. `tests/test_mm89_spotify_playlist_user.py` — 16 новых тестов; `tests/test_mm88_spotify_playlist.py` — обновлены (`_create_bot_playlist` → `_create_playlist`).

**Ключевые решения:**
- Fallback на user_token — плейлист доступен без бот-аккаунта (главная цель задачи)
- SPA endpoint получил `spotify_playlist_mode` (пропущено в MM-88)
- Чекбокс не гейтирован — пользователь всегда видит опцию

---

## ✅ MM-94 — SC like_tracks + playlist — 2026-03-16

**Баг:** `like_tracks=True` → плейлист не создавался. `_process_one_track` возвращал `("liked", None)`, `None` не попадал в `collected_ids`.

**Фикс:**
1. `migration/to_soundcloud.py` — `_process_one_track`: `return "liked", None` → `return "liked", match.track_id`
2. `migration/to_soundcloud.py` — `_run_pending_loop`: добавлен `if sc_id: collected_ids.append(sc_id)` в ветку `result == "liked"`

**Итог:** `like_tracks=True` = лайк напрямую + трек в плейлист.

---

## ✅ MM-93 — Валидация токенов перед запуском миграции — 2026-03-16

**Проблема:** невалидный токен (истёк срок) обнаруживался только в воркере.

**Что сделано:**
1. `core/db/crud.py` — `clear_service_token(user_id, service)`: зануляет токен + refresh_token в БД
2. `api/routes/web.py` — `_validate_service_token` (Spotify/YM: init(), SC: HTTP /me 401-check); `_check_token` closure; вызов во всех кейсах `start_migrate`
3. При ошибке: clear DB + session flag, редирект `/?error=...&pf={from}&pt={to}`
4. Тесты: 3 новых в `test_db_integration.py`

---

## ✅ MM-92 — Web UI: статусы, история, инлайн треки — 2026-03-16

**Цель:** переработать отображение истории и страниц миграции, ввести новый статус `in_playlist`.

**Что сделано:**

1. **Новый статус `in_playlist`** — треки добавленные в плейлист теперь не получают `status="liked"`. Режимы лайк/плейлист стали взаимоисключающими. `MigrationStats.success = liked + in_playlist`.

2. **`get_track_stats_batch()`** в `core/db/crud.py` — один GROUP BY запрос для статистики всех миграций на странице истории (вместо N+1).

3. **История миграций** — иконки + имена from/to сервисов, `success_count/total_count` в зелёном, кнопка "Новый перенос" (было "+Новый").

4. **Страница миграции** — убраны кнопки "Подробный отчёт" и "Треки"; при завершении инлайн появляется список треков через HTMX sub-fragment (`GET /migrate/{id}/tracks-fragment`). Эндпоинт `/result` → 301 редирект.

5. **Новый шаблон `fragments/tracks_table.html`** — фильтр-табы с HTMX, таблица треков, пагинация 50/страница через `#tracks-section` target.

6. **Переименования:** "Score" → "Точность", "SC" → "Ссылка" во всех шаблонах и i18n.

7. **Правильные ссылки на треки** — по `to_service`: Spotify → open.spotify.com, YM → music.yandex.ru, SC → прямой URL.

8. **Тесты** — обновлены под новый `in_playlist` статус, добавлены: `test_migration_stats_success_*`, `test_process_track_playlist_mode_returns_in_playlist`, `test_get_track_stats_batch_*`. Итого: 212 passed.

**Ключевые решения:**
- `in_playlist` — отдельный статус (не флаг) — проще фильтровать и считать статистику
- HTMX sub-fragment: `status.html` при `done=True` рендерит `<div hx-get=".../tracks-fragment" hx-trigger="load">` → треки загружаются без перезагрузки страницы
- `sc_url` поле хранит разные данные по сервису — ссылки конструируются в шаблоне по `to_service`

**Файлы:** `migration/to_soundcloud.py`, `core/db/crud.py`, `core/db/__init__.py`, `core/i18n.py`, `api/routes/web.py`, `api/routes/admin.py`, `api/templates/history.html`, `api/templates/progress.html`, `api/templates/fragments/status.html`, `api/templates/fragments/tracks_table.html` (новый), `api/templates/tracks.html`, `api/templates/admin/migrations.html`, `api/templates/admin/migration_detail.html`, `tests/test_pipeline.py`, `tests/test_db_integration.py`

---

## ✅ MM-85 — Spotify продакшн-фиксы + оптимизации — 2026-03-15

**Цель:** устранить 403 ошибку при лайке треков в Spotify и улучшить пайплайн миграции.

**Корневая причина 403:** `PUT /me/tracks` — deprecated endpoint, заменён на `PUT /me/library?uris=spotify:track:{id}`.

**Что сделано:**

1. **`like_track` → новый эндпоинт** `PUT /me/library?uris=spotify:track:{id}` — решило 403
2. **Stats fix** — `result == "error"` больше не засчитывается как `not_found` в `_run_pending_tracks_loop`
3. **Транслитерация в поиске** — `transliterate_variants` для имён артистов добавляет латинские варианты запросов (Баста → Basta)
4. **Early pagination stop** — `get_liked_tracks(limit)` в YM и Spotify клиентах останавливается при достижении лимита, не тянет все страницы
5. **Configurable search limit** — `SEARCH_LIMIT=N` в env (default 5, было 10)
6. **Matcher early exit** — `break` при `score == 100.0`
7. **UI** — опция 5 треков (для тестирования), убрана 100
8. **Диагностика** — логирование scope при refresh токена, тело ответа при не-200 в `like_track`

**Ключевые решения:**
- Spotify allowlist в dev mode — пользователей добавлять вручную в Dashboard; Playwright-автоматизация как запасной план (см. PLAN.md)
- `PUT /me/tracks` deprecated → `PUT /me/library` — единственное что реально решило 403

**Файлы:** `core/spotify/client.py`, `core/yandex/client.py`, `core/services/*/adapter.py`, `core/services/base.py`, `core/soundcloud/client.py`, `core/matcher.py`, `migration/to_spotify.py`, `config.py`, `worker/tasks.py`, `api/templates/fragments/flow_rest.html`

---

## ✅ MM-30 — README — 2026-03-14

**Цель:** создать README.md для проекта.

**Что сделано:**
- `README.md` — создан с нуля, разделы: таблица направлений миграции, запуск через Docker (prod + dev), все env-переменные с комментариями, Telegram-бот (команды + флоу авторизации), веб-интерфейс (разделы), FAQ (6 вопросов: токены, прокси, not_found, лимиты, безопасность).

**Файлы:** создан `README.md`

---

## 📋 Планирование бэклога — 2026-03-15

Добавлены 4 новые задачи в `PLAN.md`:

- **MM-86** — Ресёрч сервисов-аналогов (Soundiiz, TuneMyMusic, Stamp, SongShift и др.): поддерживаемые платформы, ограничения бесплатного тарифа, уникальные фичи, идеи для бэклога. Результат → `memory/research_competitors.md`.
- **MM-87** — Рефакторинг адаптеров: write-методы (`search_track`, `write_track`, `create_playlist`, `add_tracks_to_playlist`, `follow_artist`) выносятся в `MusicServiceAdapter` ABC. `Capability` флаги уже есть (`core/services/base.py`). Пайплайны `migration/to_*.py` работают через интерфейс адаптера — не импортируют конкретные клиенты. Матрица возможностей по сервисам: YM — write liked; SC — write playlists; Spotify — write liked + artists + (WRITE_PLAYLISTS в MM-89); File — только read. Фронт и бэк ограничивают пары через `adapter.can()`.
- **MM-88** — Spotify обход dev-ограничений через бот-аккаунт: `SPOTIFY_BOT_TOKEN` в config, бот создаёт публичный плейлист через свой аккаунт, пользователю отдаётся ссылка. Фолбэк к playlist_url в API-ответе, боте и веб-UI.
- **MM-89** — Spotify playlist mode: два режима записи — лайк треков в коллекцию (текущее) и создание плейлиста. Пользователь выбирает в UI (чекбокс) и в боте (inline кнопки). `create_playlist` + `add_tracks_to_playlist` (батч 100) в `SpotifyClient`. Возвращает `playlist_url`.

Также обновлены: `CLAUDE.md` (current state: MM-85), `PLAN.md` (стек + реестр сервисов), `MEMORY.md` (бэклог + ближайшие задачи).

---

## 🔄 MM-83 — React SPA (в процессе) — 2026-03-14

**Цель:** React-фронтенд на Vite + React + TypeScript, работает параллельно с Jinja2 UI.

**Что сделано (scaffolding + bugfix):**
- `frontend/` — scaffolding через `npm create vite@latest --template react-ts` + `react-router-dom`
- `frontend/vite.config.ts` — proxy `/api` → `http://api:8000` (env `API_PROXY_TARGET`), port 3000, `host: true` для Docker
- `frontend/src/api/` — `client.ts` (fetch wrapper + JWT Bearer), `auth.ts`, `services.ts`, `migrations.ts`
- `frontend/src/pages/` — заглушки: `HomePage`, `AuthCallbackPage`, `MigratePage`, `ProgressPage`, `HistoryPage`
- `frontend/src/App.tsx` — React Router routes: `/`, `/auth/callback`, `/migrate`, `/migrate/:id/progress`, `/history`
- `docker-compose.dev.yml` — добавлен сервис `frontend` (Vite dev server, порт 3000, `node_modules` в Docker volume)
- `Dockerfile.frontend` — образ для фронтенда
- `LOCAL_SETUP.md` — инструкция по запуску фронтенда
- **Bugfix:** `api/routes/api_v1.py` — все три OAuth callback'а теперь захватывают `code = await _issue_oauth_code(user_id)` и редиректят на `{WEB_BASE_URL}/auth/callback?code={code}&flow_from=...&flow_to=...` (ранее code терялся)
- **Bugfix:** `frontend/src/api/auth.ts` — убран `/start` суффикс (`/api/v1/auth/${service}/start` → `/api/v1/auth/${service}`)
- `tests/test_api_v1.py` — +3 теста на OAuth callbacks (проверяют `code=` в redirect URL)

**Осталось:** реализовать страницы (HomePage, AuthCallbackPage, MigratePage, ProgressPage, HistoryPage) + бэкенд: `POST /api/v1/migrations/{id}/cancel`, файловый upload.

**Тесты:** 209 passed

**Файлы:**
- Созданы: `frontend/` (весь каталог), `Dockerfile.frontend`
- Изменены: `api/routes/api_v1.py`, `frontend/src/api/auth.ts`, `docker-compose.dev.yml`, `tests/test_api_v1.py`

---

## ✅ MM-80 — Local dev mode — 2026-03-12

**Цель:** локальный запуск без реальных OAuth credentials для разработки UI.

**Итоговая реализация (без специального /dev/login роута):**
- `config.py` — `dev_mode: bool = False` + `guard_dev_mode` model_validator: если `WEB_BASE_URL`/`API_BASE_URL` не localhost — принудительно сбрасывает `dev_mode=False`
- `api/routes/web.py` — `_ensure_user_id()` при `dev_mode=True` возвращает `"dev_user"`
- `api/main.py` — startup WARNING при `dev_mode=True`
- `scripts/seed_dev.py` — создаёт `UserSession(user_id='dev_user')` с фейковыми токенами; запускается из `entrypoint.sh` при `DEV_MODE=true`
- `docker-compose.dev.yml` — standalone (postgres + redis + api)
- `.env.dev` — фейковые credentials (коммитится, `!.env.dev` в .gitignore)
- `LOCAL_SETUP.md` — инструкция для нового разработчика
- `tests/test_dev_mode.py` — 6 тестов

**Файлы:** `config.py`, `api/routes/web.py`, `api/main.py`, `scripts/seed_dev.py`, `docker-compose.dev.yml`, `.env.dev`, `LOCAL_SETUP.md`, `tests/test_dev_mode.py`

---

## ✅ MM-81 Фаза 1 — JWT auth + /api/v1/ SPA API — 2026-03-13

**Цель:** добавить JWT-аутентификацию и публичный JSON API для SPA-фронтенда. Старый Jinja2 UI и бот продолжают работать параллельно.

**Что сделано:**
- `api/security.py`: `create_access_token` (JWT HS256, TTL 15min), `create_refresh_token` (opaque hex 64 символа), `decode_access_token`, `get_current_user` FastAPI dependency (Bearer header)
- `config.py`: `cors_origins` (default `http://localhost:3000`), `jwt_secret_key`, `jwt_access_token_ttl=900`, `jwt_refresh_token_ttl=2592000`
- `core/db/models.py`: `UserSession.spa_refresh_token: Text nullable` (MM-81)
- `alembic/versions/j0k1l2m3n4o5`: добавляет колонку `spa_refresh_token` в `user_sessions`
- `core/db/crud.py`: `save_spa_refresh_token`, `get_user_id_by_spa_refresh_token` (linear scan + Fernet decrypt compare), `revoke_spa_refresh_token`, `get_user_migrations`
- `api/routes/api_v1.py`: полный роутер `/api/v1/` — auth exchange/refresh/logout/me, OAuth start redirects (flow_from/flow_to поддержка), services + matrix, migrations CRUD, tracks pagination, export (CSV/JSON FileResponse), SSE stream
- `api/main.py`: CORSMiddleware (`allow_credentials=False`), `api_v1.router` зарегистрирован всегда (вне `WEB_ENABLED`)
- `tests/test_api_v1.py`: 23 теста

**Итого тестов:** 205 passed

**Файлы:**
- Созданы: `api/security.py`, `api/routes/api_v1.py`, `alembic/versions/j0k1l2m3n4o5_add_spa_refresh_token.py`, `tests/test_api_v1.py`
- Изменены: `api/main.py`, `config.py`, `core/db/models.py`, `core/db/crud.py`, `core/db/__init__.py`, `requirements.txt`

---

## ✅ MM-79 — Auth refactor — 2026-03-13

**Цель:** вынести OAuth-роуты из `web.py`, унифицировать state, подготовить code-exchange для MM-81.

**Ключевые решения:**
- `api/routes/auth.py` → `api/routes/bot_auth.py` (internal bot auth, без изменений поведения)
- Новый `api/routes/oauth.py`: все OAuth redirect/callback из `web.py`
- State storage унифицирован: Redis `oauth_state:{provider}:{state}` TTL 600s для всех трёх провайдеров (было: `_ym_state` cookie, `_sc_state`/`_sc_verifier` cookies, `session["spotify_oauth_state"]`)
- `session["ym_token"]` удалён → `session["ym_connected"] = True` (токен только в БД)
- Ошибки OAuth: `/?error=...` вместо `/auth?error=...`
- Short-lived code `oauth_code:{code}` (Redis TTL 30s) генерируется после каждого успешного OAuth — готово для MM-81 JWT exchange
- `POST /auth/yandex` (форма ручного ввода кода) удалён — в проде всегда используется redirect
- `auth.html`: форма ввода кода убрана, только кнопка OAuth
- `_ensure_user_id` / `_session_user_id` перенесены в `oauth.py`, `web.py` импортирует их оттуда
- 16 новых тестов `tests/test_oauth.py`, итого 182 passed

**Файлы:**
- Создан: `api/routes/oauth.py`, `tests/test_oauth.py`
- Переименован: `api/routes/auth.py` → `api/routes/bot_auth.py`
- Изменены: `api/routes/web.py`, `api/main.py`, `api/templates/auth.html`

---

## ✅ MM-80 — Local dev mode — 2026-03-12

**Цель:** локальный запуск для фронтенд-разработчика без реальных OAuth credentials.

**Ключевые решения:**
- `/dev/login` регистрируется только при `DEV_MODE=true` → в продакшне (default=False) роут физически отсутствует
- Фейковая сессия устанавливает `ym_token`, `sc_connected`, `spotify_connected` → auth gate пропускает
- `docker-compose.dev.yml` standalone (без SSL-volumes) — нельзя случайно использовать вместо прода
- `.env.dev` добавлен в исключение `.gitignore` (содержит только фейк, безопасно коммитить)

**Итоговый подход:**
- Нет специального роута — `_ensure_user_id()` в dev mode возвращает `"dev_user"` → подхватывает UserSession из БД (сидируется вручную одной командой)
- `guard_dev_mode` validator в `config.py` сбрасывает `dev_mode=False` если URL не localhost → защита от случайного `.env.dev` на проде
- `LOG_LEVEL=DEBUG` + `LOG_FORMAT=pretty` указываются явно в `.env.dev`

**Файлы изменены/созданы:**
- `config.py` — `dev_mode: bool = False` + `guard_dev_mode` model_validator
- `api/routes/web.py` — `_ensure_user_id()` возвращает `"dev_user"` в dev mode
- `api/main.py` — startup warning при dev_mode=True
- `docker-compose.dev.yml` — новый файл
- `.env.dev` — новый файл (фейковые credentials)
- `.gitignore` — исключение `!.env.dev`
- `LOCAL_SETUP.md` — новый файл (инструкция)
- `tests/test_dev_mode.py` — 6 тестов (166 total, all pass)

---

## ✅ MM-75 — Ревью legacy-эндпоинтов — 2026-03-12

**Удалено:**
- `GET /import`, `GET /export` — чистые 303-заглушки, входящих ссылок не было
- `POST /auth/soundcloud` — dead code с MM-52 (нет форм в шаблонах)
- Тесты `test_import_page_redirects_to_home`, `test_export_page_redirects_to_home`

**Починено:**
- `GET /auth`: добавлены параметры `flow_from`/`flow_to`, сохраняются в session
- `POST /auth/yandex`: теперь вызывает `save_yandex_token()` (токен в БД) + восстанавливает флоу (`/?pf=...&pt=...`) вместо слепого возврата на `/auth`
- `save_yandex_token` добавлен в импорты `api/routes/web.py`

**Файлы:** `api/routes/web.py`, `tests/test_web_flow.py`
**Тесты:** 160 passed (−2 удалённых)

---

## ✅ MM-72 — Стандартизация migration/ — 2026-03-12

**Переименование файлов по destination-конвенции:**

| Старое | Новое |
|---|---|
| `migration/tracks.py` | `migration/sc_tracks.py` |
| `migration/playlists.py` | `migration/sc_playlists.py` |
| `migration/artists.py` | `migration/sc_artists.py` |
| `migration/yandex_tracks.py` | `migration/to_yandex.py` |
| `migration/spotify_tracks.py` | (слита в `sc_tracks.py`) |
| `migration/spotify_write.py` | `migration/to_spotify.py` |

**Обновлены импорты:** `worker/tasks.py`, `cli.py`, `tests/test_pipeline.py`
**Тесты:** 162 passed

---

## ✅ MM-63 — SVG brand icons — 2026-03-12

**Заменены emoji в `_SERVICE_ICONS` на inline SVG:**
- Yandex Music: звезда-эмблема из official wordmark (ph4.org/logo_logo.php?d=ya_music), `viewBox="59 0 23 22"`, цвет `#FFBC0D`
- Spotify: simpleicons path, цвет `#1ED760`
- SoundCloud: simpleicons path, цвет `#FF3300`
- File: Feather document icon, серый `#6B7280`
- Все SVG: `width="1em" height="1em"` — масштабируются через `text-2xl`/`text-lg` родителя

**Шаблоны:** добавлен `| safe` + `leading-none` в 5 местах (`index.html`, `flow_to.html` ×2, `flow_rest.html` ×2); hardcoded `📁` в `flow_to.html` заменён на `service_icons.get('file')`

**Файлы:** `api/routes/web.py`, `api/templates/index.html`, `api/templates/fragments/flow_to.html`, `api/templates/fragments/flow_rest.html`
**Тесты:** 162 passed

---

## Новые задачи добавлены — 2026-03-12

- **MM-76**: `sc_tracks+sc_playlists+sc_artists` → `to_soundcloud.py` (unified `to_*` naming)
- **MM-77**: SoundCloud как источник — проверить/дореализовать `fetch_liked_tracks` с OAuth
- **MM-78**: Async file export через ARQ worker
- **MM-79**: Унификация auth-слоя → `api/routes/auth.py` + согласованные паттерны; обсудить удаление ручного ввода YM-кода

## Git housekeeping — 2026-03-12

- Коммит `8cb0996 "здфт гзвфеу"` → `"plan update"` (scripted rebase)
- Удалены ветки: `mm-43-44-yandex-oauth-callback`, `mm-62-web-bugfixes` (локально + origin)
- `main` обновлён force-with-lease

---

## ✅ MM-69 — Rename file_csv → file — 2026-03-12

**Переименование FileAdapter.id с `file_csv` на `file`** (поддерживаются и CSV, и JSON, не только CSV).

### Изменённые файлы
- `core/services/file/adapter.py` — `id = "file"`, `name = "Файл (CSV/JSON)"`
- `core/i18n.py` — ключ `svc_file_csv` → `svc_file`
- `api/routes/web.py` — все 11 вхождений `"file_csv"` → `"file"` (иконки, маршрутизация, проверки)
- `api/templates/fragments/flow_to.html` — `data-to`, `hx-get`, `onclick`, условие `!= 'file'`
- `api/templates/fragments/flow_rest.html` — условия `'file_csv'` → `'file'`
- `tests/test_web_flow.py` — функции, docstring'и, assert'ы
- `alembic/versions/i9j0k1l2m3n4_rename_file_csv_to_file.py` — новая миграция: UPDATE from_service/to_service = 'file' WHERE = 'file_csv'

### Также в этой сессии
- PLAN.md отсортирован по номерам MM (MM-1 → MM-75)
- MM-27 создан (entrypoint.sh → scripts/), перемещён после MM-26
- MM-54 отмечена как ✅ (была ошибочно 🔲)
- MM-56 обновлена: акцент на точное воспроизведение веб-флоу
- Архитектурная диаграмма: SC URL исправлен на `api.soundcloud.com`; реестр сервисов обновлён

**Тесты:** 162 passed

---

## ✅ MM-68 (optional) + UI fixes + matrix fix — 2026-03-12

### File→File запрет
- `api/templates/fragments/flow_to.html` — карточка "В файл" теперь скрыта (`{% if from_service != 'file_csv' %}`), File→File невозможен
- Матрица переносов в PLAN.md и CLAUDE.md обновлена

### Компактный inline layout
- `flow_rest.html` — пикер файла перенесён из Settings в строку с кнопкой "Начать перенос" (compact: `max-w-[110px]`, без заголовка секции)
- `flow_rest.html` — dropdown формата (`w-20`, без заголовка) перенесён в строку с кнопкой "Скачать файл"

### MM-68 опциональные пункты
- `core/matcher.py` — параметры `score_track_match`: `ym_artist/ym_title/sc_artist/sc_title` → `source_artist/source_title/cand_artist/cand_title`
- `core/matcher.py` — параметры `find_best_match`: `ym_artist/ym_title` → `source_artist/source_title`; внутренний вызов обновлён
- `core/matcher.py` — `SCCandidate` docstring: явно указано что generic для любой платформы
- `core/matcher.py` — docstring модуля: "между стриминговыми платформами"

**Тесты:** 162 passed

---

## ✅ MM-70 + MM-71 + entrypoint housekeeping — 2026-03-12

**Ветка:** `main`

### MM-71 — Удаление мёртвого кода

Удалены эндпоинты недостижимые из UI после MM-67:
- `POST /import/preview`, `POST /import/start`, `POST /export/start` из `api/routes/web.py`
- Импорт `get_all_tracks` (использовался только в import_start)
- Шаблоны: `api/templates/import.html`, `api/templates/export.html`, `api/templates/fragments/import_preview.html`
- i18n ключи: `nav_import`, `nav_export`, весь блок Import (`import_*`, `preview_*`), большинство Export (`export_title/subtitle/back/content/liked_tracks/playlists/note/no_ym_token/format/csv_hint/json_hint/loading`)
- Оставлены: `export_fmt_label` + `export_btn` (используются в flow_rest.html), `GET /import` и `GET /export` редиректы, `_MAX_UPLOAD_BYTES`

### MM-70 — Auth-gate UX

- `flow_rest.html` — Jinja2 вычисление `auth_ok`; кнопка submit `disabled/opacity-50` когда не авторизован; подсказка `auth_required_hint` под кнопкой
- `flow_rest.html` — JS: последний активный чекбокс `content_types` нельзя снять
- `core/i18n.py` — добавлен ключ `auth_required_hint` (ru/en)
- `api/routes/web.py` — redirectы при missing token в `POST /migrate`: `/auth?error=` → `/?error=` (3 места)

### entrypoint.sh → scripts/

- `scripts/entrypoint.sh` создан, `entrypoint.sh` удалён из корня
- `Dockerfile.api` обновлён на новый путь

**Тесты:** 162 passed (без изменений — dead code не тестировался)

---

## ✅ MM-67 — Unified file import/export in main flow — 2026-03-12

**Ветка:** `main`

**Суть:** Убрали отдельные страницы `/import` и `/export`, интегрировали оба case в стандартный HTMX-флоу на главной странице.

**Изменённые файлы:**
- `core/i18n.py` — добавлены ключи `from_file_label`, `export_fmt_label`
- `worker/tasks.py` — `run_yandex_migration_job` + `run_spotify_write_job` получили `tracks_override: list[dict] | None`; при `is not None` пропускает fetch_liked_tracks
- `api/routes/web.py`:
  - `index`: `from_services["file_csv"] = _svc_name("file_csv", lang)`
  - `flow_to_step`: для file_csv → все адаптеры с WRITE_LIKED_TRACKS
  - `flow_rest`: `is_from_file`/`is_to_file` флаги, обработка None-адаптера
  - `GET /import`, `GET /export` → 303 → `/`
  - `POST /migrate`: `export_fmt`, `file` параметры; case to_file (export синхронно), case from_file (parse+job), обычный case
- `api/templates/index.html` — `enctype="multipart/form-data"`, убрана хардкодная карточка file
- `api/templates/fragments/flow_to.html` — export-карточка → HTMX button
- `api/templates/fragments/flow_rest.html` — полный conditional rendering для file кейсов

**Тесты:** 162 passed (+16 от 146)

---

## ✅ MM-68 — matcher.py адаптация для всех сервисов — 2026-03-12

**Суть:** Проверка и тесты что fuzzy-матчинг работает для всех комбинаций сервисов.

**Выводы:** `core/matcher.py` уже универсален — `transliterate_variants` пропускает EN, `normalize` работает для всех языков, `find_best_match` не привязан к SC.

**Добавлено:** `tests/test_matcher.py` — класс `TestCrossServiceMatching` (10 тестов): Spotify→SC EN, SC→YM, File→any, Cyrillic transliteration skip, feat. stripping, collab splits.

---

## ✅ MM-62 — Web UI bug fixes — 2026-03-11

**Ветка:** `mm-62-web-bugfixes`

### Bug 1: FROM service selection did nothing (Critical)

**Причина:** несовпадение имён query-параметров между HTMX URL и FastAPI сигнатурами.
- `?from=X` отправлялся из шаблона → FastAPI ожидал `?from_service=X` → 422 → HTMX ничего не рендерил
- То же для `?to=Y` → ожидалось `?to_service=Y`

**Фикс:** добавлен `Query(..., alias="from")` / `Query(..., alias="to")` в `flow_to_step` и `flow_rest`.

**Файл:** `api/routes/web.py` (добавлен `Query` в импорт, изменены сигнатуры двух endpoint'ов)

### Bug 2: Language switcher showed wrong flag

**Причина:** `base.html` показывал флаг ДРУГОГО языка (при `lang='en'` — 🇷🇺, при `lang='ru'` — 🇬🇧).

**Фикс:** переключатель теперь показывает текущий язык, ссылка ведёт на переключение:
- `lang='en'` → показывает 🇬🇧 EN, ссылка `/set-lang?lang=ru`
- `lang='ru'` → показывает 🇷🇺 RU, ссылка `/set-lang?lang=en`

**Файл:** `api/templates/base.html` (desktop + mobile блоки)

### Tests

Написаны 4 теста в `tests/test_web_flow.py`:
- `test_flow_to_step_returns_html` — GET `/api/flow/to-step?from=yandex_music` → 200
- `test_flow_to_step_missing_param_returns_422` — без `?from` → 422
- `test_flow_rest_returns_html` — GET `/api/flow/rest?from=yandex_music&to=soundcloud` → 200
- `test_flow_rest_missing_params_returns_422` — без `?to` → 422

Итого тестов: **145** (все проходят).

---

## 🔧 Bugfix сессия — 2026-03-10 (без MM-номера)

**Ветка:** `main` (хотфиксы напрямую)

**Проблема:** после деплоя MM-52 (SC OAuth) миграции падали с цепочкой ошибок.

### Баг 1: YM expired_token → непонятная ошибка
**Симптом:** `UnauthorizedError: ownerOtherwiseUserBindingError` глубоко в worker.
**Причина:** `_uid=None` → `users_likes_tracks()` без `user_id` → API отказывает.
**Фикс:** `core/yandex/client.py` — `_fetch_uid_from_yandex_id` теперь логирует response body при ошибке; `init()` поднимает `ValueError` с понятным сообщением если uid не получен.

### Баг 2: YM токен не сохранялся в БД после OAuth
**Симптом:** повторная авторизация через веб не помогала — worker использовал старый токен.
**Причина:** `auth_yandex_callback` сохранял токен только в cookie-сессию (`request.session["ym_token"]`), но не в БД. SC callback (`save_soundcloud_token`) не трогает YM поле.
**Фикс:**
- `core/db/crud.py` — добавлена `save_yandex_token(user_id, token)` — upsert только YM поля
- `core/db/__init__.py` — экспорт `save_yandex_token`
- `api/routes/web.py` — `auth_yandex_callback` теперь вызывает `await save_yandex_token(user_id, token)`

### Баг 3: SC _ensure_init падал из-за _user_id=None
**Симптом:** все треки падали с `RuntimeError: Клиент не инициализирован`.
**Причина:** `/me` возвращает 403 для неодобренных SC приложений → `_user_id` остаётся None → `_ensure_init` проверял `_session is None or _user_id is None`.
**Фикс:** `core/soundcloud/client.py` — убран `_user_id` из проверки `_ensure_init`.

### Баг 4: SC search возвращала пустые результаты (soundcloud-v2 библиотека)
**Симптом:** все треки `not_found`, 0 перенесено.
**Причина 1:** `soundcloud-v2` использовала захардкоженный `client_id=8TBFzNdd8fDb7PSVXtA7cigOe9VYgFf0` → 403.
**Причина 2:** Даже прямой запрос без `client_id` → 403.
**Фикс:** `core/soundcloud/client.py`:
- Удалена зависимость от `soundcloud-v2` библиотеки (`sc_lib`) в поиске
- `search_tracks` и `search_users` переписаны на прямые aiohttp запросы к `api-v2.soundcloud.com`
- Добавлен `client_id=settings.sc_client_id` в params запроса
- Удалены `self._sc` и `import soundcloud as sc_lib`

**Статус:** SC поиск возвращает 403 даже с OAuth токеном + client_id → нужно разбираться (задача MM-53).

**Файлы изменены:**
- `core/yandex/client.py`
- `core/soundcloud/client.py`
- `core/db/crud.py`
- `core/db/__init__.py`
- `api/routes/web.py`

---

## ✅ MM-52 — SoundCloud официальный OAuth

**Ветка:** `mm-52-sc-oauth`, слита в `main`

**Причина:** SC write API (like_track 404, create_playlist 403 Datadome) полностью заблокирован с EU datacenter IP для cookie-токенов. Официальный OAuth даёт proper credentials без Datadome.

**Что сделано:**
- `core/soundcloud/oauth.py` — `get_auth_url()`, `exchange_code()`, `refresh_access_token()`. Эндпоинты: `https://secure.soundcloud.com/oauth/authorize` и `/token`.
- `config.py` — добавлены `sc_client_id`, `sc_client_secret`, `sc_redirect_uri`
- `core/db/models.py` — `UserSession.soundcloud_refresh_token: Mapped[str | None]`
- `alembic/versions/f6a7b8c9d0e1_add_soundcloud_refresh_token.py` — новая миграция
- `core/db/crud.py` — `save_soundcloud_token(user_id, token, refresh_token)`, обновлён `load_user_session` (возвращает `soundcloud_refresh_token`)
- `core/db/__init__.py` — экспорт `save_soundcloud_token`
- `api/routes/web.py` — `GET /auth/soundcloud` (redirect + state), `GET /auth/soundcloud/callback` (exchange + save), `sc_done` в контексте auth страницы
- `api/templates/auth.html` — кнопка OAuth вместо cookie input
- `worker/tasks.py` — `_refresh_sc_token_if_needed()` helper, применён в `run_migration_job`, `run_file_migration_job`, `run_spotify_migration_job`
- `core/i18n.py` — `auth_sc_oauth_hint`, `auth_sc_oauth_btn`, `bot_sc_no_token`
- `bot/handlers/auth.py` — `_ask_soundcloud_token()`: если `sc_client_id` задан — показывает ссылку на web OAuth и очищает state (как Spotify); fallback — старый cookie метод

**Деплой:** нужно запустить `alembic upgrade head` на сервере + добавить `SC_CLIENT_ID/SECRET/REDIRECT_URI` в `.env`.

**Верификация эндпоинтов (по официальной доке + практике):**
- `PUT /me/track_likes/{track_id}` — правильный (404 ранее = Datadome, не неверный endpoint)
- `POST /playlists` — правильный (403 ранее = Datadome)
- `PUT /me/followings/{user_id}` — правильный
- Authorization Code Flow дает write-доступ без явных scopes (не документировано SC)

**Известные ограничения:**
- `like_track` не вызывается в продакшне — все воркер-джобы используют `playlist_mode=True` (треки собираются в sc_ids → плейлист в конце). Прямой лайк треков не протестирован с OAuth.
- `format_eta()` для SC завышает время: считает `sc_rate_limit_sleep + 1.5` сек/трек, но в `playlist_mode` sleep не происходит. Эта проблема pre-existing, не MM-52.
- `core/soundcloud/client.py` docstring и error message обновлены — убрано упоминание cookie.

---

## ✅ MM-24 — Экспорт треков в файл (standalone)

**Ветка:** `feature/mm-24-export`, слита в `main` (2026-03-07)

**Что сделано:**
- `Capability.EXPORT_TRACKS` — новый флаг в `core/services/base.py`
- `session_token_key` — атрибут адаптера для получения токена из сессии
- `core/export.py` — `export_library(service_id, token, fmt)` + `exportable_services()`
- `YandexMusicAdapter` — добавлен `EXPORT_TRACKS` + `fetch_liked_tracks()` → `[{artist, title}]`
- `api/routes/web.py` — `GET /export`, `POST /export/start` (Response с Content-Disposition)
- `api/templates/export.html` — динамический шаблон: список сервисов из `exportable_services()`, выбор CSV/JSON, JS loading state
- `api/templates/base.html` — ссылка «Экспорт» в nav
- `core/services/yandex/adapter.py` — EXPORT_TRACKS capability

**Формат:** совместим с `/import` (колонки `artist`, `title`)

**Merge-нюанс:** конфликт в `export.html` (mm-20 создал заглушку с i18n, mm-24 — полноценную с выбором сервиса и JS). Оставлена версия mm-24.

---

## ✅ MM-11 — Улучшенный поиск треков

**Проблема:** одиночный запрос `"{artist} {title}"` плохо работает с составными артистами типа "Земфира feat. Океан Ельзи".

**Что сделано:**
- `core/matcher.py` — `split_artists(artist)`: разбивает по `feat./ft./&/x/при уч./при участии`, возвращает уникальные части
- `migration/tracks.py` — `_process_one_track()`: `asyncio.gather` для параллельных запросов по каждому артисту, дедупликация кандидатов по `sc_id`, fallback title-only если пул пуст
- `core/soundcloud/client.py` — `_SEARCH_LIMIT` 5 → 10
- `tests/test_matcher.py` — `TestSplitArtists` (9 тестов)

---

## ✅ MM-12 — Список треков и статусы (веб)

**Что сделано:**
- `core/db/crud.py` — `get_tracks_page(migration_id, status, page, per_page=50)` → `(list[dict], int)`
- `core/db/__init__.py` — экспортирован
- `api/routes/web.py` — `GET /migrate/{id}/tracks?status=&page=1`; `_PER_PAGE=50`, `_TRACK_STATUS_LABEL`
- `api/templates/tracks.html` — таблица с фильтрами (Все/Перенесены/Не найдены/Ошибки/В очереди), пагинация
- `api/templates/result.html` — кнопка «Список треков»

---

## ✅ MM-13 — Обновление Telegram бота

**Что сделано:**
- `bot/api_client.py` — `get_not_found_tracks(migration_id)` → список строк из `/api/reports/{id}/not-found`
- `bot/handlers/migration.py` — переписан:
  - Кнопка «Отключиться от переноса» в прогресс-сообщении
  - Poll-цикл проверяет `state.get_state()` — если отключился, выходит
  - Финальное сообщение с клавиатурой: [Ненайденные треки N] + [Открыть в браузере] (URL) + [Новый перенос]
  - `migration:not_found:{id}` — первые 30 треков + ссылка на полный список
  - `migration:new` → `start_auth`
- `bot/handlers/status.py` — кнопка «Открыть в браузере» → `/migrate/{id}/tracks`

---

## ✅ Замена «миграция» → «перенос» в пользовательском тексте

**Затронуто:**
- Веб: `index.html`, `history.html`, `progress.html`, `result.html`, `tracks.html`
- `api/routes/web.py` — статусы «Завершён»/«Отменён» (мужской род)
- Бот: `migration.py`, `status.py`, `start.py`, `main.py` (описание команды)
- Не тронуто: код, переменные, логи, admin-шаблоны

---

## ✅ MM-14 — Импорт из файла (веб)

**Что сделано:**
- `core/services/file/adapter.py` — добавлены:
  - `get_columns(path)` — заголовки CSV/JSON
  - `preview_tracks(path, limit=20)` — первые N строк
  - `detect_column_mapping(columns)` — авто-маппинг по псевдонимам (artist/исполнитель/артист, title/название/трек)
  - `import_tracks(path, artist_col, title_col)` — маппинг с произвольными именами, BOM-safe
- `migration/tracks.py` — рефакторинг: `_run_pending_loop()` вынесен, `migrate_from_file_tracks(sc_client, migration_id, tracks_data)` использует `ym_id=file:{i}`
- `worker/tasks.py` — `run_file_migration_job(ctx, migration_id, sc_token, tracks, user_id)`
- `worker/main.py` — зарегистрирован в `functions`
- `api/routes/web.py` — `GET /import`, `POST /import/preview` (HTMX, temp file в сессии), `POST /import/start`
- `api/templates/import.html` — форма загрузки с HTMX
- `api/templates/fragments/import_preview.html` — таблица предпросмотра + column picker
- `api/templates/base.html` — ссылка «Импорт» в nav

---

## ✅ MM-15 — Ролевая модель

**Что сделано:**
- `core/db/models.py` — `UserSession.role: Mapped[str]` (server_default `"user"`)
- `alembic/versions/a1b2c3d4e5f6_add_user_role.py` — batch ALTER TABLE, up/downgrade
- `core/db/crud.py` — `load_user_session()` возвращает `role`; `set_user_role(user_id, role)`
- `core/db/__init__.py` — экспортирован `set_user_role`
- `api/routes/admin.py`:
  - `_is_admin(request)` → async: проверяет `is_admin` в сессии ИЛИ `role==admin` в БД
  - `_require_admin(request)` → async; все вызовы обновлены на `await`
  - `POST /admin/users/{user_id}/set-role` — принимает `role=user|admin`
  - `users_list` возвращает `role` для каждого пользователя
- `api/templates/admin/users.html` — колонка «Роль» + кнопки «Сделать admin»/«Снять admin»

**После деплоя:** `alembic upgrade head`

---

## ✅ MM-16 — Безопасность и rate limiting

**Что сделано:**
- `api/middleware.py` — `AllowedUsersWebMiddleware`: если `ALLOWED_USERS` задан, числовые user_id проверяются против списка; web_* пропускаются; exempt: /admin, /auth, /api, /health
- `api/main.py` — `AllowedUsersWebMiddleware` добавлен до `SessionMiddleware` (innermost = видит сессию)
- `api/deps.py` — `check_migration_rate_limit(user_id)`: Redis INCR `ratelimit:migrate:{user_id}`, TTL 3600, лимит 10/час
- `api/routes/web.py` — `check_migration_rate_limit` вызывается в `POST /migrate` и `POST /import/start`
- `api/routes/admin.py` — in-memory брутфорс защита `/admin/login`: 5 попыток по IP → 15 мин lockout; счётчик в `_login_attempts dict`

---

## ✅ MM-17 — Уведомления

**Что сделано:**
- `worker/notifications.py` — `notify_telegram(user_id, text)`: httpx к Bot API, пропускает `web_*` и случаи без токена; `migration_done_text()`, `migration_failed_text()`
- `worker/tasks.py` — оба job (`run_migration_job`, `run_file_migration_job`) шлют уведомление **сразу** при успехе (статистика + ссылка) и при ошибке
- Уведомления только в Telegram. В вебе — HTMX-поллинг каждые 3 с сам показывает результат.
- `check_sc_tokens_job` и `sc_token_expired_text()` **удалены** — уведомлять об истёкшем токене нецелесообразно.

---

## ✅ MM-18 — Улучшение интерфейса (веб)

> Только веб. Telegram-бот не менялся — у него нативная Telegram UI.

**Мобильная адаптация:**
- `base.html` — hamburger-меню (JS `.classList.toggle('open')`), responsive nav, sticky top bar
- Все страницы — `sm:grid-cols-*`, `flex-wrap`, `min-w-*` для корректного отображения на узких экранах

**Редизайн:**
- `rounded-2xl` карточки с `shadow-sm` вместо `rounded-xl` без теней
- Stat cards с цветовым кодированием: green/orange/red/gray
- Status badges с фоновым цветом (`bg-green-50 text-green-700` и т.д.) вместо plain text
- SVG-иконки: ноты в логотипе, check/error в баннерах, chevron в истории

**Анимации прогресса (`base.html` CSS):**
- `progress-indeterminate` — shimmer (@keyframes) пока перенос идёт
- Filled progress bar с адаптивным цветом (зелёный/индиго/оранжевый по % успеха)
- `animate-pulse-bar` — пульсирующая точка рядом со статусом
- `animate-slide-in` — плавное появление страницы
- `animate-spin-slow` — SVG-спиннер на начальной загрузке

**Страницы:**
- `base.html` — sticky nav, hamburger, CSS-анимации
- `index.html` — radio-режим (треки / треки+плейлисты+артисты), hint на /import
- `progress.html` — SVG-спиннер загрузки
- `fragments/status.html` — shimmer bar, pulse dot, 4-stat grid, filled bar при done
- `result.html` — status banner с иконкой, progress bar, 4-stat cards, responsive actions
- `history.html` — avatar `#id`, status badges, chevron, empty state с иконкой
- `auth.html` — step indicator (кружки 1→2, зелёная галочка при done)
- `tracks.html` — stat cards, status badges, rounded-2xl table, стилизованная пагинация
- `import.html` — info cards CSV/JSON, responsive form layout
- `fragments/import_preview.html` — 3-column mapping grid, styled preview table

**Код:**
- `api/routes/web.py` — `start_migrate` принимает `mode: str = Form("full")` → передаёт в ARQ job

---

## ✅ MM-19 — Централизованное логирование

**Что сделано:**
- `core/logger.py` — `setup_logger(service: str)`: два sink:
  - stderr colored (local dev)
  - stdout JSON (`serialize=True`) — Docker захватывает stdout, Promtail читает
  - `_inject_service()` вшивает `service` в `record.extra` каждой записи
- `api/main.py` — добавлен `setup_logger("api")` на уровне модуля (не в startup, чтобы логи были с самого старта)
- `run_worker.py` — добавлен `setup_logger("worker")` перед `run_worker()`
- `bot/main.py` — был `setup_logger()` без аргумента, теперь `setup_logger("bot")`
- `docker-compose.yml` — `logging: driver: json-file, max-size/max-file` на всех сервисах
- `docker-compose.monitoring.yml` — opt-in файл: Loki 2.9 + Promtail 2.9 + Grafana 10.2
- `monitoring/loki/config.yml` — filesystem storage, schema v13
- `monitoring/promtail/config.yml` — docker_sd_configs через `/var/run/docker.sock`, pipeline парсит loguru JSON, labels: `service`, `log_level`, `log_migration_id`
- `monitoring/grafana/provisioning/datasources/loki.yml` — auto-provision

**Запуск:**
```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

**Важные решения:**
- Мониторинг вынесен в отдельный compose-файл (не засоряет основной)
- JSON sink → stdout (а не в файл) — так Docker и Promtail подхватывают без лишних volume-маунтов
- `migration_id` попадёт в Loki label если код явно делает `logger.bind(migration_id=...)` в pipeline

---

## ✅ MM-20 — Тесты и ревью

**Ветка:** `mm-20`

**Что сделано:**
- `tests/test_pipeline.py` — исправлен `test_process_track_search_query_format` (broken после MM-11: fallback добавляет второй вызов search, assert_called_once падал → заменён на assert_any_call). Добавлены 4 новых теста:
  - `test_process_compound_artist_parallel_queries` — compound artist → параллельные запросы
  - `test_process_dedup_candidates_by_sc_id` — одинаковый sc_id → 1 кандидат
  - `test_process_title_only_fallback_when_compound_empty` — пустой пул → fallback title-only
- `tests/test_middleware.py` (новый) — 8 тестов для `AllowedUsersWebMiddleware`: no-allowlist, exempt paths, web_* user, allowed/blocked telegram id, no session
- `tests/test_rate_limit.py` (новый) — 8 тестов для `check_migration_rate_limit`: allow/deny, TTL logic, no Redis fallback, key format
- `tests/test_db_integration.py` (новый) — 17 тестов CRUD с изолированным in-memory SQLite (StaticPool fixture): migrations, tracks, user sessions
- `tests/test_api_integration.py` (новый) — 11 тестов через httpx.AsyncClient: /health, /api/services, /api/services/matrix, /api/migrations/{id}, 20-concurrent load tests
- **133 тестов, все зелёные**

**Ключевые решения:**
- DB fixture использует `StaticPool` + `create_async_engine` c изолированным in-memory SQLite и патчит `core.db.crud.AsyncSessionLocal` и `core.db.crud.engine`
- API тесты: `ASGITransport` не запускает lifespan → сервисы регистрируются через `autouse` fixture напрямую в `ServiceRegistry`
- Патч-таргеты: `config.settings` (middleware), `api.main.get_arq_pool` (rate limit), `api.main.create_pool` (arq Redis)

---

## ✅ MM-22 — Spotify интеграция

**Ветка:** `mm-22`, слита в `main` (2026-03-07)

**Что сделано:**
- `core/spotify/models.py` — SpotifyTrack, SpotifyPlaylist, SpotifyArtist
- `core/spotify/oauth.py` — Authorization Code Flow: `get_auth_url()`, `exchange_code()`, `refresh_access_token()`, CSRF state
- `core/spotify/client.py` — SpotifyClient: `get_liked_tracks()`, `get_playlists()`, `get_followed_artists()`, pagination
- `core/services/spotify/adapter.py` — SpotifyAdapter: READ_LIKED_TRACKS | READ_PLAYLISTS | READ_LIKED_ARTISTS
- `config.py` — `spotify_client_id`, `spotify_client_secret`, `spotify_redirect_uri`
- Alembic `c3d4e5f6a7b8` — `spotify_token TEXT NULL` в `user_sessions`
- `core/db/crud.py` — `save_spotify_token()`, `load_user_session()` возвращает `spotify_token`
- `migration/spotify_tracks.py` — `migrate_spotify_tracks()` переиспользует `_run_pending_loop`
- `worker/tasks.py` + `worker/main.py` — `run_spotify_migration_job` ARQ задача
- `api/routes/web.py` — `GET /auth/spotify`, `GET /auth/spotify/callback`, `start_migrate` для `from_service=spotify`
- `api/templates/auth.html` — Spotify секция (скрыта если `SPOTIFY_CLIENT_ID` не задан)
- `CLAUDE.md` обновлён с Spotify архитектурой

**Ограничения MVP:**
- Spotify → SC: только треки (плейлисты — TODO)
- Refresh token не сохраняется
- Spotify → File — TODO (добавлено в план как дополнение к MM-22)

---

## ✅ MM-22 доп. — Spotify → File export

**Ветка:** `mm-22-spotify-export`, слита в `main`

**Что сделано:**
- `core/services/spotify/adapter.py` — добавлены `EXPORT_TRACKS` capability, `session_token_key = "spotify_token"`, `fetch_liked_tracks(token)` → использует `SpotifyClient.get_liked_tracks()`, возвращает `[{artist, title}]` через `t.artists_str`
- `core/export.py` и шаблоны — без изменений (уже работали универсально)
- Spotify теперь появляется на странице `/export` автоматически

---

## ✅ MM-28 — Экспорт SoundCloud → File

**Что сделано:**
- `core/services/soundcloud/adapter.py` — добавлены `EXPORT_TRACKS` capability, `session_token_key = "soundcloud_token"`, `fetch_liked_tracks(token)` → `[{artist, title}]`
- `core/soundcloud/client.py` — `get_liked_tracks()`: GET `/me/track_likes` с пагинацией через `next_href`
- SoundCloud автоматически появляется на странице `/export`

---

## ✅ MM-32 — Читаемые логи в Docker

**Проблема:** два sink (stderr colored + stdout JSON) → Docker захватывал оба потока → каждое сообщение дублировалось в `docker logs`.

**Решение:** `LOG_FORMAT` env var (`pretty` | `json`) выбирает один sink:
- `pretty` (дефолт) → stderr, цветной (локальная разработка)
- `json` → stdout, newline-delimited JSON (Docker/Promtail)

**Файлы:**
- `core/logger.py` — один sink вместо двух, ветвление по `settings.log_format`
- `config.py` — `log_format: str = Field(default="pretty")`
- `docker-compose.yml` — `environment: LOG_FORMAT: json` для api/bot/worker
- `CLAUDE.md` — `LOG_FORMAT` задокументирован в env vars

---

## ✅ MM-35 — Текущий трек в прогрессе и логах

**Что сделано:**
- `migration/tracks.py` — `logger.info(f"[{i}/{total}] ▶ {track_str}")` перед каждым треком; `progress_callback` вызывается на каждом треке (убран `% 10`)
- `worker/tasks.py` — `_make_progress_callback(redis, migration_id)` → пишет `migration_current_track:{id}` в Redis (TTL 86400s) для всех трёх job типов
- `migration/spotify_tracks.py` — `run_spotify_migration()` принимает и пробрасывает `progress_callback`
- `api/routes/web.py` — `status_fragment` читает ключ из Redis, передаёт `current_track` в шаблон
- `api/templates/fragments/status.html` — `♪ Сейчас: artist — title` под прогресс-баром
- `api/routes/migrations.py` — REST `GET /api/migrations/{id}` включает `current_track`
- `bot/handlers/migration.py` — poll-цикл добавляет `♪ {current_track}` к тексту прогресса
- `core/i18n.py` — ключ `status_current_track` (ru/en)

---

## ✅ MM-34 — Файрвол на уровне провайдера (Timeweb Cloud)

Whitelist-режим в панели Timeweb Cloud → Сеть → Файрвол.

**RU сервер:** TCP 22 (все) + TCP 1080 (только 72.56.68.207). Проверено: посторонний IP не достучится до 1080, прокси с EU работает.
**EU сервер:** TCP 22 + HTTP (80) + HTTPS (443). Проверено: SSH заходит, порты доступны.

---

## ✅ MM-36 — Выбор сервиса в Telegram боте

**Ветка:** `mm-36-bot-service-selection`

**Что сделано:**
- `/migrate` теперь показывает inline-кнопки: «Яндекс Музыка 🎵» / «Spotify 🟢»
- `AuthFlow.selecting_from` — новый FSM-стейт для выбора источника
- `on_select_from_ym` — валидирует сохранённые токены YM+SC, если есть → сразу подтверждение
- `on_select_from_spotify` — если Spotify-токен есть в сессии → подтверждение; нет → сообщение со ссылкой на веб-интерфейс
- `_show_confirmation_spotify` — отдельный экран подтверждения для Spotify (показывает количество треков)
- `bot/api_client.py` — `start_migration()` принимает `from_service` и `spotify_token`
- `api/routes/migrations.py` — маршрутизирует на `run_spotify_migration_job` при `from_service=spotify`
- `bot/handlers/migration.py` — читает `from_service` из FSM data, передаёт в API

**Файлы:** `bot/handlers/auth.py`, `bot/handlers/migration.py`, `bot/api_client.py`, `api/routes/migrations.py`

---

---

## ✅ MM-41 — Spotify i18n в веб-интерфейсе

**Ветка:** `mm-41-spotify-i18n-web`

**Что сделано:**
- Добавлены 4 отсутствующих ключа в `core/i18n.py`: `auth_spotify_hint`, `auth_spotify_btn`, `auth_source_label`, `auth_dest_label`
- До этого `t('...')` возвращал сам ключ как строку — визуальный баг в UI
- Проверены все `t('...')` вызовы в templates/ — других пропущенных ключей нет

**Файлы:** `core/i18n.py`

---

## ✅ MM-40 — Динамическая оценка времени переноса

**Ветка:** `mm-40-eta`

**Что сделано:**
- `format_eta(track_count, to_service, lang, sc_rate_limit_sleep)` в `core/i18n.py`
- Оценки: SoundCloud ~`sleep+1.5` сек/трек, Spotify ~0.8, Яндекс Музыка ~1.5
- Ключи `eta_approx`, `eta_approx_hours`, `eta_label` (ru/en)
- Бот: ETA в обоих экранах подтверждения (YM→SC и Spotify→SC), убран хардкод
- Веб: ETA в `status.html` fragment по количеству pending-треков (обновляется каждые 3 сек)

**Файлы:** `core/i18n.py`, `bot/handlers/auth.py`, `api/routes/web.py`, `api/templates/fragments/status.html`

---

---

## ✅ MM-38 — Яндекс Музыка WRITE (лайки)

**Ветка:** `mm-38-ym-write`

**Что сделано:**
- `YandexMusicClient.search_tracks(query, limit)` — поиск треков через `client.search(type_="track")`
- `YandexMusicClient.like_track(track_id)` — лайк через `users_likes_tracks_add`
- `YandexMusicAdapter` — добавлен `WRITE_LIKED_TRACKS`, ServiceRegistry автоматически открывает Spotify→YM и SC→YM
- `SoundCloudAdapter` — добавлен `READ_LIKED_TRACKS` (метод `fetch_liked_tracks` уже был, флага не было)
- `migration/yandex_tracks.py` — `migrate_to_yandex(tracks_data, ym_client, migration_id)`: multi-query, dedup, fuzzy match через существующий `find_best_match`, sleep 1.0s/трек
- `worker/tasks.py` — `run_yandex_migration_job`: читает source через `ServiceRegistry.get(from_service).fetch_liked_tracks()`
- `api/routes/migrations.py` — поле `to_service` (`soundcloud` | `yandex_music`), маршрутизация на нужный ARQ job

**Файлы:** `core/yandex/client.py`, `core/services/yandex/adapter.py`, `core/services/soundcloud/adapter.py`, `migration/yandex_tracks.py`, `worker/tasks.py`, `worker/main.py`, `api/routes/migrations.py`

---

## ✅ MM-39 — Spotify WRITE (лайки треков + подписки на артистов)

**Ветка:** `mm-39-spotify-write`

**Что сделано:**
- `core/spotify/client.py` — добавлены 4 метода: `search_tracks()`, `like_track()`, `search_artists()`, `follow_artist()`
- `core/spotify/oauth.py` — расширены scopes: `user-library-modify user-follow-modify`
- `core/services/spotify/adapter.py` — добавлены `WRITE_LIKED_TRACKS | WRITE_LIKED_ARTISTS`
- `core/db/models.py` — добавлен `spotify_refresh_token: Mapped[str | None]`
- `alembic/versions/e5f6a7b8c9d0_add_spotify_refresh_token.py` — новая Alembic-миграция
- `core/db/crud.py` — `save_spotify_token(user_id, token, refresh_token=None)` сохраняет refresh_token; `load_user_session` возвращает `spotify_refresh_token`
- `api/routes/web.py` — OAuth callback теперь сохраняет `refresh_token` из Spotify
- `migration/spotify_write.py` — новый файл: `migrate_to_spotify(tracks_data, artists_data, spotify_client, migration_id)` — multi-query search, fuzzy match, like; `_run_pending_artists_loop` — поиск + follow_artist
- `worker/tasks.py` — `run_spotify_write_job`: авто-рефреш токена, читает треки + артистов через ServiceRegistry adapter, запускает `migrate_to_spotify`
- `worker/main.py` — зарегистрирован `run_spotify_write_job`
- `api/routes/migrations.py` — `to_service` расширен до `spotify`; `to_service=spotify` маршрутизирует на `run_spotify_write_job`; исправлен баг с пропущенным `mode` в `run_spotify_migration_job`
- `bot/api_client.py` — `start_migration()` принимает `to_service` и `spotify_refresh_token`

**Ключевые решения:**
- Spotify track ID — строка, не int → деdup по `hash(id) & 0x7FFFFFFF`, ID хранится в `sc_url`
- Авто-рефреш токена в воркере перед стартом — если refresh_token есть в БД, получаем свежий access_token
- Артисты: `fetch_liked_artists` вызывается через `getattr(adapter, ...)` — не все адаптеры его реализуют

**Файлы:** `core/spotify/client.py`, `core/spotify/oauth.py`, `core/services/spotify/adapter.py`, `core/db/models.py`, `alembic/...`, `core/db/crud.py`, `api/routes/web.py`, `migration/spotify_write.py`, `worker/tasks.py`, `worker/main.py`, `api/routes/migrations.py`, `bot/api_client.py`

---

## ✅ MM-37 — Настройка Spotify приложения

**Ветка:** `mm-37-spotify-credentials`

**Что сделано (код):**
- `core/spotify/oauth.py` — обновлён комментарий с актуальными scopes (READ + WRITE)
- `PLAN.md` — задача переведена в ✅, скорректированы scopes (убраны `playlist-modify-*`, которых нет)

**Операционные шаги (однократно на EU сервере):**
1. Создать app на developer.spotify.com → My Apps → Create app
2. Redirect URI: `{API_BASE_URL}/auth/spotify/callback`
3. Разрешить scopes: `user-library-read playlist-read-private user-follow-read user-library-modify user-follow-modify`
4. Добавить в `.env`: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`
5. `docker compose restart api bot worker`

**Код уже готов:** `spotify_enabled = bool(cfg.spotify_client_id)` — кнопка появляется автоматически когда env задан.

---

## ✅ MM-47 — SoundCloud playlist_mode

**Причина:** `PUT /me/track_likes/{id}` возвращает HTTP 404 для внешних токенов — SC заблокировал write-доступ.

**Решение:** вместо лайков — создание плейлистов "YM Liked #N":
1. Весь цикл `_run_pending_loop` — только поиск + матчинг (write API не вызывается)
2. Найденные `sc_id` собираются в памяти (`collected_ids`)
3. После цикла — `_create_liked_playlists`: батчи по `sc_playlist_batch_size` → `sc_client.create_playlist`

**Изменённые файлы:**
- `config.py` — добавлен `sc_playlist_batch_size: int = 500`
- `migration/tracks.py` — `playlist_mode` параметр во всей цепочке; `_process_one_track` → `tuple[str, int | None]`; новая `_create_liked_playlists`; импорт `settings` поднят на уровень модуля
- `migration/spotify_tracks.py` — пробрасывает `playlist_mode`
- `worker/tasks.py` — все три SC-джоба с `playlist_mode=True`
- `CLAUDE.md` — Architecture, Key Patterns, env vars обновлены

**Важно:** `YM_PROXY_URL` должен использовать `socks5://` (не `socks5h://` — aiohttp-socks не поддерживает)

---

## ✅ MM-50 — Лимит треков при переносе

**Цель:** тестирование на подмножестве из 5193 треков без переноса всей библиотеки.

**Реализация:**
- Лимит применяется сразу после загрузки из источника (`tracks_data[:track_limit]`), перед `bulk_insert_tracks`
- Веб: дропдаун "Лимит треков" (Все / 50 / 100 / 500) в `api/templates/index.html`; `0` → `None` в `web.py`
- Бот: отдельный шаг `selecting_limit` — после выбора режима спрашивает "Сколько треков?" (Все / 50 / 100 / 500)
- i18n: `index_track_limit`, `index_limit_all`, `index_limit_first`, `bot_select_limit`, `bot_btn_limit_all`, `bot_btn_limit_n`

**Изменённые файлы:**
- `migration/tracks.py` — `migrate_tracks`, `migrate_from_file_tracks` принимают `track_limit`
- `migration/spotify_tracks.py` — `migrate_spotify_tracks`, `run_spotify_migration` принимают `track_limit`
- `worker/tasks.py` — все 5 джобов пробрасывают `track_limit`
- `api/routes/migrations.py` — `StartMigrationRequest.track_limit: int | None = None`
- `api/routes/web.py` — `track_limit: int = Form(0)`, передаётся в enqueue_job
- `api/templates/index.html` — дропдаун выбора лимита
- `bot/api_client.py` — `start_migration(..., track_limit=None)`
- `bot/states.py` — добавлен `AuthFlow.selecting_limit`
- `bot/handlers/auth.py` — кнопки режима с callback `select_mode:tracks/full` (без лимита)
- `bot/handlers/migration.py` — `on_select_mode` → показывает лимит-кнопки; `on_start_migration` в стейте `selecting_limit`
- `core/i18n.py` — новые ключи для веба и бота
- `tests/test_pipeline.py` — тесты обновлены под `tuple` return из `_process_one_track`

---

## 📋 Ожидают реализации (по порядку)

- **MM-47** — ✅ SoundCloud playlist_mode (сделано ранее)
- **MM-50** — ✅ Лимит треков (сделано)
- **MM-9** — Домен + SSL/HTTPS (нужен домен для Spotify redirect URI и MM-43/44)
- **MM-37** (операционная часть) — прописать Spotify credentials на EU сервере (после домена)
- **MM-43** — Яндекс OAuth автоматический callback (веб) — требует MM-9
- **MM-44** — Яндекс OAuth через веб-посредник для бота — требует MM-43
- **MM-45** — SoundCloud мобильная авторизация (исследование + реализация)
- **MM-30** — README
- **MM-42** — YM WRITE артисты (отложено)
- **MM-26** — Монетизация (после функционала)
- **MM-10** — CI/CD (позже)

## 📝 Заметки

- `WEB_ENABLED=false` отключает и веб UI, и админку (оба роутера в одном `if settings.web_enabled` блоке в `api/main.py`). Internal API + бот продолжают работать.
