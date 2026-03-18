import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { refreshAccessToken, getOAuthStartUrl } from '../api/auth'
import { fetchUserStatus, isConnected } from '../api/services'
import type { UserStatus } from '../api/services'
import { startMigration } from '../api/migrations'
import { getAccessToken } from '../api/client'

const SERVICE_LABELS: Record<string, string> = {
  yandex_music: 'Яндекс Музыка',
  spotify: 'Spotify',
  soundcloud: 'SoundCloud',
  file: 'Файл (CSV/JSON)',
}

const SERVICE_ICONS: Record<string, string> = {
  yandex_music: '🎵',
  spotify: '🎧',
  soundcloud: '☁️',
  file: '📄',
}

export default function MigratePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const ran = useRef(false)

  const fromSvc = searchParams.get('from') ?? ''
  const toSvc = searchParams.get('to') ?? ''

  const [userStatus, setUserStatus] = useState<UserStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Settings
  const [limit, setLimit] = useState<number | undefined>(undefined)
  const [skipAlready, setSkipAlready] = useState(true)
  const [likeTracks, setLikeTracks] = useState(false)
  const [spotifyPlaylistMode, setSpotifyPlaylistMode] = useState(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    if (!fromSvc || !toSvc) {
      navigate('/', { replace: true })
      return
    }

    async function init() {
      try {
        if (!getAccessToken()) {
          await refreshAccessToken()
        }
        if (getAccessToken()) {
          const status = await fetchUserStatus()
          setUserStatus(status)
        }
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [])

  const needsAuth = (svcId: string) => svcId !== 'file'
  const isAuth = (svcId: string) => {
    if (!userStatus) return false
    return isConnected(userStatus, svcId)
  }

  const authServices = [fromSvc, toSvc]
    .filter((id, idx, arr) => arr.indexOf(id) === idx && needsAuth(id))

  const canStart =
    authServices.every(id => isAuth(id)) &&
    !starting

  async function handleStart() {
    if (!canStart) return
    setStarting(true)
    setError(null)
    try {
      const result = await startMigration({
        from_service: fromSvc,
        to_service: toSvc,
        limit: limit,
        skip_already_migrated: fromSvc !== 'file' ? skipAlready : undefined,
        like_tracks: toSvc === 'soundcloud' ? likeTracks : undefined,
        spotify_playlist_mode: toSvc === 'spotify' ? spotifyPlaylistMode : undefined,
      })
      navigate(`/migrate/${result.migration_id}/progress`)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Неизвестная ошибка'
      setError(msg)
      setStarting(false)
    }
  }

  if (loading) {
    return (
      <div className="page-center">
        <p className="muted">Загрузка…</p>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="container">
        {/* Back */}
        <Link to="/" className="back-link">← Назад</Link>

        {/* Direction header */}
        <div className="page-header">
          <h1 className="title">
            {SERVICE_ICONS[fromSvc]} {SERVICE_LABELS[fromSvc] ?? fromSvc}
            {' → '}
            {SERVICE_ICONS[toSvc]} {SERVICE_LABELS[toSvc] ?? toSvc}
          </h1>
          <p className="subtitle">Настройте параметры миграции</p>
        </div>

        {error && (
          <div className="alert alert-error">{error}</div>
        )}

        {/* Auth section */}
        {authServices.length > 0 && (
          <div className="section">
            <div className="section-label">Авторизация</div>
            <div className="auth-list">
              {authServices.map(svcId => (
                <div key={svcId} className="auth-row">
                  <span>
                    {SERVICE_ICONS[svcId]} {SERVICE_LABELS[svcId] ?? svcId}
                  </span>
                  {isAuth(svcId) ? (
                    <span className="auth-ok">✓ Подключено</span>
                  ) : (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        window.location.href = getOAuthStartUrl(svcId, fromSvc, toSvc)
                      }}
                    >
                      Войти
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Settings */}
        <div className="section">
          <div className="section-label">Настройки</div>

          <div className="settings-list">
            {/* Track limit */}
            <div className="setting-row">
              <label className="setting-label" htmlFor="limit-select">
                Количество треков
              </label>
              <select
                id="limit-select"
                className="setting-select"
                value={limit ?? ''}
                onChange={e => setLimit(e.target.value ? Number(e.target.value) : undefined)}
              >
                <option value="">Все</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="500">500</option>
              </select>
            </div>

            {/* Skip already migrated */}
            {fromSvc !== 'file' && (
              <div className="setting-row">
                <label className="setting-label" htmlFor="skip-check">
                  Пропускать уже перенесённые
                </label>
                <input
                  id="skip-check"
                  type="checkbox"
                  className="setting-checkbox"
                  checked={skipAlready}
                  onChange={e => setSkipAlready(e.target.checked)}
                />
              </div>
            )}

            {/* Like tracks — only for SoundCloud destination */}
            {toSvc === 'soundcloud' && (
              <div className="setting-row">
                <label className="setting-label" htmlFor="like-check">
                  Лайкать треки напрямую
                  <span className="muted"> (иначе — в плейлист)</span>
                </label>
                <input
                  id="like-check"
                  type="checkbox"
                  className="setting-checkbox"
                  checked={likeTracks}
                  onChange={e => setLikeTracks(e.target.checked)}
                />
              </div>
            )}

            {/* Spotify playlist mode */}
            {toSvc === 'spotify' && (
              <div className="setting-row">
                <label className="setting-label" htmlFor="spotify-playlist-check">
                  Создать плейлист
                  <span className="muted"> (иначе — добавить в лайки)</span>
                </label>
                <input
                  id="spotify-playlist-check"
                  type="checkbox"
                  className="setting-checkbox"
                  checked={spotifyPlaylistMode}
                  onChange={e => setSpotifyPlaylistMode(e.target.checked)}
                />
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="actions">
          <button
            className="btn btn-primary"
            disabled={!canStart}
            onClick={handleStart}
          >
            {starting ? 'Запуск…' : 'Начать'}
          </button>
        </div>
      </div>
    </div>
  )
}
