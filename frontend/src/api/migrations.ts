import { api } from './client'

export interface StartMigrationRequest {
  from_service: string
  to_service: string
  content_types?: string[]
  limit?: number
  skip_already_migrated?: boolean
  like_tracks?: boolean
  spotify_playlist_mode?: boolean
  spotify_playlist_name?: string
}

export interface TrackStats {
  pending?: number
  liked?: number
  not_found?: number
  error?: number
  in_playlist?: number
}

export interface Migration {
  id: number
  from_service: string
  to_service: string
  status: string
  created_at: string | null
  result_path?: string | null
  stats?: TrackStats
}

export interface MigrationDetail {
  migration: Migration
  stats: TrackStats
  current_track: string | null
}

export interface TracksPage {
  tracks: TrackRow[]
  total: number
  page: number
  pages: number
}

export interface TrackRow {
  id: number
  ym_artist: string
  ym_title: string
  status: string
  match_score: number | null
  sc_url: string | null
}

export function startMigration(req: StartMigrationRequest): Promise<{ migration_id: number }> {
  return api.post<{ migration_id: number }>('/migrations', req)
}

export function getMigration(id: number): Promise<MigrationDetail> {
  return api.get<MigrationDetail>(`/migrations/${id}`)
}

export function listMigrations(): Promise<Migration[]> {
  return api.get<Migration[]>('/migrations')
}

export function getMigrationTracks(id: number, status?: string, page = 1): Promise<TracksPage> {
  const q = new URLSearchParams({ page: String(page) })
  if (status) q.set('status', status)
  return api.get<TracksPage>(`/migrations/${id}/tracks?${q}`)
}
