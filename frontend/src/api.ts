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
  manhole: 'Manhole',
  speed_breaker: 'Speed breaker',
  debris: 'Debris',
  barricade: 'Barricade',
}
export const CLASSES = Object.keys(CLASS_LABEL)
export const label = (c: string) => CLASS_LABEL[c] ?? c.replace(/_/g, ' ')
export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleString() : '-')
export const fmtDay = (s?: string | null) => (s ? new Date(s).toLocaleDateString() : '-')
export const RISK_COLOR: Record<string, string> = { High: 'var(--high)', Medium: 'var(--med)', Low: 'var(--low)' }

/* ---------- operations: repair costs, budget, alerts, reports ---------- */

export type CostRow = {
  defect_id: number
  uid: string
  class_name: string
  severity: string
  risk_score: number
  risk_level: string
  area_m2: number
  depth_cm: number
  volume_m3: number
  material: string
  material_cost: number
  labour_cost: number
  traffic_cost: number
  total_cost: number
  delay_weekly?: number
  delay_30d?: number
  delay_growth_pct_week?: number
  lat: number | null
  lon: number | null
  crop_url: string | null
  road_type: string
}

export type BudgetPlan = {
  budget: number
  selected: CostRow[]
  total_cost: number
  risk_covered: number
  risk_total: number
  left: number
  objective?: string
  delay_weekly_avoided?: number
}

export type Alert = {
  id: number
  type: string
  level: 'critical' | 'warning' | 'info'
  defect_id: number | null
  uid: string | null
  message: string
  status: string
  lat: number | null
  lon: number | null
  created_at: string
}

export type AlertSummary = { open: number; critical: number; warning: number; info: number }

export const ops = {
  costs: (status = 'active') => req<CostRow[]>(`/api/ops/costs?status=${status}`),
  rates: () => req<Record<string, any>>('/api/ops/rates'),
  budget: (budget: number, objective = 'risk') => req<BudgetPlan>('/api/ops/budget', json({ budget, objective })),
  weather: (lat: number, lon: number) =>
    req<{ rain_mm_24h: number; max_precip_probability: number; risk: string }>(`/api/ops/weather?lat=${lat}&lon=${lon}`),
  enrichRoads: () => req<any>('/api/ops/enrich-roads', { method: 'POST' }),
  complaintText: (id: number) => req<{ text: string }>(`/api/ops/complaint-text/${id}`),
  send: (id: number) => req<{ mock: boolean; to: string; subject: string; body: string }>(`/api/ops/send/${id}`, { method: 'POST' }),
  alerts: (status = 'open') => req<Alert[]>(`/api/alerts?status=${status}`),
  alertSummary: () => req<AlertSummary>('/api/alerts/summary'),
  setAlert: (id: number, status: 'acknowledged' | 'resolved') => req<any>(`/api/alerts/${id}`, json({ status })),
  scanAlerts: () => req<AlertSummary>('/api/alerts/scan', { method: 'POST' }),
}

export const reportUrl = (kind: 'complaint' | 'authority' | 'evidence', defectId: number) => `/api/reports/${kind}/${defectId}.pdf`

/** Indian rupees with en-IN digit grouping, e.g. "Rs 1,23,450". */
export const inr = (n: number | null | undefined) =>
  n == null || !isFinite(n) ? '-' : `Rs ${Math.round(n).toLocaleString('en-IN')}`

/** Short relative time, e.g. "5 min ago". */
export const timeAgo = (s?: string | null) => {
  if (!s) return '-'
  const sec = Math.max(0, (Date.now() - new Date(s).getTime()) / 1000)
  if (!isFinite(sec)) return '-'
  if (sec < 60) return 'just now'
  if (sec < 3600) return `${Math.floor(sec / 60)} min ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)} h ago`
  return `${Math.floor(sec / 86400)} d ago`
}

/* ---------- phone complaints: voice intake and verification ladder ---------- */

export type PhoneComplaint = {
  complaint_id: number
  ticket: string
  created_at: string
  caller_name: string | null
  caller_phone: string | null
  location_text: string | null
  landmark: string | null
  address: string | null
  lat: number | null
  lon: number | null
  issue_type: string | null
  category: string
  description: string | null
  urgency: 'high' | 'normal'
  verification: 'unverified' | 'corroborated' | 'photo_verified' | 'field_verified'
  evidence: string[]
  status: string
  upload_url: string
  media_count: number
  geocode_source: string
  summary: string | null
  updated_at: string
}

export const voice = {
  queue: (filter: 'needs_check' | 'all' = 'needs_check') => req<PhoneComplaint[]>(`/api/voice/queue?filter=${filter}`),
  count: () => req<{ needs_check: number }>('/api/voice/queue/count'),
  verify: (id: number, note = '') => req<any>(`/api/voice/verify/${id}`, json({ level: 'field_verified', note })),
  importCalls: (calls: unknown[]) => req<{ created: number; results: any[] }>('/api/voice/import', json({ calls })),
  link: (ticket: string) => req<{ upload_url: string; sms_text: string }>(`/api/voice/link/${ticket}`),
}
