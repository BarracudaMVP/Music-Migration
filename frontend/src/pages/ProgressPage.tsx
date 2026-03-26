import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { refreshAccessToken } from '../api/auth'
import { getMigration } from '../api/migrations'
import type { MigrationDetail } from '../api/migrations'
import { getAccessToken } from '../api/client'
import { useLang } from '../App'
import { t, tService, tStatus } from '../i18n'

const TERMINAL_STATUSES = new Set(['done', 'failed', 'cancelled'])

export default function ProgressPage() {
  const { lang } = useLang()
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const ran = useRef(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [detail, setDetail] = useState<MigrationDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  function stopPolling() {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }

  async function poll() {
    if (!id) return
    try {
      const data = await getMigration(Number(id))
      setDetail(data)
      setLoading(false)
      if (TERMINAL_STATUSES.has(data.migration.status)) {
        stopPolling()
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('load_error', lang)
      setError(msg)
      setLoading(false)
      stopPolling()
    }
  }

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    if (!id) {
      navigate('/', { replace: true })
      return
    }

    async function init() {
      if (!getAccessToken()) {
        await refreshAccessToken()
      }
      if (!getAccessToken()) {
        navigate('/', { replace: true })
        return
      }
      await poll()
      intervalRef.current = setInterval(poll, 2000)
    }

    init()

    return () => stopPolling()
  }, [])

  if (loading) {
    return (
      <div className="page-center">
        <p className="muted">{t('loading', lang)}</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-center">
        <div className="alert alert-error">{error}</div>
        <Link to="/" className="btn btn-ghost">{t('to_home', lang)}</Link>
      </div>
    )
  }

  if (!detail) return null

  const { migration, stats, current_track } = detail
  const s = stats ?? {}
  const liked = s.liked ?? 0
  const inPlaylist = s.in_playlist ?? 0
  const notFound = s.not_found ?? 0
  const errorCount = s.error ?? 0
  const pending = s.pending ?? 0

  const doneCount = liked + inPlaylist + notFound + errorCount
  const total = doneCount + pending
  const pct = total > 0 ? Math.round((doneCount / total) * 100) : 0
  const isTerminal = TERMINAL_STATUSES.has(migration.status)
  const success = liked + inPlaylist

  return (
    <div className="page">
      <div className="container">
        {/* Header */}
        <div className="page-header">
          <h1 className="title">
            {tService(migration.from_service, lang)}
            {' → '}
            {tService(migration.to_service, lang)}
          </h1>
          <span className={`status-badge status-${migration.status}`}>
            {tStatus(migration.status, lang)}
          </span>
        </div>

        {/* Progress bar */}
        <div className="section">
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="muted" style={{ marginTop: 6 }}>
            {doneCount} / {total} {t('tracks_count', lang)} ({pct}%)
          </p>
        </div>

        {/* Current track */}
        {current_track && !isTerminal && (
          <div className="section">
            <div className="section-label">{t('now', lang)}</div>
            <p className="current-track">{current_track}</p>
          </div>
        )}

        {/* Stats */}
        <div className="section">
          <div className="section-label">{t('stats', lang)}</div>
          <div className="stat-rows">
            <div className="stat-row stat-success">
              <span>{t('stat_found', lang)}</span>
              <span>{success}</span>
            </div>
            <div className="stat-row stat-muted">
              <span>{t('stat_not_found', lang)}</span>
              <span>{notFound}</span>
            </div>
            {errorCount > 0 && (
              <div className="stat-row stat-error">
                <span>{t('stat_errors', lang)}</span>
                <span>{errorCount}</span>
              </div>
            )}
            {pending > 0 && (
              <div className="stat-row stat-muted">
                <span>{t('stat_pending', lang)}</span>
                <span>{pending}</span>
              </div>
            )}
          </div>
        </div>

        {/* Terminal actions */}
        {isTerminal && (
          <div className="section">
            {migration.status === 'failed' && (
              <div className="alert alert-error" style={{ marginBottom: 16 }}>
                {t('migration_failed', lang)}
              </div>
            )}
            {migration.result_path && (
              <div style={{ marginBottom: 16 }}>
                <a
                  href={migration.result_path}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-primary"
                >
                  {t('open_playlist', lang)}
                </a>
              </div>
            )}
            {migration.to_service === 'file' && migration.status === 'done' && (
              <div style={{ marginBottom: 16, display: 'flex', gap: 8 }}>
                <a
                  href={`/api/v1/migrations/${migration.id}/export?fmt=csv`}
                  download={`migration-${migration.id}.csv`}
                  className="btn btn-ghost"
                >
                  CSV ↓
                </a>
                <a
                  href={`/api/v1/migrations/${migration.id}/export?fmt=json`}
                  download={`migration-${migration.id}.json`}
                  className="btn btn-ghost"
                >
                  JSON ↓
                </a>
              </div>
            )}
            <div className="actions">
              <Link to="/" className="btn btn-primary">{t('new_migration', lang)}</Link>
              <Link to="/history" className="btn btn-ghost">{t('history', lang)}</Link>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

