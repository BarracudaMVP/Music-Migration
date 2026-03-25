import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { listMigrations } from '../../api/migrations'
import type { Migration, MigrationsPage } from '../../api/migrations'

const SERVICE_LABELS: Record<string, string> = {
  yandex_music: 'Яндекс Музыка',
  spotify: 'Spotify',
  soundcloud: 'SoundCloud',
  file: 'Файл',
}

const STATUS_LABELS: Record<string, string> = {
  pending: 'В очереди',
  running: 'В процессе',
  done: 'Завершено',
  failed: 'Ошибка',
  cancelled: 'Отменено',
}

export default function AdminMigrationsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [data, setData] = useState<MigrationsPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const filterUser = searchParams.get('user_id') ?? ''
  const filterStatus = searchParams.get('status') ?? ''
  const page = parseInt(searchParams.get('page') ?? '1', 10)

  useEffect(() => {
    setLoading(true)
    listMigrations({ user_id: filterUser || undefined, status: filterStatus || undefined, page })
      .then(d => { setData(d); setError(null) })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Ошибка'))
      .finally(() => setLoading(false))
  }, [filterUser, filterStatus, page])

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete('page')
    setSearchParams(next)
  }

  function setPage(p: number) {
    const next = new URLSearchParams(searchParams)
    next.set('page', String(p))
    setSearchParams(next)
  }

  return (
    <div className="admin-page">
      <h1 className="title" style={{ marginBottom: 20 }}>Migrations</h1>

      {/* Filters */}
      <div className="admin-filters">
        <input
          className="setting-input"
          placeholder="user_id"
          value={filterUser}
          onChange={e => setParam('user_id', e.target.value)}
          style={{ minWidth: 200 }}
        />
        <select
          className="setting-select"
          value={filterStatus}
          onChange={e => setParam('status', e.target.value)}
        >
          <option value="">Все статусы</option>
          {Object.entries(STATUS_LABELS).map(([v, l]) => (
            <option key={v} value={v}>{l}</option>
          ))}
        </select>
      </div>

      {error && <div className="alert alert-error" style={{ marginTop: 12 }}>{error}</div>}
      {loading && <p className="muted" style={{ marginTop: 12 }}>Загрузка…</p>}

      {!loading && data && (
        <>
          <div className="admin-table-wrap" style={{ marginTop: 16 }}>
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
                {data.migrations.map((m: Migration) => (
                  <tr key={m.id}>
                    <td>#{m.id}</td>
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
                {data.migrations.length === 0 && (
                  <tr><td colSpan={5} className="muted" style={{ textAlign: 'center', padding: 24 }}>Нет миграций</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {data.pages > 1 && (
            <div className="admin-pagination">
              <button
                className="btn btn-ghost btn-sm"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                ← Назад
              </button>
              <span className="muted" style={{ fontSize: 13 }}>
                {page} / {data.pages}
              </span>
              <button
                className="btn btn-ghost btn-sm"
                disabled={page >= data.pages}
                onClick={() => setPage(page + 1)}
              >
                Вперёд →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
