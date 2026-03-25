import { api } from './client'

export interface AdminStats {
  total_migrations: number
  total_users: number
  by_status: Record<string, number>
  recent: AdminMigrationRow[]
}

export interface AdminMigrationRow {
  id: number
  user_id: string
  from_service: string
  to_service: string
  status: string
  created_at: string | null
  result_path?: string | null
}

export interface AdminUsersPage {
  users: AdminUser[]
  total: number
  page: number
  pages: number
}

export interface AdminUser {
  user_id: string
  role: string
  migration_count: number
}

export function fetchStats(): Promise<AdminStats> {
  return api.get<AdminStats>('/stats')
}

export function listUsers(page = 1): Promise<AdminUsersPage> {
  return api.get<AdminUsersPage>(`/users?page=${page}`)
}
