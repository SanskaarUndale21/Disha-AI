export type Detection = {
  id: number
  inspection_id: number
  defect_id: number | null
  defect_uid: string | null
  class_name: string
  final_class: string
  confidence: number
  bbox: number[]
  area_ratio: number
  severity: string
  final_severity: string
  severity_score: number
  risk_score: number
  risk_level: string
  track_id: number | null
  frame_index: number
  frames_seen: number
  lat: number | null
  lon: number | null
  crop_url: string | null
  is_duplicate: boolean
  match_score: number | null
  match_distance_m: number | null
  verification: string
  corrected_class: string | null
  corrected_severity: string | null
  verified_by: string | null
  verified_at: string | null
  verify_note: string | null
  annotated_url?: string
  media_type?: string
}

export type Inspection = {
  id: number
  media_type: 'image' | 'video' | 'live'
  original_name: string
  media_url: string | null
  annotated_url: string | null
  width: number
  height: number
  frames_processed: number
  fps: number | null
  captured_at: string
  created_at: string
  lat: number | null
  lon: number | null
  location_source: string
  road_name: string | null
  road_type: string
  traffic_level: string
  inspector: string | null
  notes: string | null
  duplicate_of_inspection: number | null
  processing_ms: number | null
  model_name: string | null
  summary: Record<string, any> | null
  detections?: Detection[]
}

export type Defect = {
  id: number
  uid: string
  class_name: string
  lat: number | null
  lon: number | null
  location_source: string
  road_type: string
  traffic_level: string
  severity: string
  severity_score: number
  risk_score: number
  risk_level: string
  status: string
  trend: string
  report_count: number
  crop_url: string | null
  first_seen: string
  last_seen: string
  verified: boolean
  detections?: Detection[]
  history?: {
    inspection_id: number | null
    observed_at: string
    present: boolean
    area_ratio: number | null
    severity: string | null
    severity_score: number | null
    risk_score: number | null
    trend: string
  }[]
}

import { authToken } from './auth'

export const authHeaders = (h: Record<string, string> = {}) => {
  const t = authToken()
  return t ? { ...h, Authorization: `Bearer ${t}` } : h
}

async function req<T>(url: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(url, { ...init, headers: authHeaders((init.headers as Record<string, string>) ?? {}) })
  if (!r.ok) {
    let msg = r.statusText
    try {
      const j = await r.json()
      msg = j.detail ?? msg
    } catch {
      /* ignore */
    }
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return r.json()
}

const json = (body: unknown, method = 'POST'): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => req<any>('/api/health'),
  config: () => req<any>('/api/config'),
  stats: () => req<any>('/api/stats'),
  inspections: () => req<Inspection[]>('/api/inspections'),
  inspection: (id: number) => req<Inspection>(`/api/inspections/${id}`),
  deleteInspection: (id: number) => req<any>(`/api/inspections/${id}`, { method: 'DELETE' }),
  upload: (fd: FormData) => req<any>('/api/inspections', { method: 'POST', body: fd }),
  job: (id: string) => req<any>(`/api/jobs/${id}`),
  defects: (q = '') => req<Defect[]>(`/api/defects${q}`),
  defect: (id: number) => req<Defect>(`/api/defects/${id}`),
  patchDefect: (id: number, body: Partial<Defect>) => req<Defect>(`/api/defects/${id}`, json(body, 'PATCH')),
  queue: (status = 'pending') => req<Detection[]>(`/api/verification/queue?status=${status}`),
  verify: (id: number, body: any) => req<Detection>(`/api/detections/${id}/verify`, json(body)),
  progress: (lat: number, lon: number, r: number) =>
    req<any>(`/api/progress?lat=${lat}&lon=${lon}&radius_m=${r}`),
  metrics: () => req<any>('/api/model/metrics'),
  users: (role = '') => req<any[]>(`/api/admin/users${role ? `?role=${role}` : ''}`),
  patchUser: (id: string, body: any) => req<any>(`/api/admin/users/${id}`, json(body, 'PATCH')),
  complaints: (q = '') => req<any[]>(`/api/complaints${q}`),
  complaint: (id: number) => req<any>(`/api/complaints/${id}`),
  patchComplaint: (id: number, body: any) => req<any>(`/api/complaints/${id}`, json(body, 'PATCH')),
}

export const CLASS_LABEL: Record<string, string> = {
  pothole: 'Pothole',
  alligator_crack: 'Alligator crack',
  transverse_crack: 'Transverse crack',
  longitudinal_crack: 'Longitudinal crack',
}
export const CLASSES = Object.keys(CLASS_LABEL)
export const label = (c: string) => CLASS_LABEL[c] ?? c.replace(/_/g, ' ')
export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleString() : '-')
export const fmtDay = (s?: string | null) => (s ? new Date(s).toLocaleDateString() : '-')
export const RISK_COLOR: Record<string, string> = { High: 'var(--high)', Medium: 'var(--med)', Low: 'var(--low)' }
