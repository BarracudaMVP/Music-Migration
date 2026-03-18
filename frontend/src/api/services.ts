import { api } from './client'

export interface Service {
  id: string
  name: string
  capabilities: string[]
}

export interface MatrixEntry {
  from: string
  to: string
}

export interface UserStatus {
  user_id: string
  ym_connected: boolean
  sc_connected: boolean
  spotify_connected: boolean
  lang: string
  role: string
}

export function isConnected(status: UserStatus, serviceId: string): boolean {
  if (serviceId === 'yandex_music') return status.ym_connected
  if (serviceId === 'soundcloud') return status.sc_connected
  if (serviceId === 'spotify') return status.spotify_connected
  return false
}

export function fetchServices(): Promise<Service[]> {
  return api.get<Service[]>('/services')
}

export function fetchMatrix(): Promise<MatrixEntry[]> {
  return api.get<MatrixEntry[]>('/services/matrix')
}

export function fetchUserStatus(): Promise<UserStatus> {
  return api.get<UserStatus>('/auth/me')
}
