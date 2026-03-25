import { useEffect, useState } from 'react'
import { listUsers } from '../../api/admin'
import type { AdminUsersPage as UsersPageType, AdminUser } from '../../api/admin'

export default function AdminUsersPage() {
  const [data, setData] = useState<UsersPageType | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    listUsers(page)
      .then(d => { setData(d); setError(null) })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Ошибка'))
      .finally(() => setLoading(false))
  }, [page])

  return (
    <div className="admin-page">
      <h1 className="title" style={{ marginBottom: 20 }}>Users</h1>

      {error && <div className="alert alert-error">{error}</div>}
      {loading && <p className="muted">Загрузка…</p>}

      {!loading && data && (
        <>
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>User ID</th>
                  <th>Роль</th>
                  <th>Миграций</th>
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
                  <tr><td colSpan={3} className="muted" style={{ textAlign: 'center', padding: 24 }}>Нет пользователей</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {data.pages > 1 && (
            <div className="admin-pagination">
              <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                ← Назад
              </button>
              <span className="muted" style={{ fontSize: 13 }}>{page} / {data.pages}</span>
              <button className="btn btn-ghost btn-sm" disabled={page >= data.pages} onClick={() => setPage(p => p + 1)}>
                Вперёд →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
