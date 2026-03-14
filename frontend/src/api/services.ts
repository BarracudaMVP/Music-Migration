import { api } from './client'

export interface Service {
  id: string
  name: string
  capabilities: string[]
}

export interface ServicesResponse {
  services: Service[]
  auth_status: Record<string, boolean>
}

export interface MatrixResponse {
  matrix: Record<string, string[]>
}

export function fetchServices(): Promise<ServicesResponse> {
  return api.get<ServicesResponse>('/services')
}

export function fetchMatrix(): Promise<MatrixResponse> {
  return api.get<MatrixResponse>('/services/matrix')
}
