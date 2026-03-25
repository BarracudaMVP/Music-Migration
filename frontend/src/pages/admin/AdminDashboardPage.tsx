import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchStats } from '../../api/admin'
import type { AdminStats } from '../../api/admin'

const STATUS_LABELS: Record<string, string> = {
  pending: 'В очереди',
  running: 'В процессе',
  done: 'Завершено',
  failed: 'Ошибка',
  cancelled: 'Отменено',
}

const SERVICE_LABELS: Record<string, string> = {
  yandex_music: 'Яндекс Музыка',
  spotify: 'Spotify',
  soundcloud: 'SoundCloud',
  file: 'Файл',
}

export default function AdminDashboardPage() {
  const ran = useRef(false)
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (ran.current) return
    ran.current = true
    fetchStats().then(setStats).catch((e: unknown) => {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки')
    })
  }, [])

  if (!stats && !error) {
    return <div className="page-center"><p className="muted">Загрузка…</p></div>
  }

  if (error) {
    return <div className="page-center"><div className="alert alert-error">{error}</div></div>
  }

  return (
    <div className="admin-page">
      <h1 className="title" style={{ marginBottom: 24 }}>Dashboard</h1>

      {/* Summary cards */}
      <div className="admin-cards">
        <div className="admin-card">
          <div className="admin-card-value">{stats!.total_migrations}</div>
          <div className="admin-card-label">Миграций</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-value">{stats!.total_users}</div>
          <div className="admin-card-label">Пользователей</div>
        </div>
      </div>

      {/* By status */}
      <div className="section" style={{ marginTop: 28 }}>
        <div className="section-label">По статусам</div>
        <div className="stat-rows">
          {Object.entries(stats!.by_status).map(([status, count]) => (
            <div key={status} className="stat-row">
              <span className={`status-badge status-${status}`}>{STATUS_LABELS[status] ?? status}</span>
              <span>{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Recent migrations */}
      {stats!.recent.length > 0 && (
        <div className="section" style={{ marginTop: 28 }}>
          <div className="section-label">Последние миграции</div>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>User</th>
                  <th>Откуда → Куда</th>
                  <th>Статус</th>
                  <th>Дата</th>
                </tr>
              </thead>
              <tbody>
                {stats!.recent.map(m => (
                  <tr key={m.id}>
                    <td>
                      <Link to={`/migrations?user_id=${m.user_id}`} className="admin-link">
                        #{m.id}
                      </Link>
                    </td>
                    <td className="muted" style={{ fontSize: 12 }}>{m.user_id}</td>
                    <td>
                      {SERVICE_LABELS[m.from_service] ?? m.from_service}
                      {' → '}
                      {SERVICE_LABELS[m.to_service] ?? m.to_service}
                    </td>
                    <td>
                      <span className={`status-badge status-${m.status}`}>
                        {STATUS_LABELS[m.status] ?? m.status}
                      </span>
                    </td>
                    <td className="muted" style={{ fontSize: 12 }}>
                      {m.created_at ? new Date(m.created_at).toLocaleString('ru-RU') : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
