import { api } from './client'

export interface TrackImport {
  artist: string
  title: string
}

export interface StartMigrationRequest {
  from_service: string
  to_service: string
  content_types?: string[]
  limit?: number
  skip_already_migrated?: boolean
  like_tracks?: boolean
  spotify_playlist_mode?: boolean
  spotify_playlist_name?: string
  tracks_override?: TrackImport[]
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

export async function parseImportFile(file: File): Promise<TrackImport[]> {
  const text = await file.text()

  if (file.name.toLowerCase().endsWith('.json')) {
    const data = JSON.parse(text) as TrackImport[]
    return data.filter(t => t && typeof t.artist === 'string' && typeof t.title === 'string')
  }

  // CSV: first line is header, expect artist and title columns
  const lines = text.trim().split('\n')
  if (lines.length < 2) return []
  const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/"/g, ''))
  const artistIdx = headers.indexOf('artist')
  const titleIdx = headers.indexOf('title')
  if (artistIdx === -1 || titleIdx === -1) return []

  return lines.slice(1)
    .map(line => {
      const cols = line.split(',').map(c => c.trim().replace(/^"|"$/g, ''))
      return { artist: cols[artistIdx] ?? '', title: cols[titleIdx] ?? '' }
    })
    .filter(t => t.artist || t.title)
}
