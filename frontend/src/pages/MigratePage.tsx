import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { refreshAccessToken, getOAuthStartUrl } from '../api/auth'
import { fetchUserStatus, isConnected } from '../api/services'
import type { UserStatus } from '../api/services'
import { startMigration, parseImportFile } from '../api/migrations'
import type { TrackImport } from '../api/migrations'
import { getAccessToken } from '../api/client'
import { useLang } from '../App'
import { t, tService } from '../i18n'

const SERVICE_ICONS: Record<string, string> = {
  yandex_music: '🎵',
  spotify: '🎧',
  soundcloud: '☁️',
  file: '📄',
}

export default function MigratePage() {
  const { lang } = useLang()
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
  const [spotifyPlaylistName, setSpotifyPlaylistName] = useState('')
  const [contentTypes, setContentTypes] = useState<string[]>(['tracks'])
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

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
    !starting &&
    (fromSvc !== 'file' || importFile !== null)

  async function handleStart() {
    if (!canStart) return
    setStarting(true)
    setError(null)
    setImportError(null)

    let tracksOverride: TrackImport[] | undefined
    if (fromSvc === 'file') {
      if (!importFile) {
        setError(t('error_no_file', lang))
        setStarting(false)
        return
      }
      try {
        tracksOverride = await parseImportFile(importFile)
        if (tracksOverride.length === 0) {
          setImportError(t('error_empty_file', lang))
          setStarting(false)
          return
        }
      } catch {
        setImportError(t('error_read_file', lang))
        setStarting(false)
        return
      }
    }

    try {
      const result = await startMigration({
        from_service: fromSvc,
        to_service: toSvc,
        content_types: fromSvc === 'file' ? ['tracks'] : contentTypes,
        limit: limit,
        skip_already_migrated: fromSvc !== 'file' ? skipAlready : undefined,
        like_tracks: toSvc === 'soundcloud' ? likeTracks : undefined,
        spotify_playlist_mode: toSvc === 'spotify' ? spotifyPlaylistMode : undefined,
        spotify_playlist_name: toSvc === 'spotify' && spotifyPlaylistMode && spotifyPlaylistName
          ? spotifyPlaylistName
          : undefined,
        tracks_override: tracksOverride,
      })
      navigate(`/migrate/${result.migration_id}/progress`)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('error_unknown', lang)
      setError(msg)
      setStarting(false)
    }
  }

  if (loading) {
    return (
      <div className="page-center">
        <p className="muted">{t('loading', lang)}</p>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="container">
        {/* Back */}
        <Link to="/" className="back-link">{t('back', lang)}</Link>

        {/* Direction header */}
        <div className="page-header">
          <h1 className="title">
            {SERVICE_ICONS[fromSvc]} {tService(fromSvc, lang)}
            {' → '}
            {SERVICE_ICONS[toSvc]} {tService(toSvc, lang)}
          </h1>
          <p className="subtitle">{t('migrate_subtitle', lang)}</p>
        </div>

        {error && (
          <div className="alert alert-error">{error}</div>
        )}
        {importError && (
          <div className="alert alert-error">{importError}</div>
        )}

        {/* Auth section */}
        {authServices.length > 0 && (
          <div className="section">
            <div className="section-label">{t('auth', lang)}</div>
            <div className="auth-list">
              {authServices.map(svcId => (
                <div key={svcId} className="auth-row">
                  <span>
                    {SERVICE_ICONS[svcId]} {tService(svcId, lang)}
                  </span>
                  {isAuth(svcId) ? (
                    <span className="auth-ok">{t('connected', lang)}</span>
                  ) : (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        window.location.href = getOAuthStartUrl(svcId, fromSvc, toSvc)
                      }}
                    >
                      {t('connect', lang)}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Settings */}
        <div className="section">
          <div className="section-label">{t('settings', lang)}</div>

          <div className="settings-list">
            {/* Track limit */}
            <div className="setting-row">
              <label className="setting-label" htmlFor="limit-select">
                {t('track_limit', lang)}
              </label>
              <select
                id="limit-select"
                className="setting-select"
                value={limit ?? ''}
                onChange={e => setLimit(e.target.value ? Number(e.target.value) : undefined)}
              >
                <option value="">{t('all', lang)}</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="500">500</option>
              </select>
            </div>

            {/* Skip already migrated */}
            {fromSvc !== 'file' && (
              <div className="setting-row">
                <label className="setting-label" htmlFor="skip-check">
                  {t('skip_migrated', lang)}
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
                  {t('like_directly', lang)}
                  <span className="muted"> {t('otherwise_playlist', lang)}</span>
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
                  {t('create_playlist', lang)}
                  <span className="muted"> {t('otherwise_likes', lang)}</span>
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

            {/* Spotify playlist name */}
            {toSvc === 'spotify' && spotifyPlaylistMode && (
              <div className="setting-row">
                <label className="setting-label" htmlFor="playlist-name">
                  {t('playlist_name', lang)}
                </label>
                <input
                  id="playlist-name"
                  type="text"
                  className="setting-input"
                  placeholder="Music Migration"
                  value={spotifyPlaylistName}
                  onChange={e => setSpotifyPlaylistName(e.target.value)}
                />
              </div>
            )}

            {/* File import picker */}
            {fromSvc === 'file' && (
              <div className="setting-row">
                <label className="setting-label" htmlFor="import-file">
                  {t('import_file', lang)}
                </label>
                <input
                  id="import-file"
                  type="file"
                  accept=".csv,.json"
                  className="setting-file"
                  onChange={e => {
                    setImportFile(e.target.files?.[0] ?? null)
                    setImportError(null)
                  }}
                />
              </div>
            )}

            {/* Content types */}
            {fromSvc !== 'file' && (
              <div className="setting-row">
                <span className="setting-label">{t('what_to_migrate', lang)}</span>
                <div className="setting-checkboxes">
                  {(['tracks', 'playlists', 'artists'] as const).map(ct => (
                    <label key={ct} className="setting-checkbox-label">
                      <input
                        type="checkbox"
                        checked={contentTypes.includes(ct)}
                        onChange={e => {
                          if (ct === 'tracks') return  // tracks always included
                          setContentTypes(prev =>
                            e.target.checked
                              ? [...prev, ct]
                              : prev.filter(x => x !== ct)
                          )
                        }}
                        disabled={ct === 'tracks'}
                      />
                      {ct === 'tracks' ? t('tracks', lang) : ct === 'playlists' ? t('playlists', lang) : t('artists', lang)}
                    </label>
                  ))}
                </div>
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
            {starting ? t('starting', lang) : t('start', lang)}
          </button>
        </div>
      </div>
    </div>
  )
}
