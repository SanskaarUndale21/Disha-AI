import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MapContainer, Marker, Polyline, Popup, Rectangle, TileLayer, Tooltip, useMap } from 'react-leaflet'
import L from 'leaflet'
import {
  ArrowsDownUp, ChatCircleText, Crosshair, DeviceMobile, Drop, Globe, Lightbulb, MapPin, Path, Phone, Trash, Warning, WarningCircle,
} from '@phosphor-icons/react'
import { api, label, pub, routes, timeAgo, type Defect, type PlannedRoute, type PublicComplaint, type PublicSummary, type RoutePlan, type Zones } from '../api'
import { DEFAULT_CENTER, DefectDrawer, useTileUrl } from '../components'
import { useLiveRefresh } from '../events'
import { RISK_HEX, Tile } from '../icons'

const ATTR = 'Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors'
const LEVEL_HEX = { red: '#d92d20', yellow: '#f2b705', green: '#2e9a57' } as const
const LEVEL_WORD = { red: 'Red zone', yellow: 'Yellow zone', green: 'Green zone' } as const
const LIVE_PREFIXES = ['map.', 'defect.', 'complaint.']

type Mode = 'zones' | 'defects' | 'both'
type Fly = { lat: number; lon: number; zoom?: number; key: number }

function cellBounds(c: { lat: number; lon: number; size_m: number }): L.LatLngBoundsExpression {
  const dLat = c.size_m / 2 / 111320
  const dLon = c.size_m / 2 / (111320 * Math.max(0.2, Math.cos((c.lat * Math.PI) / 180)))
  return [[c.lat - dLat, c.lon - dLon], [c.lat + dLat, c.lon + dLon]]
}

function countIcon(n: number, level: keyof typeof LEVEL_HEX) {
  return L.divIcon({ className: '', iconSize: [36, 22], iconAnchor: [18, 11], html: `<div class="lm-count ${level}">${n}</div>` })
}
function defectIcon(d: Defect) {
  const col = RISK_HEX[d.risk_level] ?? '#8e8e93'
  const size = 16 + Math.min(8, (d.report_count - 1) * 2)
  return L.divIcon({ className: '', iconSize: [size, size], iconAnchor: [size / 2, size / 2], html: `<div class="rw-pin" style="--c:${col};width:${size}px;height:${size}px"></div>` })
}
function routeDotIcon(n: number, severe: boolean) {
  return L.divIcon({ className: '', iconSize: [22, 22], iconAnchor: [11, 11], html: `<div class="lm-rdot ${severe ? 'sev' : ''}">${n}</div>` })
}
function endIcon(kind: 'start' | 'end') {
  return L.divIcon({ className: '', iconSize: [26, 26], iconAnchor: [13, 13], html: `<div class="lm-end ${kind}">${kind === 'start' ? 'A' : 'B'}</div>` })
}
const pulseIcon = L.divIcon({ className: '', iconSize: [40, 40], iconAnchor: [20, 20], html: '<div class="lm-pulse"></div>' })

function Controller({ fly, fit }: { fly: Fly | null; fit: L.LatLngBoundsExpression | null }) {
  const map = useMap()
  useEffect(() => {
    if (fly) map.flyTo([fly.lat, fly.lon], fly.zoom ?? Math.max(map.getZoom(), 16), { duration: 0.8 })
  }, [fly?.key])
  const fitKey = fit ? JSON.stringify(fit) : ''
  useEffect(() => {
    if (fit) map.fitBounds(fit, { padding: [50, 50], maxZoom: 16 })
  }, [fitKey])
  return null
}

function categoryIcon(c: string) {
  const s = (c || '').toLowerCase()
  if (s.includes('pothole') || s.includes('crack') || s.includes('road')) return { icon: Warning, color: '#dd7a07' }
  if (s.includes('water') || s.includes('drain') || s.includes('flood')) return { icon: Drop, color: '#1f5fbf' }
  if (s.includes('light')) return { icon: Lightbulb, color: '#b58a00' }
  if (s.includes('garbage') || s.includes('debris') || s.includes('waste')) return { icon: Trash, color: '#6a4fc7' }
  return { icon: ChatCircleText, color: '#ff9500' }
}
const SRC: Record<string, { icon: any; text: string }> = {
  phone: { icon: Phone, text: 'Phone' },
  voice: { icon: Phone, text: 'Phone' },
  app: { icon: DeviceMobile, text: 'App' },
  mobile: { icon: DeviceMobile, text: 'App' },
  web: { icon: Globe, text: 'Web' },
}
const statusClass = (s: string) => `st-${(s || '').toLowerCase().replace(/[^a-z]+/g, '-')}`
const statusText = (s: string) => (s || '').replace(/_/g, ' ')

function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="skel-stack">
      {Array.from({ length: rows }, (_, i) => <i key={i} className="skel" style={{ width: `${95 - i * 12}%` }} />)}
    </div>
  )
}

function recChanged(a: RoutePlan, b: RoutePlan) {
  const ra = a.routes.find((r) => r.index === a.recommended)
  const rb = b.routes.find((r) => r.index === b.recommended)
  if (!ra || !rb) return false
  return ra.index !== rb.index || Math.abs(ra.distance_km - rb.distance_km) > 0.05
}

/* ---------- summary and legend ---------- */
function SummaryCard({ sum, zones, err, onRetry }: { sum: PublicSummary | null; zones: Zones | null; err: boolean; onRetry: () => void }) {
  if (err && !sum && !zones)
    return (
      <div className="card lm-card">
        <div className="empty"><WarningCircle size={28} weight="duotone" />Map data could not be loaded.<button className="btn sm" onClick={onRetry}>Try again</button></div>
      </div>
    )
  if (!sum && !zones) return <div className="card lm-card"><Skeleton rows={4} /></div>
  const counts = {
    red: sum?.red_zones ?? zones?.totals.red,
    yellow: sum?.yellow_zones ?? zones?.totals.yellow,
    green: sum?.green_zones ?? zones?.totals.green,
  }
  return (
    <div className="card lm-card">
      <div className="lm-kpis">
        <div><b className="num">{sum?.open_defects ?? zones?.totals.defects ?? '-'}</b><span>Open defects</span></div>
        <div><b className="num">{sum?.complaints_total ?? '-'}</b><span>Complaints received</span></div>
        <div><b className="num">{sum?.complaints_open ?? '-'}</b><span>Complaints open</span></div>
      </div>
      <div className="lm-zones">
        {(['red', 'yellow', 'green'] as const).map((k) => (
          <span key={k} className="lm-zchip"><i style={{ background: LEVEL_HEX[k] }} /><b className="num">{counts[k] ?? '-'}</b> {k}</span>
        ))}
      </div>
      {sum?.most_affected_area && (
        <div className="lm-area"><MapPin size={16} weight="fill" color="var(--red)" /> Most affected area <b>{sum.most_affected_area}</b></div>
      )}
    </div>
  )
}

function Legend() {
  return (
    <div className="lm-legend">
      <b>Zone colours</b>
      <span><i style={{ background: LEVEL_HEX.green }} />Green: 1 to 2 defects</span>
      <span><i style={{ background: LEVEL_HEX.yellow }} />Yellow: 3 to 5 defects</span>
      <span><i style={{ background: LEVEL_HEX.red }} />Red: 6 or more defects, or 3 or more serious</span>
    </div>
  )
}

/* ---------- route planner ---------- */
function RoutePanel(p: {
  plan: RoutePlan | null
  clear: () => void
  selected: number
  setSelected: (i: number) => void
  note: string
  doPlan: () => void
  loading: boolean
  err: string
  from: string
  to: string
  setFrom: (s: string) => void
  setTo: (s: string) => void
}) {
  const [geoErr, setGeoErr] = useState('')
  const locate = () => {
    setGeoErr('')
    if (!navigator.geolocation) return setGeoErr('This browser cannot share your location.')
    navigator.geolocation.getCurrentPosition(
      (pos) => p.setFrom(`${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)}`),
      () => setGeoErr('Location is blocked. Type a place name instead.'),
      { timeout: 8000 },
    )
  }
  return (
    <div className="card lm-card">
      <div className="row" style={{ marginBottom: 12 }}>
        <Tile icon={Path} color="#2e9a57" />
        <h3 style={{ margin: 0 }}>Route planner</h3>
      </div>
      <form className="lm-form" onSubmit={(e) => { e.preventDefault(); p.doPlan() }}>
        <label className="f">From
          <div className="lm-in">
            <input value={p.from} onChange={(e) => p.setFrom(e.target.value)} placeholder="Place name or lat, lon" />
            <button type="button" className="btn sm" onClick={locate} title="Use my location"><Crosshair size={15} weight="bold" /> My location</button>
          </div>
        </label>
        <div className="lm-swaprow">
          <button type="button" className="icon-btn lm-swap" onClick={() => { p.setFrom(p.to); p.setTo(p.from) }} aria-label="Swap start and destination" title="Swap"><ArrowsDownUp size={15} weight="bold" /></button>
        </div>
        <label className="f">To
          <input value={p.to} onChange={(e) => p.setTo(e.target.value)} placeholder="Place name or lat, lon" />
        </label>
        <button className="btn primary wide" disabled={p.loading || !p.from.trim() || !p.to.trim()}>{p.loading ? 'Comparing...' : 'Compare routes'}</button>
      </form>
      {geoErr && <div className="note" style={{ marginTop: 8 }}>{geoErr}</div>}
      {p.err && <div className="err" style={{ marginTop: 12 }}>{p.err}</div>}
      {p.note && <div className="lm-note" role="status"><WarningCircle size={16} weight="fill" /> {p.note}</div>}
      {p.loading && !p.plan && <div style={{ marginTop: 12 }}><Skeleton rows={3} /></div>}
      {p.plan && (
        <div className="lm-routes">
          <div className="lm-advice">{p.plan.advice}</div>
          {p.plan.routes.map((r) => <RouteCard key={r.index} r={r} on={r.index === p.selected} onPick={() => p.setSelected(r.index)} />)}
          <button className="btn sm" onClick={p.clear}>Clear route</button>
        </div>
      )}
      {!p.plan && !p.loading && !p.err && <div className="note" style={{ marginTop: 12 }}>Compare the quickest road with the smoothest one. Reported potholes add delay to each route.</div>}
    </div>
  )
}

function RouteCard({ r, on, onPick }: { r: PlannedRoute; on: boolean; onPick: () => void }) {
  return (
    <button className={`lm-route ${on ? 'on' : ''}`} onClick={onPick} aria-pressed={on}>
      <div className="lm-route-top">
        <b className="num">{Math.round(r.duration_min)} min</b>
        <span className="num muted">{r.distance_km.toFixed(1)} km</span>
        <span className="spacer" />
        {r.labels.map((l) => <span key={l} className={`lm-chip ${l}`}>{l}</span>)}
      </div>
      <div className="note">
        <span className="num">{r.defect_count}</span> reported pothole{r.defect_count === 1 ? '' : 's'}
        {r.severe_count > 0 && <>, <b className="num" style={{ color: 'var(--red)' }}>{r.severe_count}</b> serious</>}
        {r.penalty_min > 0 && <>, about <span className="num">{r.penalty_min.toFixed(1)}</span> min of slow driving</>}
      </div>
    </button>
  )
}

/* ---------- complaints feed ---------- */
function Feed({ items, loading, err, fresh, onPick }: { items: PublicComplaint[]; loading: boolean; err: boolean; fresh: Set<string>; onPick: (c: PublicComplaint) => void }) {
  return (
    <div className="card lm-card lm-feed">
      <div className="row" style={{ marginBottom: 8 }}>
        <Tile icon={ChatCircleText} color="#ff9500" />
        <h3 style={{ margin: 0 }}>Complaints received</h3>
        <span className="spacer" />
        <span className="live-chip"><i className="dot ok" /> Live</span>
      </div>
      {loading && <Skeleton rows={4} />}
      {!loading && err && <div className="note">Complaints could not be loaded.</div>}
      {!loading && !err && items.length === 0 && <div className="empty">No complaints yet. New reports from citizens appear here the moment they arrive.</div>}
      <div className="lm-list">
        {items.map((c) => {
          const ci = categoryIcon(c.category)
          const s = SRC[(c.source || '').toLowerCase()]
          const can = c.lat != null && c.lon != null
          return (
            <button key={c.number} className={`lm-item ${fresh.has(c.number) ? 'fresh' : ''}`} onClick={() => onPick(c)} disabled={!can} title={can ? 'Show on map' : 'No location'}>
              <Tile icon={ci.icon} color={ci.color} size={30} />
              <div className="lm-item-main">
                <div className="lm-item-top"><span className="uid">{c.number}</span><span className={`pill ${statusClass(c.status)}`}>{statusText(c.status)}</span></div>
                <div className="note">
                  {c.area || 'Area not known'}
                  {s && <span className="lm-src"><s.icon size={12} weight="bold" />{s.text}</span>}
                </div>
              </div>
              <span className="note num">{timeAgo(c.created_at)}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ---------- page ---------- */
export default function LiveMap() {
  const tile = useTileUrl()
  const [mode, setMode] = useState<Mode>('zones')
  const [zones, setZones] = useState<Zones | null>(null)
  const [sum, setSum] = useState<PublicSummary | null>(null)
  const [defects, setDefects] = useState<Defect[]>([])
  const [items, setItems] = useState<PublicComplaint[]>([])
  const [loading, setLoading] = useState(true)
  const [mapErr, setMapErr] = useState(false)
  const [cErr, setCErr] = useState(false)
  const [fly, setFly] = useState<Fly | null>(null)
  const [pulse, setPulse] = useState<{ lat: number; lon: number; key: number } | null>(null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())
  const [sel, setSel] = useState<number | null>(null)
  const seen = useRef<Set<string> | null>(null)
  const [, tick] = useState(0)

  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [plan, setPlan] = useState<RoutePlan | null>(null)
  const [selected, setSelected] = useState(0)
  const [rLoading, setRLoading] = useState(false)
  const [rErr, setRErr] = useState('')
  const [note, setNote] = useState('')
  const lastQ = useRef<[string, string] | null>(null)
  const planRef = useRef<RoutePlan | null>(null)
  planRef.current = plan
  const [fitRoute, setFitRoute] = useState<L.LatLngBoundsExpression | null>(null)
  const [fitZones, setFitZones] = useState<L.LatLngBoundsExpression | null>(null)
  const fittedZones = useRef(false)

  const load = useCallback(() => {
    pub.zones(300).then((z) => {
      setZones(z)
      setMapErr(false)
      if (!fittedZones.current && z.cells.length) {
        fittedZones.current = true
        setFitZones(L.latLngBounds(z.cells.map((c) => [c.lat, c.lon] as [number, number])))
      }
    }).catch(() => setMapErr(true))
    pub.summary().then(setSum).catch(() => {})
    api.defects().then((d) => setDefects(d.filter((x) => x.status === 'active'))).catch(() => {})
    pub.complaints(40).then((rows) => {
      setCErr(false)
      if (seen.current) {
        const added = rows.filter((r) => !seen.current!.has(r.number)).map((r) => r.number)
        if (added.length) {
          setFresh(new Set(added))
          setTimeout(() => setFresh(new Set()), 5000)
        }
      }
      seen.current = new Set(rows.map((r) => r.number))
      setItems(rows)
    }).catch(() => setCErr(true)).finally(() => setLoading(false))
  }, [])
  useEffect(load, [load])
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 30000)
    return () => clearInterval(t)
  }, [])

  const runPlan = useCallback(async (quiet: boolean) => {
    const q = quiet ? lastQ.current : ([from.trim(), to.trim()] as [string, string])
    if (!q) return
    if (!quiet) {
      lastQ.current = q
      setRLoading(true)
      setRErr('')
      setNote('')
    }
    try {
      const p = await routes.plan(q[0], q[1])
      const old = planRef.current
      if (quiet && old) {
        const sig = (x: RoutePlan) => x.routes.map((r) => `${r.index}:${r.defect_count}`).join('|')
        const changed = recChanged(old, p)
        if (changed) setNote('A new report changed the best route')
        else if (sig(old) !== sig(p)) setNote('A new report was added along these routes')
        setSelected((cur) => (changed ? p.recommended : p.routes.some((r) => r.index === cur) ? cur : p.recommended))
      } else {
        setSelected(p.recommended)
        const rec = p.routes.find((r) => r.index === p.recommended)
        setFitRoute(L.latLngBounds([[p.origin.lat, p.origin.lon], [p.destination.lat, p.destination.lon], ...(rec?.geometry ?? [])]))
      }
      setPlan(p)
    } catch (e: any) {
      if (!quiet) {
        setPlan(null)
        const m = String(e?.message || '').trim()
        setRErr(/not found|geocod|resolve|could not|unknown/i.test(m) ? `${m}. Try a fuller place name, or type coordinates like 12.97, 77.59.` : m || 'The route could not be planned. Try again in a moment.')
      }
    } finally {
      if (!quiet) setRLoading(false)
    }
  }, [from, to])

  useLiveRefresh(LIVE_PREFIXES, () => {
    load()
    if (planRef.current) runPlan(true)
  })

  const route = plan?.routes.find((r) => r.index === selected) ?? null
  const others = plan?.routes.filter((r) => r.index !== selected) ?? []
  const showZones = mode !== 'defects'
  const showDefects = mode !== 'zones'
  const cells = useMemo(() => zones?.cells ?? [], [zones])

  const pick = (c: PublicComplaint) => {
    if (c.lat == null || c.lon == null) return
    const key = Date.now()
    setFly({ lat: c.lat, lon: c.lon, zoom: 17, key })
    setPulse({ lat: c.lat, lon: c.lon, key })
    setTimeout(() => setPulse((x) => (x && x.key === key ? null : x)), 6000)
  }

  return (
    <div className="lm">
      <div className="lm-mapcol">
        <MapContainer center={DEFAULT_CENTER} zoom={13} style={{ height: '100%', width: '100%' }}>
          <TileLayer key={tile} url={tile} attribution={ATTR} maxNativeZoom={16} maxZoom={19} />
          <Controller fly={fly} fit={fitRoute ?? fitZones} />

          {showZones && cells.map((c, i) => (
            <Rectangle key={`z${i}-${c.lat}-${c.lon}`} bounds={cellBounds(c)} pathOptions={{ color: LEVEL_HEX[c.level], weight: 1.5, opacity: 0.8, fillColor: LEVEL_HEX[c.level], fillOpacity: 0.35 }}>
              <Tooltip sticky>{c.label || `${LEVEL_WORD[c.level]}: ${c.count} defects`}</Tooltip>
            </Rectangle>
          ))}
          {showZones && cells.map((c, i) => <Marker key={`n${i}-${c.lat}-${c.lon}`} position={[c.lat, c.lon]} icon={countIcon(c.count, c.level)} interactive={false} keyboard={false} />)}

          {showDefects && defects.filter((d) => d.lat != null && d.lon != null).map((d) => (
            <Marker key={d.id} position={[d.lat!, d.lon!]} icon={defectIcon(d)} eventHandlers={{ click: () => setSel(d.id) }}>
              <Popup><b>{d.uid}</b> {label(d.class_name)}<br />Risk {Math.round(d.risk_score)}, {d.severity?.toLowerCase()} severity</Popup>
            </Marker>
          ))}

          {others.map((r) => (
            <Polyline key={`o${r.index}`} positions={r.geometry} pathOptions={{ color: '#8a9097', weight: 6, opacity: 0.8 }} eventHandlers={{ click: () => setSelected(r.index) }} />
          ))}
          {route && (
            <>
              <Polyline positions={route.geometry} pathOptions={{ color: '#ffffff', weight: 10, opacity: 0.9 }} interactive={false} />
              <Polyline positions={route.geometry} pathOptions={{ color: route.index === plan!.recommended ? '#2e9a57' : '#5d636b', weight: 6, opacity: 1 }} interactive={false} />
              {route.defects.map((d, i) => (
                <Marker key={d.uid} position={[d.lat, d.lon]} icon={routeDotIcon(i + 1, /severe|critical/i.test(d.severity))} zIndexOffset={500}>
                  <Popup><b>{d.uid}</b> {label(d.class)}<br />{d.severity}, risk {Math.round(d.risk)}<br />About {d.penalty_min.toFixed(1)} min of slow driving</Popup>
                </Marker>
              ))}
            </>
          )}
          {plan && <Marker position={[plan.origin.lat, plan.origin.lon]} icon={endIcon('start')} zIndexOffset={800}><Tooltip>{plan.origin.name || 'Start'}</Tooltip></Marker>}
          {plan && <Marker position={[plan.destination.lat, plan.destination.lon]} icon={endIcon('end')} zIndexOffset={800}><Tooltip>{plan.destination.name || 'Destination'}</Tooltip></Marker>}
          {pulse && <Marker position={[pulse.lat, pulse.lon]} icon={pulseIcon} interactive={false} zIndexOffset={900} />}
        </MapContainer>

        <div className="lm-overlay">
          <div className="glass lm-title">
            <h1>Live map</h1>
            <p>Where road damage is clustering and which complaints just came in.</p>
          </div>
          <div className="glass lm-mode seg" role="group" aria-label="Map layers">
            {([['zones', 'Zones'], ['defects', 'Individual defects'], ['both', 'Both']] as const).map(([k, t]) => (
              <button key={k} className={mode === k ? 'on' : ''} onClick={() => setMode(k)} aria-pressed={mode === k}>{t}</button>
            ))}
          </div>
        </div>
        <div className="glass lm-legend-wrap"><Legend /></div>
      </div>

      <aside className="lm-side">
        <SummaryCard sum={sum} zones={zones} err={mapErr} onRetry={load} />
        <RoutePanel
          plan={plan}
          clear={() => { setPlan(null); setNote(''); setRErr(''); setFitRoute(null) }}
          selected={selected}
          setSelected={setSelected}
          note={note}
          doPlan={() => runPlan(false)}
          loading={rLoading}
          err={rErr}
          from={from}
          to={to}
          setFrom={setFrom}
          setTo={setTo}
        />
        <Feed items={items} loading={loading} err={cErr} fresh={fresh} onPick={pick} />
      </aside>
      {sel != null && <DefectDrawer id={sel} onClose={() => setSel(null)} />}
    </div>
  )
}
