import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { refreshAccessToken, getOAuthStartUrl, getTokenRole } from '../api/auth'
import { fetchServices, fetchMatrix, fetchUserStatus, isConnected } from '../api/services'
import type { Service, MatrixEntry, UserStatus } from '../api/services'
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

export default function HomePage() {
  const { lang } = useLang()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const ran = useRef(false)

  const [services, setServices] = useState<Service[]>([])
  const [matrix, setMatrix] = useState<MatrixEntry[]>([])
  const [userStatus, setUserStatus] = useState<UserStatus | null>(null)
  const [loading, setLoading] = useState(true)
  // Pre-populate from URL params (e.g. after OAuth redirect back: /?from=yandex_music&to=soundcloud)
  const [fromSvc, setFromSvc] = useState<string | null>(searchParams.get('from'))
  const [toSvc, setToSvc] = useState<string | null>(searchParams.get('to'))
  const [authError, setAuthError] = useState(false)

  // Migration settings
  const [limit, setLimit] = useState<number | undefined>(undefined)
  const [skipAlready, setSkipAlready] = useState(true)
  const [likeTracks, setLikeTracks] = useState(false)
  const [spotifyPlaylistMode, setSpotifyPlaylistMode] = useState(false)
  const [spotifyPlaylistName, setSpotifyPlaylistName] = useState('')
  const [contentTypes, setContentTypes] = useState<string[]>(['tracks'])
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importError, setImportError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<string | null>(null)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    setAuthError(searchParams.get('auth_error') === '1')

    async function init() {
      try {
        if (!getAccessToken()) {
          await refreshAccessToken()
        }
        const [svcs, mtx] = await Promise.all([fetchServices(), fetchMatrix()])
        setServices(svcs)
        setMatrix(mtx)
        if (getAccessToken()) {
          try {
            const status = await fetchUserStatus()
            setUserStatus(status)
          } catch {
            // not authenticated
          }
        }
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [])

  // file service is import-only and not in the capability matrix — add explicitly
  const fromServices = [
    ...Array.from(new Set(matrix.map(e => e.from)))
      .map(id => services.find(s => s.id === id))
      .filter(Boolean) as Service[],
    ...services.filter(s => s.id === 'file' && s.capabilities.includes('IMPORT_FILE')),
  ]

  // For file source: all services with WRITE_LIKED_TRACKS (file→file is forbidden)
  // For other sources: matrix entries + file (for export, FileAdapter has EXPORT_FILE)
  const toServices = fromSvc === 'file'
    ? services.filter(s => s.id !== 'file' && s.capabilities.includes('WRITE_LIKED_TRACKS'))
    : fromSvc
      ? [
          ...matrix
            .filter(e => e.from === fromSvc)
            .map(e => services.find(s => s.id === e.to))
            .filter(Boolean) as Service[],
          // File export: explicitly add (not in matrix)
          ...services.filter(s => s.id === 'file' && s.capabilities.includes('EXPORT_FILE')),
        ]
      : []

  function handleFromSelect(id: string) {
    setFromSvc(id)
    setToSvc(null)
    setImportFile(null)
    setImportError(null)
  }

  function handleToSelect(id: string) {
    setToSvc(id)
  }

  const needsAuth = (svcId: string) => svcId !== 'file'
  const isAuth = (svcId: string) => {
    if (!userStatus) return false
    return isConnected(userStatus, svcId)
  }

  const authServices = fromSvc && toSvc
    ? [fromSvc, toSvc].filter((id, idx, arr) => arr.indexOf(id) === idx && needsAuth(id))
    : []

  const allAuthed = authServices.every(id => isAuth(id))
  const canStart =
    fromSvc !== null &&
    toSvc !== null &&
    allAuthed &&
    !starting &&
    (fromSvc !== 'file' || importFile !== null)

  async function handleStart() {
    if (!canStart) return
    setStarting(true)
    setStartError(null)
    setImportError(null)

    let tracksOverride: TrackImport[] | undefined
    if (fromSvc === 'file') {
      if (!importFile) {
        setStartError(t('error_no_file', lang))
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
        from_service: fromSvc!,
        to_service: toSvc!,
        content_types: fromSvc === 'file' ? ['tracks'] : contentTypes,
        limit: limit,
        skip_already_migrated: fromSvc !== 'file' ? skipAlready : undefined,
        like_tracks: toSvc === 'soundcloud' ? likeTracks : undefined,
        spotify_playlist_mode: toSvc === 'spotify' ? spotifyPlaylistMode : undefined,
        spotify_playlist_name:
          toSvc === 'spotify' && spotifyPlaylistMode && spotifyPlaylistName
            ? spotifyPlaylistName
            : undefined,
        tracks_override: tracksOverride,
      })
      navigate(`/migrate/${result.migration_id}/progress`)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('error_unknown', lang)
      setStartError(msg)
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
        {/* Header */}
        <div className="page-header">
          <h1 className="title">Music Migration</h1>
          <p className="subtitle">{t('app_subtitle', lang)}</p>
          {userStatus && (
            <Link to="/history" className="history-link">{t('history_link', lang)}</Link>
          )}
        </div>

        {authError && (
          <div className="alert alert-error">
            {t('auth_error', lang)}
          </div>
        )}

        {/* FROM selection */}
        <div className="section">
          <div className="section-label">{t('from', lang)}</div>
          <div className="service-grid">
            {fromServices.map(svc => (
              <button
                key={svc.id}
                className={`service-card${fromSvc === svc.id ? ' selected' : ''}`}
                onClick={() => handleFromSelect(svc.id)}
              >
                <span className="service-icon">{SERVICE_ICONS[svc.id] ?? '🎶'}</span>
                <span className="service-name">{tService(svc.id, lang)}</span>
                {needsAuth(svc.id) && userStatus && isAuth(svc.id) && (
                  <span className="auth-ok" style={{ fontSize: 11, marginTop: 2 }}>{t('connected', lang)}</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* TO selection */}
        {fromSvc && (
          <div className="section">
            <div className="section-label">{t('to', lang)}</div>
            <div className="service-grid">
              {toServices.map(svc => (
                <button
                  key={svc.id}
                  className={`service-card${toSvc === svc.id ? ' selected' : ''}`}
                  onClick={() => handleToSelect(svc.id)}
                >
                  <span className="service-icon">{SERVICE_ICONS[svc.id] ?? '🎶'}</span>
                  <span className="service-name">{tService(svc.id, lang)}</span>
                  {needsAuth(svc.id) && userStatus && isAuth(svc.id) && (
                    <span className="auth-ok" style={{ fontSize: 11, marginTop: 2 }}>{t('connected', lang)}</span>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Auth section */}
        {fromSvc && toSvc && authServices.length > 0 && (
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
                        window.location.href = getOAuthStartUrl(svcId, fromSvc!, toSvc!)
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

        {/* Settings — shown once FROM and TO are selected */}
        {fromSvc && toSvc && (
          <div className="section">
            <div className="section-label">{t('settings', lang)}</div>

            {(startError || importError) && (
              <div className="alert alert-error" style={{ marginBottom: 12 }}>
                {startError || importError}
              </div>
            )}

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
                  <option value="5">5</option>
                  <option value="50">50</option>
                  <option value="500">500</option>
                  <option value="">{t('all', lang)}</option>
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

            {/* Start button */}
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
        )}

        {/* Admin link */}
        {getTokenRole() === 'admin' && (
          <div style={{ paddingTop: 8 }}>
            <Link to="/dashboard" className="muted" style={{ fontSize: 13 }}>
              {t('admin_link', lang)}
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
