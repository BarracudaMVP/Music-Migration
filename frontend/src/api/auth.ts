import { api, setAccessToken } from './client'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface AuthStatus {
  [service: string]: boolean
}

// Exchange short-lived OAuth code (from callback URL) for JWT pair
export async function exchangeCode(code: string): Promise<TokenPair> {
  const tokens = await api.post<TokenPair>('/auth/exchange', { code })
  setAccessToken(tokens.access_token)
  // Persist refresh token in localStorage
  localStorage.setItem('refresh_token', tokens.refresh_token)
  return tokens
}

// Use stored refresh token to get a new access token
export async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem('refresh_token')
  if (!refreshToken) {
    // No token — probe /auth/me without auth.
    // In DEV_MODE the server bypasses JWT and returns dev_user, so we get a 200.
    // In production this returns 401 and we fall through to null.
    try {
      await api.get('/auth/me')
      setAccessToken('dev')
      return 'dev'
    } catch {
      return null
    }
  }

  try {
    const tokens = await api.post<TokenPair>('/auth/refresh', {
      refresh_token: refreshToken,
    })
    setAccessToken(tokens.access_token)
    localStorage.setItem('refresh_token', tokens.refresh_token)
    return tokens.access_token
  } catch {
    localStorage.removeItem('refresh_token')
    setAccessToken(null)
    return null
  }
}

export async function logout(): Promise<void> {
  try {
    await api.post('/auth/logout')
  } finally {
    localStorage.removeItem('refresh_token')
    setAccessToken(null)
  }
}

const SERVICE_AUTH_SLUG: Record<string, string> = {
  yandex_music: 'yandex',
}

export function getOAuthStartUrl(service: string, flowFrom?: string, flowTo?: string): string {
  const slug = SERVICE_AUTH_SLUG[service] ?? service
  const params = new URLSearchParams()
  if (flowFrom) params.set('flow_from', flowFrom)
  if (flowTo) params.set('flow_to', flowTo)
  const qs = params.toString()
  return `/api/v1/auth/${slug}${qs ? `?${qs}` : ''}`
}
