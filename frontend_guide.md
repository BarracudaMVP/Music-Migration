# Frontend Guide — Music Migration SPA

> Актуально на 2026-03-26 (после MM-99).
> Для фронтендера, который подключается к проекту.

---

## Стек

| Что | Версия / детали |
|-----|-----------------|
| React | 19 (StrictMode) |
| TypeScript | да |
| Bundler | Vite |
| Routing | React Router v6 |
| CSS | plain CSS (`index.css`) — никаких UI-библиотек |
| State | только `useState` / `useRef` — нет Redux, нет Zustand |
| i18n | самописный (`src/i18n.ts`) |
| Auth | JWT Bearer (access token в памяти, refresh в `localStorage`) |
| API | самописный `fetch`-клиент (`src/api/client.ts`) |

---

## Структура файлов

```
frontend/src/
├── main.tsx                  — точка входа: StrictMode + BrowserRouter + <App/>
├── App.tsx                   — роутер, LangContext, LangSwitcher, AdminRoute
├── i18n.ts                   — переводы RU/EN + хелперы t(), tStatus(), tService(), formatDate()
├── index.css                 — все стили проекта
│
├── api/
│   ├── client.ts             — базовый fetch-клиент (JWT, ApiError)
│   ├── auth.ts               — exchangeCode, refreshAccessToken, getTokenRole, getOAuthStartUrl
│   ├── migrations.ts         — startMigration, getMigration, listMigrations, parseImportFile
│   ├── services.ts           — fetchServices, fetchMatrix, fetchUserStatus, isConnected
│   └── admin.ts              — fetchStats, listUsers
│
└── pages/
    ├── HomePage.tsx          — выбор FROM/TO + авторизация сервисов
    ├── AuthCallbackPage.tsx  — OAuth callback: exchangeCode → redirect
    ├── MigratePage.tsx       — настройки миграции + запуск
    ├── ProgressPage.tsx      — прогресс (polling 2s), статистика, результат
    ├── HistoryPage.tsx       — список миграций пользователя
    └── admin/
        ├── AdminLayout.tsx   — sidebar навигация (Dashboard / Migrations / Users)
        ├── AdminDashboardPage.tsx — карточки stats + by_status + recent[10]
        ├── AdminMigrationsPage.tsx — все миграции системы + фильтры + пагинация
        └── AdminUsersPage.tsx     — все пользователи + пагинация
```

---

## Роутинг

```
/                          → HomePage
/auth/callback             → AuthCallbackPage   (OAuth redirect)
/migrate?from=X&to=Y       → MigratePage
/migrate/:id/progress      → ProgressPage
/history                   → HistoryPage

/dashboard                 → AdminLayout → AdminDashboardPage   (require admin)
/migrations                → AdminLayout → AdminMigrationsPage  (require admin)
/users                     → AdminLayout → AdminUsersPage        (require admin)
```

`AdminRoute` — компонент-враппер: если `getTokenRole() !== 'admin'`, редиректит на `/`.

---

## Auth flow

### JWT в памяти (не в localStorage)

Access token хранится в переменной модуля (`let accessToken = null` в `client.ts`).
При перезагрузке страницы — пропадает. Восстанавливается через refresh.

### Refresh token

Хранится в `localStorage` под ключом `refresh_token` (строка, opaque hex).

### Старт приложения (каждая страница)

```typescript
if (!getAccessToken()) {
  await refreshAccessToken()   // читает refresh из localStorage, обменивает на access
}
```

В dev-режиме (`DEV_MODE=true` на сервере) `GET /api/v1/auth/me` без токена возвращает 200 с `user_id="dev_user"` — auto-login без OAuth.

### OAuth flow

1. Пользователь нажимает "Connect" на сервис
2. `getOAuthStartUrl(svcId, flowFrom, flowTo)` → `/api/v1/auth/{slug}?flow_from=...&flow_to=...`
3. Сервер делает redirect к провайдеру (Yandex / Spotify / SoundCloud)
4. Провайдер редиректит на `/api/v1/auth/{svc}/callback?code=...`
5. Сервер сохраняет токен в БД, генерирует short-lived `oauth_code` (Redis 30s)
6. Сервер редиректит на `/auth/callback?code={oauth_code}&flow_from=...&flow_to=...`
7. `AuthCallbackPage` вызывает `exchangeCode(code)` → `POST /api/v1/auth/exchange`
8. Получает `{access_token, refresh_token}` → сохраняет в память + localStorage
9. Редиректит на `/migrate?from=...&to=...`

### Маппинг service ID → OAuth slug

```typescript
const SERVICE_AUTH_SLUG: Record<string, string> = {
  yandex_music: 'yandex',   // НЕ yandex_music — важно!
}
// spotify, soundcloud — без маппинга (slug === id)
```

---

## API клиент

`src/api/client.ts` — тонкая обёртка над `fetch`:

```typescript
const BASE = '/api/v1'
let accessToken: string | null = null

// Все запросы добавляют Authorization: Bearer {token} если token != null
// При !res.ok — бросает ApiError(status, text)
// 204 → возвращает undefined
```

Все api-функции используют `api.get<T>`, `api.post<T>`, `api.delete<T>`.

**Пример добавления нового endpoint:**

```typescript
// src/api/migrations.ts
export function cancelMigration(id: number): Promise<void> {
  return api.delete<void>(`/migrations/${id}`)
}
```

---

## i18n

`src/i18n.ts` — простой объект с ключами, никаких внешних библиотек.

```typescript
export function t(key: TKey, lang: string): string
export function tStatus(status: string, lang: string): string  // pending/running/done/failed/cancelled
export function tService(svcId: string, lang: string): string  // yandex_music/spotify/soundcloud/file
export function formatDate(dt: string | null, lang: string): string
```

Язык хранится в `localStorage('lang')` через `LangContext` в `App.tsx`.
Все страницы получают язык через `const { lang } = useLang()`.

**Добавить новый ключ:**

```typescript
// В translations.ru:
my_new_key: 'Русский текст',
// В translations.en:
my_new_key: 'English text',
// TypeScript автоматически подберёт тип TKey через keyof typeof translations.ru
```

---

## Страницы

### HomePage

**Задача:** выбор FROM / TO сервиса, проверка авторизации, переход к настройкам.

**Логика:**
1. `refreshAccessToken()` — восстановить сессию
2. `fetchServices()` + `fetchMatrix()` — получить список сервисов и матрицу переходов
3. `fetchUserStatus()` → `isConnected(status, svcId)` — проверить авторизован ли пользователь
4. FROM-сервисы = уникальные значения `matrix[].from`
5. TO-сервисы = `matrix.filter(e => e.from === fromSvc).map(e => e.to)`
6. `canProceed = fromSvc && toSvc && все нужные сервисы авторизованы`
7. `needsAuth(svcId) = svcId !== 'file'` — file не требует OAuth

**Примечание:** `SERVICE_ICONS` — дублируется в `MigratePage.tsx` (TODO для рефактора MM-100).

### AuthCallbackPage

**Задача:** обменять `oauth_code` на JWT.

```
/auth/callback?code=XXX&flow_from=yandex_music&flow_to=soundcloud
→ exchangeCode(XXX) → {access_token, refresh_token}
→ navigate(/migrate?from=yandex_music&to=soundcloud)
```

Если code нет или обмен упал → `navigate('/?auth_error=1')`.

### MigratePage

**Задача:** настройки миграции и запуск.

URL-параметры: `?from=yandex_music&to=soundcloud`.

**Настройки:**
| Параметр | Когда показывается |
|----------|--------------------|
| Лимит треков | всегда (0 = без лимита) |
| Пропускать уже перенесённые | from !== 'file' |
| Лайкать напрямую | to === 'soundcloud' (иначе playlist mode) |
| Создать плейлист | to === 'spotify' |
| Название плейлиста | to === 'spotify' && spotifyPlaylistMode |
| Файл для импорта | from === 'file' |
| Типы контента | from !== 'file' (tracks / playlists / artists) |

**canStart:**
- Все нужные сервисы авторизованы
- Если from=file — файл выбран
- `!starting` (защита от двойного клика)

**Запуск:**
1. Если from=file → `parseImportFile(file)` → `tracksOverride: TrackImport[]`
2. `startMigration({...}) → {migration_id}`
3. `navigate(/migrate/{id}/progress)`

### ProgressPage

**Задача:** polling статуса миграции каждые 2 секунды.

Статусы: `pending | running | done | failed | cancelled`.
`TERMINAL_STATUSES = {'done', 'failed', 'cancelled'}` — при достижении polling останавливается.

**Что отображается:**
- Прогресс-бар (`doneCount / total`)
- `current_track` — текущий трек (если status=running)
- Статистика: liked / in_playlist (оба = success), not_found, error, pending
- При `result_path` (Spotify/YM playlist URL) — кнопка "Открыть плейлист"
- При `to_service='file' && status='done'` — кнопки CSV↓ / JSON↓
- При terminal — кнопки "Новая миграция" + "История"

**Антипаттерн (известно):** `useRef(false)` вместо `AbortController` для предотвращения двойного запуска в StrictMode.

### HistoryPage

Список миграций пользователя. Каждый ряд — ссылка на ProgressPage.
Показывает: FROM → TO, статус, дату, кол-во успешных/не найденных, ссылку на плейлист.

---

## Admin панель

Доступна только для `role='admin'` (проверяется через `getTokenRole()` из JWT payload).

**AdminRoute:**
```typescript
function AdminRoute({ children }) {
  if (getTokenRole() !== 'admin') return <Navigate to="/" />
  return <>{children}</>
}
```

**Страницы:**
- `AdminDashboardPage` — карточки (total_migrations, total_users) + by_status + recent[10]
- `AdminMigrationsPage` — все миграции, фильтр по user_id / status, пагинация через URL-параметры (`?user_id=...&status=...&page=...`)
- `AdminUsersPage` — список пользователей с кол-вом миграций

**API (бэкенд):**
- `GET /api/v1/stats` — admin only
- `GET /api/v1/users?page=N` — admin only
- `GET /api/v1/migrations?user_id=X&status=Y&page=N` — admin видит все, user видит только свои

---

## Типы данных (migration-related)

```typescript
// src/api/migrations.ts

interface TrackImport { artist: string; title: string }

interface StartMigrationRequest {
  from_service: string
  to_service: string
  content_types?: string[]
  limit?: number
  skip_already_migrated?: boolean
  like_tracks?: boolean
  spotify_playlist_mode?: boolean
  spotify_playlist_name?: string
  tracks_override?: TrackImport[]
}

interface TrackStats {
  liked?: number; in_playlist?: number; not_found?: number
  error?: number; pending?: number
}

interface Migration {
  id: number; user_id: string
  from_service: string; to_service: string
  status: string; created_at: string | null
  result_path?: string | null
  stats?: TrackStats
}

interface MigrationDetail {
  migration: Migration
  stats: TrackStats | null
  current_track: string | null
}
```

---

## File import / export

### Import (CSV/JSON → треки)

`parseImportFile(file: File): Promise<TrackImport[]>` — в браузере:
- Проверка `file.size > 5 * 1024 * 1024` → ошибка
- `.json` → `JSON.parse` в try-catch, проверка `Array.isArray`
- `.csv` → сплит по строкам, поиск колонок `artist` и `title` (case-insensitive)
- Возвращает `TrackImport[]` — передаётся как `tracks_override` в `startMigration`

### Export (CSV/JSON ← бэкенд)

При `to_service='file' && status='done'` на ProgressPage:
```html
<a href="/api/v1/migrations/{id}/export?fmt=csv" download="migration-{id}.csv">CSV ↓</a>
<a href="/api/v1/migrations/{id}/export?fmt=json" download="migration-{id}.json">JSON ↓</a>
```
Браузер скачивает файл напрямую. Authorization header не нужен т.к. fetch не используется — работает через `download` атрибут.

> **Потенциальная проблема:** если access token истёк, download не будет авторизован.
> Пока приемлемо — пользователь чаще всего на этой странице сразу после завершения миграции.

---

## CSS-классы (основные)

```
.page              — контейнер страницы (padding, min-height)
.container         — центрирование + max-width
.page-header       — заголовок страницы
.title             — h1
.subtitle          — подзаголовок
.section           — секция с отступом
.section-label     — лейбл секции (uppercase, muted)
.service-grid      — grid для карточек сервисов
.service-card      — карточка сервиса (кнопка)
.service-card.selected — выбранная карточка
.auth-list / .auth-row — список авторизаций
.auth-ok           — зелёный "✓ Connected"
.settings-list / .setting-row — список настроек
.setting-select / .setting-input / .setting-checkbox — инпуты
.btn / .btn-primary / .btn-ghost / .btn-sm — кнопки
.status-badge      — бейдж статуса
.status-running / .status-done / .status-failed etc. — цвет бейджа
.progress-bar / .progress-fill — прогресс-бар
.stat-rows / .stat-row / .stat-success / .stat-error — статистика
.migration-list / .migration-row — список миграций в History
.alert / .alert-error — алерты
.muted             — серый текст
.admin-layout / .admin-sidebar / .admin-table — admin UI
.lang-switcher / .lang-btn — переключатель языка (fixed top-right)
```

---

## Известные проблемы / технический долг (MM-100)

1. **`useRef(false)` вместо `AbortController`** — во всех 5 страницах (HomePage, MigratePage, ProgressPage, HistoryPage, AdminDashboardPage). React StrictMode дважды запускает эффекты — `useRef` предотвращает двойной fetch. Правильное решение — `AbortController` + `signal` в fetch.

2. **Дублирование `SERVICE_ICONS`** — в `HomePage.tsx:10-15` и `MigratePage.tsx:12-17`. Надо вынести в `src/constants.ts`.

3. **Дублирование блока авторизации сервиса** — JSX-блок auth row (25 строк) копируется в `HomePage.tsx:159-183` и `MigratePage.tsx:163-189`. Надо вынести в `ServiceAuthSection.tsx`.

4. **Паттерн loading/error/data** — повторяется в 6+ страницах. Надо вынести в хук `useApiCall<T>(fn)`.

5. **Дублирование пагинации** — в `AdminMigrationsPage.tsx` и `AdminUsersPage.tsx`. Надо вынести в `Pagination.tsx`.

6. **Нет `ErrorBoundary`** — при runtime ошибке в компоненте упадёт белый экран. Надо добавить `ErrorBoundary` в `App.tsx`.

---

## Локальная разработка

```bash
# Backend (FastAPI + Redis + PostgreSQL):
docker compose -f docker-compose.dev.yml up

# Frontend (hot reload на :3000):
cd frontend
npm install
npm run dev
# → http://localhost:3000
# Vite проксирует /api/* → http://localhost:8000
```

В `.env.dev` установлен `DEV_MODE=true` — авторизация не нужна, все запросы идут от `dev_user`.

---

## Добавление нового сервиса (чеклист для фронтенда)

1. `src/api/services.ts` — `isConnected` добавить ветку для нового `serviceId`
2. `src/pages/HomePage.tsx` — добавить иконку в `SERVICE_ICONS` (и `MigratePage.tsx` пока дублирование не убрано)
3. `src/i18n.ts` — добавить `svc_new_service: 'Название'` в RU и EN
4. `tService()` в `i18n.ts` — добавить case (если не покрывается автоматически через `svc_` prefix)
5. Бэкенд: зарегистрировать `Adapter` в `ServiceRegistry` — SPA получает сервис через `/api/v1/services`

---

## Добавление нового endpoint (чеклист)

```typescript
// 1. Добавить функцию в нужный api/*.ts файл
export function doSomething(id: number): Promise<SomeType> {
  return api.post<SomeType>(`/something/${id}`)
}

// 2. Использовать в компоненте
const [loading, setLoading] = useState(false)
const [error, setError] = useState<string | null>(null)

async function handleClick() {
  setLoading(true)
  try {
    await doSomething(id)
    // обновить UI
  } catch (e) {
    setError(e instanceof Error ? e.message : t('error_unknown', lang))
  } finally {
    setLoading(false)
  }
}
```

---

## Деплой

В проде SPA обслуживается nginx как статика (`nginx/spa.conf: try_files → /index.html`).
Vite собирает в `frontend/dist/` через `Dockerfile.frontend.prod` (multi-stage: node build → nginx:alpine).
Все API-запросы идут на тот же домен, nginx проксирует `/api/` → `api:8000`.
