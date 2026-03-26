import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchStats } from '../../api/admin'
import type { AdminStats } from '../../api/admin'
import { useLang } from '../../App'
import { t, tService, tStatus, formatDate } from '../../i18n'

export default function AdminDashboardPage() {
  const { lang } = useLang()
  const ran = useRef(false)
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (ran.current) return
    ran.current = true
    fetchStats().then(setStats).catch((e: unknown) => {
      setError(e instanceof Error ? e.message : t('load_error', lang))
    })
  }, [])

  if (!stats && !error) {
    return <div className="page-center"><p className="muted">{t('loading', lang)}</p></div>
  }

  if (error) {
    return <div className="page-center"><div className="alert alert-error">{error}</div></div>
  }

  return (
    <div className="admin-page">
      <h1 className="title" style={{ marginBottom: 24 }}>{t('dashboard', lang)}</h1>

      {/* Summary cards */}
      <div className="admin-cards">
        <div className="admin-card">
          <div className="admin-card-value">{stats!.total_migrations}</div>
          <div className="admin-card-label">{t('migrations_count', lang)}</div>
        </div>
        <div className="admin-card">
          <div className="admin-card-value">{stats!.total_users}</div>
          <div className="admin-card-label">{t('users_count', lang)}</div>
        </div>
      </div>

      {/* By status */}
      <div className="section" style={{ marginTop: 28 }}>
        <div className="section-label">{t('by_status', lang)}</div>
        <div className="stat-rows">
          {Object.entries(stats!.by_status).map(([status, count]) => (
            <div key={status} className="stat-row">
              <span className={`status-badge status-${status}`}>{tStatus(status, lang)}</span>
              <span>{count}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Recent migrations */}
      {stats!.recent.length > 0 && (
        <div className="section" style={{ marginTop: 28 }}>
          <div className="section-label">{t('recent_migrations', lang)}</div>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>User</th>
                  <th>{t('from_to', lang)}</th>
                  <th>{t('col_status', lang)}</th>
                  <th>{t('col_date', lang)}</th>
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
                      {tService(m.from_service, lang)}
                      {' → '}
                      {tService(m.to_service, lang)}
                    </td>
                    <td>
                      <span className={`status-badge status-${m.status}`}>
                        {tStatus(m.status, lang)}
                      </span>
                    </td>
                    <td className="muted" style={{ fontSize: 12 }}>
                      {formatDate(m.created_at, lang)}
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
