import { useEffect, useRef, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { refreshAccessToken } from '../api/auth'
import { listMigrations } from '../api/migrations'
import type { Migration } from '../api/migrations'
import { getAccessToken } from '../api/client'
import { useLang } from '../App'
import { t, tService, tStatus, formatDate } from '../i18n'

function statusClass(status: string): string {
  switch (status) {
    case 'running': return 'status-running'
    case 'pending': return 'status-pending'
    case 'done': return 'status-done'
    case 'failed': return 'status-failed'
    case 'cancelled': return 'status-cancelled'
    default: return ''
  }
}

export default function HistoryPage() {
  const { lang } = useLang()
  const navigate = useNavigate()
  const ran = useRef(false)

  const [migrations, setMigrations] = useState<Migration[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    async function init() {
      try {
        if (!getAccessToken()) {
          const token = await refreshAccessToken()
          if (!token) {
            navigate('/', { replace: true })
            return
          }
        }
        const data = await listMigrations()
        setMigrations(data.migrations)
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : t('load_error', lang)
        setError(msg)
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [])

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
          <h1 className="title">{t('history_title', lang)}</h1>
          <Link to="/" className="btn btn-primary btn-sm">{t('new_migration_btn', lang)}</Link>
        </div>

        {error && (
          <div className="alert alert-error">{error}</div>
        )}

        {!error && migrations.length === 0 && (
          <div className="empty-state">
            <p className="muted">{t('no_migrations', lang)}</p>
            <Link to="/" className="btn btn-primary" style={{ marginTop: 16 }}>
              {t('start_first', lang)}
            </Link>
          </div>
        )}

        {migrations.length > 0 && (
          <div className="migration-list">
            {migrations.map(m => {
              const liked = m.stats?.liked ?? 0
              const inPlaylist = m.stats?.in_playlist ?? 0
              const notFound = m.stats?.not_found ?? 0
              const success = liked + inPlaylist

              return (
                <Link
                  key={m.id}
                  to={`/migrate/${m.id}/progress`}
                  className="migration-row"
                >
                  <div className="migration-direction">
                    <span>{tService(m.from_service, lang)}</span>
                    <span className="muted"> → </span>
                    <span>{tService(m.to_service, lang)}</span>
                  </div>

                  <div className="migration-meta">
                    <span className={`status-badge ${statusClass(m.status)}`}>
                      {tStatus(m.status, lang)}
                    </span>
                    <span className="muted migration-date">{formatDate(m.created_at, lang)}</span>
                  </div>

                  {m.status === 'done' && (
                    <div className="migration-stats">
                      <span className="stat-ok">✓ {success}</span>
                      {notFound > 0 && <span className="stat-miss"> · ✗ {notFound}</span>}
                      {m.result_path && (
                        <a
                          href={m.result_path}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="playlist-link"
                          onClick={e => e.stopPropagation()}
                        >
                          {t('playlist_link', lang)}
                        </a>
                      )}
                    </div>
                  )}
                </Link>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
