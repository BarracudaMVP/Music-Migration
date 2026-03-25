import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, Link } from 'react-router-dom'
import { refreshAccessToken } from '../api/auth'
import { getMigration } from '../api/migrations'
import type { MigrationDetail } from '../api/migrations'
import { getAccessToken } from '../api/client'

const SERVICE_LABELS: Record<string, string> = {
  yandex_music: 'Яндекс Музыка',
  spotify: 'Spotify',
  soundcloud: 'SoundCloud',
  file: 'Файл (CSV/JSON)',
}

const TERMINAL_STATUSES = new Set(['done', 'failed', 'cancelled'])

export default function ProgressPage() {
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
      const msg = e instanceof Error ? e.message : 'Ошибка загрузки'
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
        <p className="muted">Загрузка…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page-center">
        <div className="alert alert-error">{error}</div>
        <Link to="/" className="btn btn-ghost">На главную</Link>
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
            {SERVICE_LABELS[migration.from_service] ?? migration.from_service}
            {' → '}
            {SERVICE_LABELS[migration.to_service] ?? migration.to_service}
          </h1>
          <span className={`status-badge status-${migration.status}`}>
            {statusLabel(migration.status)}
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
            {doneCount} / {total} треков ({pct}%)
          </p>
        </div>

        {/* Current track */}
        {current_track && !isTerminal && (
          <div className="section">
            <div className="section-label">Сейчас</div>
            <p className="current-track">{current_track}</p>
          </div>
        )}

        {/* Stats */}
        <div className="section">
          <div className="section-label">Статистика</div>
          <div className="stat-rows">
            <div className="stat-row stat-success">
              <span>✓ Найдено и добавлено</span>
              <span>{success}</span>
            </div>
            <div className="stat-row stat-muted">
              <span>✗ Не найдено</span>
              <span>{notFound}</span>
            </div>
            {errorCount > 0 && (
              <div className="stat-row stat-error">
                <span>⚠ Ошибок</span>
                <span>{errorCount}</span>
              </div>
            )}
            {pending > 0 && (
              <div className="stat-row stat-muted">
                <span>⏳ Ожидает</span>
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
                Миграция завершилась с ошибкой.
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
                  Открыть плейлист ↗
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
              <Link to="/" className="btn btn-primary">Новая миграция</Link>
              <Link to="/history" className="btn btn-ghost">История</Link>
            </div>
          </div>
        )}
      </div>
    </div>
  )
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
