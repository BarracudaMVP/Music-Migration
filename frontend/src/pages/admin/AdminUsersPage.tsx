import { useEffect, useState } from 'react'
import { listUsers } from '../../api/admin'
import type { AdminUsersPage as UsersPageType, AdminUser } from '../../api/admin'
import { useLang } from '../../App'
import { t } from '../../i18n'

export default function AdminUsersPage() {
  const { lang } = useLang()
  const [data, setData] = useState<UsersPageType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    listUsers(page)
      .then(d => { setData(d); setError(null) })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : t('load_error', lang)))
      .finally(() => setLoading(false))
  }, [page])

  return (
    <div className="admin-page">
      <h1 className="title" style={{ marginBottom: 20 }}>{t('nav_users', lang)}</h1>

      {error && <div className="alert alert-error">{error}</div>}
      {loading && <p className="muted">{t('loading', lang)}</p>}

      {!loading && data && (
        <>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>User ID</th>
                  <th>{t('col_role', lang)}</th>
                  <th>{t('migrations_count', lang)}</th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((u: AdminUser) => (
                  <tr key={u.user_id}>
                    <td style={{ fontFamily: 'monospace', fontSize: 13 }}>{u.user_id}</td>
                    <td>
                      {u.role === 'admin' ? (
                        <span className="status-badge status-running">admin</span>
                      ) : (
                        <span className="muted">user</span>
                      )}
                    </td>
                    <td>{u.migration_count}</td>
                  </tr>
                ))}
                {data.users.length === 0 && (
                  <tr><td colSpan={3} className="muted" style={{ textAlign: 'center', padding: 24 }}>{t('no_users', lang)}</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {data.pages > 1 && (
            <div className="admin-pagination">
              <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                {t('prev', lang)}
              </button>
              <span className="muted" style={{ fontSize: 13 }}>{page} / {data.pages}</span>
              <button className="btn btn-ghost btn-sm" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)}>
                {t('next_page', lang)}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
