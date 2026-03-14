import { useEffect, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { exchangeCode } from '../api/auth'

// OAuth providers redirect back here with ?code=...&flow_from=...&flow_to=...
export default function AuthCallbackPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return
    ran.current = true

    const code = params.get('code')
    if (!code) {
      navigate('/', { replace: true })
      return
    }

    exchangeCode(code)
      .then(() => {
        const flowFrom = params.get('flow_from')
        const flowTo = params.get('flow_to')
        if (flowFrom && flowTo) {
          navigate(`/migrate?from=${flowFrom}&to=${flowTo}`, { replace: true })
        } else {
          navigate('/', { replace: true })
        }
      })
      .catch(() => {
        navigate('/?auth_error=1', { replace: true })
      })
  }, [])

  return (
    <div className="page-center">
      <p>Авторизация…</p>
    </div>
  )
}
