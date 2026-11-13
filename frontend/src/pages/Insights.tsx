import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CircleMarker, MapContainer, Marker, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { ArrowDownRight, ArrowRight, ArrowUpRight, Warning, Moon, CloudRain, Crosshair } from '@phosphor-icons/react'
import { authHeaders, inr, label, ops, type BudgetPlan } from '../api'
import { DEFAULT_CENTER, useTileUrl } from '../components'
import './insights.css'

type Road = {
  id: number | string; name: string; ref?: string; lat: number; lon: number; length_km: number; score: number
  grade: string; open_defects: number; serious: number; trend: 'improving' | 'worsening' | 'stable'
  contractor?: string; built_year?: number; under_liability?: boolean
}
type Contractor = {
  contractor: string; roads: number; km: number; open_defects: number; serious: number; defects_per_km: number
  repaired: number; liability_roads: number; score: number; rank: number
}
type WItem = { uid: string; class: string; severity: string; now_rs: number; in_4_weeks_rs: number; extra_rs: number; lat: number; lon: number }
type Waiting = { weekly_total_rs: number; total_now_rs: number; total_4w_rs: number; items: WItem[] }
type Acct = {
  ticket: string; category: string; address: string; days_open: number; hours_open: number; status: string
  ward: string; officer: string; overdue: boolean; sla_days: number; escalation_level: number | string
}
type Near = { id: number; lat: number; lon: number; note: string; created_at: string }

async function getJson<T>(url: string): Promise<T> {
  let r: Response
  try { r = await fetch(url, { headers: authHeaders() }) } catch { throw new Error('Cannot reach the server.') }
  if (!r.ok) throw new Error(r.status === 404 ? 'This insight is not available yet.' : `Server returned ${r.status}.`)
  return r.json()
}

function useData<T>(url: string, fallback: T) {
  const [data, setData] = useState<T>(fallback)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(true)
  const load = useCallback(() => {
    setLoading(true)
    getJson<T>(url).then((d) => { setData(d); setErr('') }).catch((e) => setErr(e.message)).finally(() => setLoading(false))
  }, [url])
  useEffect(load, [load])
  return { data, err, loading, reload: load }
}

const reduced = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
const scoreColor = (s: number) => (s >= 70 ? '#81b29a' : s >= 45 ? '#f2cc8f' : '#e07a5f')

function useCount(target: number, ms = 900) {
  const [v, setV] = useState(0)
  const from = useRef(0)
  useEffect(() => {
    if (reduced()) { setV(target); return }
    const a = from.current, t0 = performance.now()
    let raf = 0
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - p, 3)
      const cur = a + (target - a) * e
      setV(cur); from.current = cur
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [target, ms])
  return v
}
const Num = ({ v, money, d = 0 }: { v: number; money?: boolean; d?: number }) => {
  const c = useCount(v)
  return <>{money ? inr(c) : c.toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: d })}</>
}

function Ring({ value, size = 64, color, text }: { value: number; size?: number; color?: string; text?: string }) {
  const c = color ?? scoreColor(value), r = size / 2 - 5, C = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(100, value)) / 100
  return (
    <svg width={size} height={size} className="ins-ring" style={{ filter: `drop-shadow(0 0 6px ${c}88)`, flex: 'none' }} aria-hidden>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--fill-2)" strokeWidth="5" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={c} strokeWidth="5" strokeLinecap="round"
        strokeDasharray={`${C * pct} ${C}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ transition: 'stroke-dasharray .7s ease, stroke .4s' }} />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" fill="var(--ink)" fontSize={size * 0.3} fontWeight="600" className="mono">{text ?? Math.round(value)}</text>
    </svg>
  )
}

const TrendIcon = ({ t }: { t: string }) =>
  t === 'improving' ? <span className="ins-tr good"><ArrowUpRight size={14} weight="bold" /> improving</span>
    : t === 'worsening' ? <span className="ins-tr bad"><ArrowDownRight size={14} weight="bold" /> worsening</span>
    : <span className="ins-tr"><ArrowRight size={14} weight="bold" /> stable</span>

function Retry({ err, onRetry }: { err: string; onRetry: () => void }) {
  return (
    <div className="card empty" role="alert">
      <Warning size={26} />
      <b>{err}</b>
      <button className="btn sm" onClick={onRetry}>Retry</button>
    </div>
  )
}
const Skel = () => <div className="card ins-skel" aria-busy="true" />

function FitMap({ pts }: { pts: [number, number][] }) {
  const map = useMap()
  const key = JSON.stringify(pts)
  useEffect(() => {
    if (pts.length > 1) map.fitBounds(L.latLngBounds(pts), { padding: [30, 30], maxZoom: 15 })
    else if (pts.length === 1) map.setView(pts[0], 14)
    const t = setTimeout(() => map.invalidateSize(), 200)
    return () => clearTimeout(t)
  }, [key]) // eslint-disable-line
  return null
}
function Picker({ on }: { on: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => on(e.latlng.lat, e.latlng.lng) })
  return null
}
const pulseIcon = L.divIcon({ className: 'ins-pulse-wrap', html: '<span class="ins-pulse"></span>', iconSize: [22, 22], iconAnchor: [11, 11] })
const pickIcon = L.divIcon({ className: 'ins-pulse-wrap', html: '<span class="ins-pick"></span>', iconSize: [18, 18], iconAnchor: [9, 9] })

/* ---------- 1 + 6 + 7 : road health ---------- */
type Veh = 'two' | 'car' | 'truck'
function adjust(s: number, veh: Veh, night: boolean, rain: boolean) {
  const pen = 100 - s
  const m = (veh === 'two' ? 1.4 : veh === 'truck' ? 0.8 : 1) * (night ? 1.25 : 1) * (rain ? 1.3 : 1)
  return Math.max(0, Math.min(100, Math.round(100 - pen * m)))
}

function RoadHealth() {
  const { data, err, loading, reload } = useData<Road[]>('/api/insights/road-health', [])
  const near = useData<Near[]>('/api/nearmiss', [])
  const tile = useTileUrl()
  const [veh, setVeh] = useState<Veh>('car')
  const [night, setNight] = useState(false)
  const [rain, setRain] = useState(false)
  const [sel, setSel] = useState<Road | null>(null)
  const [pick, setPick] = useState<[number, number] | null>(null)
  const [note, setNote] = useState('')
  const [sent, setSent] = useState('')
  const [busy, setBusy] = useState(false)

  const rows = useMemo(() => {
    const l = (Array.isArray(data) ? data : []).map((r) => ({ ...r, adj: adjust(r.score, veh, night, rain) }))
    return l.sort((a, b) => a.adj - b.adj)
  }, [data, veh, night, rain])
  const adjusted = veh !== 'car' || night || rain
  const pts = rows.filter((r) => r.lat != null).map((r) => [r.lat, r.lon] as [number, number])
  const nm = Array.isArray(near.data) ? near.data : []
  const cur = sel ? rows.find((r) => r.id === sel.id) : null

  const report = async () => {
    if (!pick) return
    setBusy(true); setSent('')
    try {
      const r = await fetch('/api/nearmiss', { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify({ lat: pick[0], lon: pick[1], note }) })
      if (!r.ok) throw new Error()
      setSent('Near miss recorded. Thank you.'); setNote(''); setPick(null); near.reload()
    } catch { setSent('Could not save the report. Try again.') } finally { setBusy(false) }
  }

  if (err) return <Retry err={err} onRetry={reload} />
  return (
    <div className="ins-split">
      <div className="ins-col">
        <div className="card ins-ctl">
          <div className="seg" role="group" aria-label="Vehicle">
            {([['two', 'Two-wheeler'], ['car', 'Car'], ['truck', 'Truck']] as const).map(([k, t]) => (
              <button key={k} className={veh === k ? 'on' : ''} onClick={() => setVeh(k)} aria-pressed={veh === k}>{t}</button>
            ))}
          </div>
          <button className={`ins-sw ${night ? 'on' : ''}`} onClick={() => setNight(!night)} role="switch" aria-checked={night}><Moon size={15} /> Night <i /></button>
          <button className={`ins-sw ${rain ? 'on' : ''}`} onClick={() => setRain(!rain)} role="switch" aria-checked={rain}><CloudRain size={15} /> Rain <i /></button>
        </div>
        {loading && !rows.length ? <><Skel /><Skel /><Skel /></> : rows.length === 0 ? <div className="card empty">No roads scored yet.</div> : (
          <div className="ins-list">
            {rows.map((r, i) => (
              <button key={r.id} className={`card tilt ins-road ${cur?.id === r.id ? 'sel' : ''}`} style={{ animationDelay: `${Math.min(i, 12) * 40}ms` }} onClick={() => setSel(r)}>
                <Ring value={r.adj} />
                <div className="ins-road-b">
                  <b>{r.name}</b>
                  <span className="mono-l">{r.ref || 'road'} / {r.length_km?.toFixed?.(1)} km</span>
                  <span className="note">{r.open_defects} open, {r.serious} serious <TrendIcon t={r.trend} /></span>
                </div>
                <div className="ins-road-r">
                  <span className="ins-grade" style={{ background: `${scoreColor(r.adj)}26`, color: scoreColor(r.adj), borderColor: `${scoreColor(r.adj)}66` }}>{r.grade}</span>
                  {adjusted && <span className="mono-l">adjusted<br />base {Math.round(r.score)}</span>}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="ins-col ins-sticky">
        <div className="card ins-map-card">
          <div className="ins-map-h">
            <span className="mono-l">Road health map</span>
            <span className="ins-chip"><span className="ins-dot" /> {nm.length} near misses</span>
          </div>
          <div className="ins-map">
            <MapContainer center={pts[0] ?? DEFAULT_CENTER} zoom={13} style={{ height: '100%', width: '100%' }}>
              <TileLayer url={tile} maxNativeZoom={16} maxZoom={19} />
              <FitMap pts={pts} />
              <Picker on={(a, b) => setPick([a, b])} />
              {rows.map((r) => r.lat != null && (
                <CircleMarker key={r.id} center={[r.lat, r.lon]} radius={cur?.id === r.id ? 17 : 11}
                  pathOptions={{ color: scoreColor(r.adj), fillColor: scoreColor(r.adj), fillOpacity: 0.45, weight: 3, className: 'ins-glow' }}
                  eventHandlers={{ click: () => setSel(r) }}>
                  <Tooltip>{r.name}: {r.adj}</Tooltip>
                </CircleMarker>
              ))}
              {nm.filter((n) => n.lat != null).map((n) => <Marker key={n.id} position={[n.lat, n.lon]} icon={pulseIcon}><Tooltip>{n.note || 'Near miss'}</Tooltip></Marker>)}
              {pick && <Marker position={pick} icon={pickIcon} />}
            </MapContainer>
          </div>
        </div>
        <div className="card ins-nm">
          <h3><Crosshair size={18} /> Report a near miss</h3>
          <p className="note">{pick ? `Point chosen: ${pick[0].toFixed(5)}, ${pick[1].toFixed(5)}` : 'Click the map to choose where it happened.'}</p>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            <input className="ins-in" placeholder="What happened?" value={note} onChange={(e) => setNote(e.target.value)} aria-label="Near miss note" />
            <button className="btn primary" disabled={!pick || busy} onClick={report}>{busy ? 'Saving' : 'Report'}</button>
          </div>
          {sent && <p className="note" role="status">{sent}</p>}
        </div>
        {cur && (
          <div className="card ins-detail">
            <div className="row" style={{ gap: 14 }}>
              <Ring value={cur.adj} size={84} />
              <div><h3 style={{ margin: 0 }}>{cur.name}</h3><span className="mono-l">{cur.ref} / grade {cur.grade}</span></div>
              <button className="btn sm" style={{ marginLeft: 'auto' }} onClick={() => setSel(null)}>Close</button>
            </div>
            <dl className="ins-dl">
              <div><dt>Contractor</dt><dd>{cur.contractor || '-'}</dd></div>
              <div><dt>Built</dt><dd>{cur.built_year || '-'}</dd></div>
              <div><dt>Length</dt><dd>{cur.length_km?.toFixed?.(1)} km</dd></div>
              <div><dt>Open / serious</dt><dd>{cur.open_defects} / {cur.serious}</dd></div>
              <div><dt>Base score</dt><dd>{Math.round(cur.score)}</dd></div>
              <div><dt>Liability</dt><dd>{cur.under_liability ? 'Under defect liability' : 'Expired'}</dd></div>
            </dl>
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------- 2 : contractors ---------- */
function Contractors() {
  const { data, err, loading, reload } = useData<Contractor[]>('/api/insights/contractors', [])
  if (err) return <Retry err={err} onRetry={reload} />
  const rows = [...(Array.isArray(data) ? data : [])].sort((a, b) => a.rank - b.rank)
  if (loading && !rows.length) return <Skel />
  if (!rows.length) return <div className="card empty">No contractor data yet.</div>
  const worst = rows.reduce((a, b) => (b.score < a.score ? b : a), rows[0])
  const liab = rows.reduce((a, b) => a + (b.liability_roads || 0), 0)
  return (
    <div className="ins-col">
      <div className="card ins-worst tilt">
        <Warning size={30} color="#e07a5f" weight="duotone" />
        <div>
          <span className="mono-l">Worst performer</span>
          <h3 style={{ margin: '4px 0' }}>{worst.contractor}</h3>
          <span className="note">{worst.defects_per_km.toFixed(1)} defects per km across {worst.roads} roads, {worst.serious} serious.</span>
        </div>
        <Ring value={worst.score} size={76} />
      </div>
      <div className="card ins-note">Roads still under defect liability ({liab}) can be repaired by the contractor at no cost to the city. Raise a claim before the period ends.</div>
      <div className="ins-list">
        {rows.map((c) => (
          <div key={c.contractor} className="card tilt ins-ct">
            <span className="ins-rank">#{c.rank}</span>
            <div className="ins-ct-b">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <b>{c.contractor}</b><span className="mono" style={{ color: scoreColor(c.score) }}>{Math.round(c.score)}</span>
              </div>
              <div className="ins-bar"><i style={{ width: `${Math.max(2, c.score)}%`, background: scoreColor(c.score), boxShadow: `0 0 12px ${scoreColor(c.score)}88` }} /></div>
              <span className="note">{c.roads} roads, {c.km.toFixed(1)} km / {c.open_defects} open / {c.defects_per_km.toFixed(1)} per km / {c.repaired} repaired / {c.liability_roads} under liability</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ---------- 3 : cost of waiting ---------- */
function Waiting() {
  const { data, err, loading, reload } = useData<Waiting | null>('/api/insights/waiting-cost', null)
  const [t0] = useState(() => performance.now())
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (reduced()) return
    const id = setInterval(() => setTick(performance.now()), 100)
    return () => clearInterval(id)
  }, [])
  if (err) return <Retry err={err} onRetry={reload} />
  if (loading && !data) return <Skel />
  if (!data) return null
  const perSec = (data.weekly_total_rs || 0) / (7 * 86400)
  const live = (data.total_now_rs || 0) + (tick ? ((tick - t0) / 1000) * perSec : 0)
  const max = Math.max(data.total_4w_rs, 1)
  const items = [...(data.items ?? [])].sort((a, b) => b.extra_rs - a.extra_rs).slice(0, 8)
  return (
    <div className="ins-col">
      <div className="card ins-big tilt">
        <span className="mono-l">Cost of waiting, live</span>
        <div className="ins-counter mono">{inr(live)}</div>
        <span className="note">Rising by about Rs {perSec.toFixed(4)} every second ({inr(data.weekly_total_rs)} per week) while defects stay open.</span>
        <div className="ins-4w">
          <div><span className="mono-l">Today</span><div className="ins-bar big"><i style={{ width: `${(data.total_now_rs / max) * 100}%`, background: '#81b29a' }} /></div><b className="mono">{inr(data.total_now_rs)}</b></div>
          <div><span className="mono-l">In 4 weeks</span><div className="ins-bar big"><i style={{ width: '100%', background: '#e07a5f', boxShadow: '0 0 14px #e07a5f88' }} /></div><b className="mono">{inr(data.total_4w_rs)}</b></div>
        </div>
      </div>
      <div className="ins-list">
        {items.map((it, i) => (
          <div key={it.uid} className="card tilt ins-wi">
            <span className="ins-rank">{i + 1}</span>
            <div className="ins-ct-b">
              <b>{label(it.class)} <span className="mono-l">{it.uid}</span></b>
              <span className="note">{it.severity} / now {inr(it.now_rs)} / in 4 weeks {inr(it.in_4_weeks_rs)}</span>
            </div>
            <b className="mono" style={{ color: '#e07a5f' }}>+<Num v={it.extra_rs} money /></b>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ---------- 4 : accountability ---------- */
const ESC: Record<string, string> = { '1': 'L1 Ward engineer', '2': 'L2 Executive engineer', '3': 'L3 Commissioner' }
function Accountability() {
  const { data, err, loading, reload } = useData<Acct[]>('/api/insights/accountability', [])
  if (err) return <Retry err={err} onRetry={reload} />
  const rows = [...(Array.isArray(data) ? data : [])].sort((a, b) => Number(b.overdue) - Number(a.overdue) || b.days_open - a.days_open)
  if (loading && !rows.length) return <Skel />
  if (!rows.length) return <div className="card empty">No open tickets.</div>
  return (
    <div className="ins-grid">
      {rows.map((t) => {
        const lvl = String(t.escalation_level).replace(/\D/g, '') || '0'
        const left = Math.max(0, t.sla_days - t.days_open)
        const pct = t.sla_days ? Math.max(0, 100 * (1 - t.days_open / t.sla_days)) : 0
        const col = t.overdue ? '#e07a5f' : '#81b29a'
        return (
          <div key={t.ticket} className={`card tilt ins-ac ${t.overdue ? 'over' : ''}`}>
            <Ring value={t.overdue ? 100 : pct} size={72} color={col} text={t.overdue ? `+${Math.max(0, t.days_open - t.sla_days)}d` : `${left}d`} />
            <div className="ins-ct-b">
              <span className="mono-l">{t.ticket} / {t.category}</span>
              <b>{t.address || 'Address not recorded'}</b>
              <span className="note">{t.ward} / {t.officer} / {t.status}</span>
              <span className="note">{t.days_open}d {Math.round(t.hours_open % 24)}h open, SLA {t.sla_days}d</span>
              {lvl !== '0' && <span className={`ins-esc l${lvl}`}>{ESC[lvl] ?? `L${lvl}`}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ---------- 5 : budget optimizer ---------- */
const LAKH = 100000
function Budget() {
  const tile = useTileUrl()
  const [budget, setBudget] = useState(5 * LAKH)
  const [plan, setPlan] = useState<BudgetPlan | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const run = useCallback((b: number) => {
    setBusy(true)
    ops.budget(b, 'risk').then((p) => { setPlan({ ...p, selected: Array.isArray(p?.selected) ? p.selected : [] }); setErr('') })
      .catch((e) => setErr(e?.message || 'Could not plan repairs')).finally(() => setBusy(false))
  }, [])
  useEffect(() => { const t = setTimeout(() => run(budget), 250); return () => clearTimeout(t) }, [budget, run])
  const sel = plan?.selected ?? []
  const pts = sel.filter((s) => s.lat != null).map((s) => [s.lat!, s.lon!] as [number, number])
  const share = plan && plan.risk_total > 0 ? Math.min(100, (plan.risk_covered / plan.risk_total) * 100) : 0
  const clamp = (n: number) => Math.max(LAKH, Math.min(50 * LAKH, n || LAKH))
  return (
    <div className="ins-split">
      <div className="ins-col">
        <div className="card ins-ctl col">
          <span className="mono-l">Budget</span>
          <div className="ins-counter mono sm">{inr(budget)}</div>
          <input type="range" min={LAKH} max={50 * LAKH} step={LAKH / 2} value={budget} onChange={(e) => setBudget(Number(e.target.value))} aria-label="Budget in rupees" className="ins-range" />
          <input className="ins-in" type="number" value={budget} min={LAKH} max={50 * LAKH} onChange={(e) => setBudget(clamp(Number(e.target.value)))} aria-label="Budget amount" />
          <div className="note">1 lakh to 50 lakh rupees</div>
        </div>
        {err ? <Retry err={err} onRetry={() => run(budget)} /> : (
          <div className="ins-stats" style={{ opacity: busy ? 0.7 : 1 }}>
            <div className="card tilt"><span className="mono-l">Spent</span><b className="ins-v mono"><Num v={plan?.total_cost ?? 0} money /></b></div>
            <div className="card tilt"><span className="mono-l">Defects fixed</span><b className="ins-v mono"><Num v={sel.length} /></b></div>
            <div className="card tilt"><span className="mono-l">Risk reduced</span><b className="ins-v mono"><Num v={share} d={0} />%</b>
              <div className="ins-bar"><i style={{ width: `${share}%`, background: '#81b29a' }} /></div></div>
          </div>
        )}
      </div>
      <div className="card ins-map-card ins-sticky">
        <div className="ins-map" style={{ height: 460 }}>
          <MapContainer center={pts[0] ?? DEFAULT_CENTER} zoom={13} style={{ height: '100%', width: '100%' }}>
            <TileLayer url={tile} maxNativeZoom={16} maxZoom={19} />
            <FitMap pts={pts} />
            {sel.filter((s) => s.lat != null).map((s) => (
              <CircleMarker key={s.defect_id} center={[s.lat!, s.lon!]} radius={9} pathOptions={{ color: '#81b29a', fillColor: '#81b29a', fillOpacity: 0.55, weight: 3, className: 'ins-glow' }}>
                <Tooltip>{label(s.class_name)} / {inr(s.total_cost)}</Tooltip>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>
      </div>
    </div>
  )
}

/* ---------- page ---------- */
const TABS = [
  ['health', 'Road health'], ['contractors', 'Contractors'], ['waiting', 'Cost of waiting'], ['clock', 'Accountability'], ['budget', 'Budget optimizer'],
] as const

export default function Insights() {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('health')
  return (
    <>
      <div className="page-h">
        <div>
          <h1>City insights</h1>
          <p>Road health, contractor performance, the price of delay, and who is answerable. All from live data.</p>
        </div>
      </div>
      <div className="ins-tabs" role="tablist">
        {TABS.map(([k, t]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{t}</button>)}
      </div>
      <div key={tab} className="ins-fade">
        {tab === 'health' && <RoadHealth />}
        {tab === 'contractors' && <Contractors />}
        {tab === 'waiting' && <Waiting />}
        {tab === 'clock' && <Accountability />}
        {tab === 'budget' && <Budget />}
      </div>
    </>
  )
}
