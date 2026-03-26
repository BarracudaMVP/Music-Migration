import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { refreshAccessToken, getOAuthStartUrl, getTokenRole } from '../api/auth'
import { fetchServices, fetchMatrix, fetchUserStatus, isConnected } from '../api/services'
import type { Service, MatrixEntry, UserStatus } from '../api/services'
import { getAccessToken } from '../api/client'
import { useLang } from '../App'
import { t, tService } from '../i18n'

const SERVICE_ICONS: Record<string, string> = {
  yandex_music: '🎵',
  spotify: '🎧',
  soundcloud: '☁️',
  file: '📄',
}

export default function HomePage() {
  const { lang } = useLang()
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
        <p className="muted">{t('loading', lang)}</p>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="container">
        {/* Header */}
        <div className="page-header">
          <h1 className="title">Music Migration</h1>
          <p className="subtitle">{t('app_subtitle', lang)}</p>
          {userStatus && (
            <Link to="/history" className="history-link">{t('history_link', lang)}</Link>
          )}
        </div>

        {authError && (
          <div className="alert alert-error">
            {t('auth_error', lang)}
          </div>
        )}

        {/* FROM selection */}
        <div className="section">
          <div className="section-label">{t('from', lang)}</div>
          <div className="service-grid">
            {fromServices.map(svc => (
              <button
                key={svc.id}
                className={`service-card${fromSvc === svc.id ? ' selected' : ''}`}
                onClick={() => handleFromSelect(svc.id)}
              >
                <span className="service-icon">{SERVICE_ICONS[svc.id] ?? '🎶'}</span>
                <span className="service-name">{tService(svc.id, lang)}</span>
              </button>
            ))}
          </div>
        </div>

        {/* TO selection */}
        {fromSvc && (
          <div className="section">
            <div className="section-label">{t('to', lang)}</div>
            <div className="service-grid">
              {toServices.map(svc => (
                <button
                  key={svc.id}
                  className={`service-card${toSvc === svc.id ? ' selected' : ''}`}
                  onClick={() => handleToSelect(svc.id)}
                >
                  <span className="service-icon">{SERVICE_ICONS[svc.id] ?? '🎶'}</span>
                  <span className="service-name">{tService(svc.id, lang)}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Auth section */}
        {fromSvc && toSvc && authServices.length > 0 && (
          <div className="section">
            <div className="section-label">{t('auth', lang)}</div>
            <div className="auth-list">
              {authServices.map(svcId => (
                <div key={svcId} className="auth-row">
                  <span>
                    {SERVICE_ICONS[svcId]} {tService(svcId, lang)}
                  </span>
                  {isAuth(svcId) ? (
                    <span className="auth-ok">{t('connected', lang)}</span>
                  ) : (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        window.location.href = getOAuthStartUrl(svcId, fromSvc!, toSvc!)
                      }}
                    >
                      {t('connect', lang)}
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
              {t('next', lang)}
            </button>
          </div>
        )}

        {/* Admin link */}
        {getTokenRole() === 'admin' && (
          <div style={{ paddingTop: 8 }}>
            <Link to="/dashboard" className="muted" style={{ fontSize: 13 }}>
              {t('admin_link', lang)}
            </Link>
          </div>
        )}
      </div>
    </div>
  )
}
