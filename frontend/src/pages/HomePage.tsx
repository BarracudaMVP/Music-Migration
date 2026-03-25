import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { refreshAccessToken, getOAuthStartUrl } from '../api/auth'
import { fetchServices, fetchMatrix, fetchUserStatus, isConnected } from '../api/services'
import type { Service, MatrixEntry, UserStatus } from '../api/services'
import { getAccessToken } from '../api/client'

const SERVICE_LABELS: Record<string, string> = {
  yandex_music: 'Яндекс Музыка',
  spotify: 'Spotify',
  soundcloud: 'SoundCloud',
  file: 'Файл (CSV/JSON)',
}

const SERVICE_ICONS: Record<string, string> = {
  yandex_music: '🎵',
  spotify: '🎧',
  soundcloud: '☁️',
  file: '📄',
}

export default function HomePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const ran = useRef(false)

  const [services, setServices] = useState<Service[]>([])
  const [matrix, setMatrix] = useState<MatrixEntry[]>([])
  const [userStatus, setUserStatus] = useState<UserStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [fromSvc, setFromSvc] = useState<string | null>(null)
  const [toSvc, setToSvc] = useState<string | null>(null)
  const [authError, setAuthError] = useState(false)

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

  const fromServices = Array.from(new Set(matrix.map(e => e.from)))
    .map(id => services.find(s => s.id === id))
    .filter(Boolean) as Service[]

  const toServices = fromSvc
    ? matrix
        .filter(e => e.from === fromSvc)
        .map(e => services.find(s => s.id === e.to))
        .filter(Boolean) as Service[]
    : []

  function handleFromSelect(id: string) {
    setFromSvc(id)
    setToSvc(null)
  }

  function handleToSelect(id: string) {
    setToSvc(id)
  }

  const needsAuth = (svcId: string) => svcId !== 'file'
  const isAuth = (svcId: string) => {
    if (!userStatus) return false
    return isConnected(userStatus, svcId)
  }
  const canProceed =
    fromSvc !== null &&
    toSvc !== null &&
    (!needsAuth(fromSvc) || isAuth(fromSvc)) &&
    (!needsAuth(toSvc) || isAuth(toSvc))

  const authServices = fromSvc && toSvc
    ? [fromSvc, toSvc].filter((id, idx, arr) => arr.indexOf(id) === idx && needsAuth(id))
    : []

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
          <h1 className="title">Music Migration</h1>
          <p className="subtitle">Перенос музыкальной библиотеки между платформами</p>
          {userStatus && (
            <Link to="/history" className="history-link">История миграций →</Link>
          )}
        </div>

        {authError && (
          <div className="alert alert-error">
            Ошибка авторизации. Попробуйте снова.
          </div>
        )}

        {/* FROM selection */}
        <div className="section">
          <div className="section-label">Откуда</div>
          <div className="service-grid">
            {fromServices.map(svc => (
              <button
                key={svc.id}
                className={`service-card${fromSvc === svc.id ? ' selected' : ''}`}
                onClick={() => handleFromSelect(svc.id)}
              >
                <span className="service-icon">{SERVICE_ICONS[svc.id] ?? '🎶'}</span>
                <span className="service-name">{SERVICE_LABELS[svc.id] ?? svc.name}</span>
              </button>
            ))}
          </div>
        </div>

        {/* TO selection */}
        {fromSvc && (
          <div className="section">
            <div className="section-label">Куда</div>
            <div className="service-grid">
              {toServices.map(svc => (
                <button
                  key={svc.id}
                  className={`service-card${toSvc === svc.id ? ' selected' : ''}`}
                  onClick={() => handleToSelect(svc.id)}
                >
                  <span className="service-icon">{SERVICE_ICONS[svc.id] ?? '🎶'}</span>
                  <span className="service-name">{SERVICE_LABELS[svc.id] ?? svc.name}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Auth section */}
        {fromSvc && toSvc && authServices.length > 0 && (
          <div className="section">
            <div className="section-label">Авторизация</div>
            <div className="auth-list">
              {authServices.map(svcId => (
                <div key={svcId} className="auth-row">
                  <span>
                    {SERVICE_ICONS[svcId]} {SERVICE_LABELS[svcId] ?? svcId}
                  </span>
                  {isAuth(svcId) ? (
                    <span className="auth-ok">✓ Подключено</span>
                  ) : (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        window.location.href = getOAuthStartUrl(svcId, fromSvc!, toSvc!)
                      }}
                    >
                      Войти
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        {fromSvc && toSvc && (
          <div className="actions">
            <button
              className="btn btn-primary"
              disabled={!canProceed}
              onClick={() => navigate(`/migrate?from=${fromSvc}&to=${toSvc}`)}
            >
              Далее →
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
