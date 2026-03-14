import { api } from './client'

export interface MigrationRequest {
  from_service: string
  to_service: string
  content_types: string[]
  limit?: number
}

export interface Migration {
  id: string
  from_service: string
  to_service: string
  status: string
  created_at: string
  total_tracks?: number
  liked_tracks?: number
  not_found_tracks?: number
}

export interface MigrationStatus {
  id: string
  status: string
  total: number
  liked: number
  not_found: number
  error: number
  pending: number
}

export function startMigration(req: MigrationRequest): Promise<{ id: string }> {
  return api.post<{ id: string }>('/migrations', req)
}

export function getMigrationStatus(id: string): Promise<MigrationStatus> {
  return api.get<MigrationStatus>(`/migrations/${id}`)
}

export function getMigrations(): Promise<{ migrations: Migration[] }> {
  return api.get<{ migrations: Migration[] }>('/migrations')
}
