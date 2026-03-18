import { useEffect, useRef, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { refreshAccessToken } from '../api/auth'
import { listMigrations } from '../api/migrations'
import type { Migration } from '../api/migrations'
import { getAccessToken } from '../api/client'

const SERVICE_LABELS: Record<string, string> = {
  yandex_music: 'Яндекс Музыка',
  spotify: 'Spotify',
  soundcloud: 'SoundCloud',
  file: 'Файл (CSV/JSON)',
}

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

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

function statusLabel(status: string): string {
  switch (status) {
    case 'running': return 'В процессе'
    case 'pending': return 'В очереди'
    case 'done': return 'Завершено'
    case 'failed': return 'Ошибка'
    case 'cancelled': return 'Отменено'
    default: return status
  }
}

export default function HistoryPage() {
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
        setMigrations(data)
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : 'Ошибка загрузки'
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
        <p className="muted">Загрузка…</p>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="container">
        {/* Header */}
        <div className="page-header">
          <h1 className="title">История миграций</h1>
          <Link to="/" className="btn btn-primary btn-sm">+ Новая миграция</Link>
        </div>

        {error && (
          <div className="alert alert-error">{error}</div>
        )}

        {!error && migrations.length === 0 && (
          <div className="empty-state">
            <p className="muted">Миграций ещё нет.</p>
            <Link to="/" className="btn btn-primary" style={{ marginTop: 16 }}>
              Начать первую миграцию
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
                    <span>{SERVICE_LABELS[m.from_service] ?? m.from_service}</span>
                    <span className="muted"> → </span>
                    <span>{SERVICE_LABELS[m.to_service] ?? m.to_service}</span>
                  </div>

                  <div className="migration-meta">
                    <span className={`status-badge ${statusClass(m.status)}`}>
                      {statusLabel(m.status)}
                    </span>
                    <span className="muted migration-date">{formatDate(m.created_at)}</span>
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
                          Плейлист ↗
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
