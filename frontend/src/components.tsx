import { useEffect, useState } from 'react'
import { MapContainer, Marker, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { MeasurePanel } from './measure'
import { RoadRecord } from './roadrecord'
import { api, fmtDate, fmtDay, inr, label, ops, reportUrl, type CostRow, type Defect } from './api'

const RISK_HEX: Record<string, string> = { High: '#ff3b30', Medium: '#ff9500', Low: '#34c759' }

/** Apple Maps-style marker: white-ringed disc in the risk colour, sized by reports, halo when high risk. */
function pinIcon(d: Defect) {
  const col = d.status === 'repaired' ? '#007aff' : RISK_HEX[d.risk_level] ?? '#8e8e93'
  const size = 18 + Math.min(10, (d.report_count - 1) * 3)
  const halo = d.status !== 'repaired' && d.risk_level === 'High'
  return L.divIcon({
    className: '',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div class="rw-pin${halo ? ' halo' : ''}" style="--c:${col};width:${size}px;height:${size}px"></div>`,
  })
}

// default marker icon fix for bundlers
const pin = L.divIcon({
  className: '',
  html: '<div style="width:18px;height:18px;border-radius:50% 50% 50% 0;background:#f5b100;border:2px solid #111;transform:rotate(-45deg)"></div>',
  iconSize: [18, 18],
  iconAnchor: [9, 18],
})

export const DEFAULT_CENTER: [number, number] = [12.9716, 77.5946]
const TILE_LIGHT = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}'
const TILE_DARK = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'
const isDark = () => {
  const t = document.documentElement.getAttribute('data-theme')
  return t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
}
/** Basemap that follows the app's light / dark appearance. */
export function useTileUrl() {
  const [dark, setDark] = useState(isDark())
  useEffect(() => {
    const f = () => setDark(isDark())
    window.addEventListener('rw-theme', f)
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', f)
    return () => {
      window.removeEventListener('rw-theme', f)
      mq.removeEventListener('change', f)
    }
  }, [])
  return dark ? TILE_DARK : TILE_LIGHT
}
const ATTR = 'Tiles &copy; Esri, HERE, Garmin, &copy; OpenStreetMap contributors'

export function Pill({ v, kind }: { v: string | null | undefined; kind?: string }) {
  if (!v) return <span className="muted">-</span>
  return <span className={`pill ${kind ?? v}`}>{v}</span>
}

export function Risk({ score, level }: { score: number; level: string }) {
  return (
    <span className={`pill ${level}`}>
      <span className="mono">{Math.round(score ?? 0)}</span> {level}
    </span>
  )
}

export function Trend({ t }: { t: string }) {
  return <span className={`trend-${t}`}>{t}</span>
}

function FitBounds({ pts }: { pts: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (pts.length === 1) map.setView(pts[0], 15)
    else if (pts.length > 1) map.fitBounds(L.latLngBounds(pts), { padding: [60, 60], maxZoom: 15 })
  }, [JSON.stringify(pts)])
  return null
}

export function DefectMap({
  defects,
  onSelect,
  className = 'map',
  onClick,
  marker,
}: {
  defects: Defect[]
  onSelect?: (d: Defect) => void
  className?: string
  onClick?: (lat: number, lon: number) => void
  marker?: [number, number] | null
}) {
  const tile = useTileUrl()
  const geo = defects.filter((d) => d.lat != null && d.lon != null)
  const pts = geo.map((d) => [d.lat!, d.lon!] as [number, number])
  return (
    <div className={className}>
      <MapContainer center={pts[0] ?? DEFAULT_CENTER} zoom={13} style={{ height: '100%', width: '100%' }}>
        <TileLayer key={tile} url={tile} attribution={ATTR} maxNativeZoom={16} maxZoom={19} />
        <FitBounds pts={marker ? [marker] : pts} />
        {onClick && <ClickCatcher onClick={onClick} />}
        {marker && <Marker position={marker} icon={pin} />}
        {geo.map((d) => (
          <Marker
            key={d.id}
            position={[d.lat!, d.lon!]}
            icon={pinIcon(d)}
            eventHandlers={onSelect ? { click: () => onSelect(d) } : undefined}
          >
            <Popup>
              <b>{d.uid}</b> {label(d.class_name)}
              <br />
              Risk {Math.round(d.risk_score)}, {d.severity?.toLowerCase()} severity
              <br />
              {d.report_count} report{d.report_count === 1 ? '' : 's'}, {d.status}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}

function ClickCatcher({ onClick }: { onClick: (lat: number, lon: number) => void }) {
  useMapEvents({ click: (e) => onClick(e.latlng.lat, e.latlng.lng) })
  return null
}

export function LocationPicker({
  value,
  onChange,
}: {
  value: [number, number] | null
  onChange: (v: [number, number] | null) => void
}) {
  const tile = useTileUrl()
  return (
    <div className="map sm">
      <MapContainer center={value ?? DEFAULT_CENTER} zoom={value ? 16 : 12} style={{ height: '100%', width: '100%' }}>
        <TileLayer key={tile} url={tile} attribution={ATTR} maxNativeZoom={16} maxZoom={19} />
        <ClickCatcher onClick={(a, b) => onChange([a, b])} />
        {value && <Marker position={value} icon={pin} />}
      </MapContainer>
    </div>
  )
}

export function DefectDrawer({ id, onClose, onChanged }: { id: number; onClose: () => void; onChanged?: () => void }) {
  const [d, setD] = useState<Defect | null>(null)
  const load = () => api.defect(id).then(setD)
  useEffect(() => {
    load()
  }, [id])
  const patch = async (body: any) => {
    await api.patchDefect(id, body)
    await load()
    onChanged?.()
  }
  const [cost, setCost] = useState<CostRow | null>(null)
  const [mail, setMail] = useState<{ to: string; subject: string; body: string } | null>(null)
  const [mailErr, setMailErr] = useState('')
  const [sending, setSending] = useState(false)
  const [showMeasure, setShowMeasure] = useState(false)
  useEffect(() => {
    setShowMeasure(false)
    setCost(null)
    setMail(null)
    setMailErr('')
    ops
      .costs('active')
      .then((rows) => setCost((Array.isArray(rows) ? rows : []).find((r) => r.defect_id === id) ?? null))
      .catch(() => {})
  }, [id])
  const sendMail = async () => {
    setSending(true)
    setMailErr('')
    try {
      setMail(await ops.send(id))
    } catch (e: any) {
      setMailErr(e?.message || 'Could not prepare the message')
    } finally {
      setSending(false)
    }
  }
  return (
    <div className="drawer-bg" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        {!d ? (
          <div className="skel-stack" aria-busy="true"><i className="skel" style={{ width: '45%', height: 24 }} /><i className="skel" style={{ width: '100%', height: 180 }} /><i className="skel" style={{ width: '80%' }} /><i className="skel" style={{ width: '65%' }} /></div>
        ) : (
          <div className="grid">
            <div className="row">
              <span className="uid" style={{ fontSize: 16 }}>{d.uid}</span>
              <b style={{ fontSize: 18 }}>{label(d.class_name)}</b>
              <span className="spacer" />
              <button className="btn sm" onClick={onClose}>Close</button>
            </div>
            {d.crop_url && <img src={d.crop_url} className="media" style={{ maxHeight: 260 }} />}
            <div className="grid g3">
              <div className="card kpi"><div className="l">Risk</div><Risk score={d.risk_score} level={d.risk_level} /></div>
              <div className="card kpi"><div className="l">Severity</div><Pill v={d.severity} /></div>
              <div className="card kpi"><div className="l">Trend</div><Trend t={d.trend} /></div>
            </div>
            {cost && (
              <div className="card dd-cost">
                <div>
                  <div className="note">Estimated repair cost</div>
                  <div className="dd-cost-v">{inr(cost.total_cost)}</div>
                </div>
                <div className="dd-cost-parts note">
                  <span>Material {inr(cost.material_cost)}</span>
                  <span>Labour {inr(cost.labour_cost)}</span>
                  <span>Traffic {inr(cost.traffic_cost)}</span>
                  {cost.material && <span>{cost.material}</span>}
                </div>
              </div>
            )}
            <div className="dd-actions">
              <a className="btn sm" href={reportUrl('complaint', d.id)} target="_blank" rel="noreferrer">Complaint PDF</a>
              <a className="btn sm" href={reportUrl('authority', d.id)} target="_blank" rel="noreferrer">Authority report</a>
            <a className="btn sm" href={reportUrl('evidence', d.id)} target="_blank" rel="noreferrer">Evidence record</a>
              <span className="spacer" />
              <button className="btn sm primary" disabled={sending} onClick={sendMail}>{sending ? 'Preparing...' : 'Send to roads department'}</button>
            </div>
            {d.class_name === 'pothole' && (
              <div className="card ms-card">
                <div className="row">
                  <b>Size and depth</b>
                  <span className="spacer" />
                  {!showMeasure && <button className="btn sm" onClick={() => setShowMeasure(true)}>Measure size and depth</button>}
                </div>
                {showMeasure && <div style={{ marginTop: 10 }}><MeasurePanel defectId={d.id} /></div>}
              </div>
            )}
            {mailErr && <div className="err">Could not send. {mailErr}</div>}
            {mail && (
              <div className="dd-mail">
                <div className="row">
                  <b>Message preview</b>
                  <span className="pill">Mock</span>
                  <span className="spacer" />
                  <button className="btn sm" onClick={() => setMail(null)}>Hide</button>
                </div>
                <div className="note">This is a mock. No real email is sent.</div>
                <div className="dd-mail-h"><span className="muted">To</span> {mail.to}</div>
                <div className="dd-mail-h"><span className="muted">Subject</span> {mail.subject}</div>
                <pre className="dd-mail-b">{mail.body}</pre>
              </div>
            )}
            <div className="card">
              <table className="t">
                <tbody>
                  <tr><td className="muted">Status</td><td>{d.status}</td></tr>
                  <tr><td className="muted">Reports</td><td>{d.report_count}</td></tr>
                  <tr><td className="muted">Location</td><td className="mono">{d.lat != null ? `${d.lat.toFixed(6)}, ${d.lon!.toFixed(6)} (${d.location_source})` : 'unknown'}</td></tr>
                  <tr><td className="muted">Road</td><td>{d.road_type}, traffic {d.traffic_level}</td></tr>
                  <tr><td className="muted">First / last seen</td><td>{fmtDate(d.first_seen)} / {fmtDate(d.last_seen)}</td></tr>
                  <tr><td className="muted">Verified</td><td>{d.verified ? 'yes' : 'no'}</td></tr>
                </tbody>
              </table>
              <div className="row" style={{ marginTop: 12 }}>
                <select value={d.road_type} onChange={(e) => patch({ road_type: e.target.value })}>
                  {['unknown', 'highway', 'arterial', 'collector', 'local'].map((x) => <option key={x}>{x}</option>)}
                </select>
                <select value={d.traffic_level} onChange={(e) => patch({ traffic_level: e.target.value })}>
                  {['unknown', 'high', 'medium', 'low'].map((x) => <option key={x}>{x}</option>)}
                </select>
                <span className="spacer" />
                {d.status !== 'repaired' ? (
                  <button className="btn sm" onClick={() => patch({ status: 'repaired' })}>Mark repaired</button>
                ) : (
                  <button className="btn sm" onClick={() => patch({ status: 'active' })}>Reopen</button>
                )}
              </div>
            </div>
            <RoadRecord defectId={d.id} lat={d.lat} lon={d.lon} />
            {d.history && d.history.length > 0 && (
              <div className="card">
                <h3>Progress timeline</h3>
                <div style={{ height: 180 }}>
                  <ResponsiveContainer>
                    <LineChart data={d.history.map((h) => ({ ...h, day: fmtDay(h.observed_at), sev: h.severity_score ?? 0 }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                      <XAxis dataKey="day" fontSize={11} />
                      <YAxis domain={[0, 1]} fontSize={11} />
                      <Tooltip />
                      <Line type="monotone" dataKey="sev" name="severity score" stroke="#f5b100" strokeWidth={2} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <table className="t">
                  <thead><tr><th>Date</th><th>Seen</th><th>Severity</th><th>Risk</th><th>Trend</th></tr></thead>
                  <tbody>
                    {d.history.map((h, i) => (
                      <tr key={i}>
                        <td>{fmtDate(h.observed_at)}</td>
                        <td>{h.present ? 'yes' : 'not found'}</td>
                        <td>{h.severity ?? '-'} {h.severity_score != null && <span className="muted mono">({h.severity_score.toFixed(2)})</span>}</td>
                        <td className="mono">{h.risk_score != null ? Math.round(h.risk_score) : '-'}</td>
                        <td><Trend t={h.trend} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="card">
              <h3>Observations ({d.detections?.length})</h3>
              <table className="t">
                <thead><tr><th></th><th>Inspection</th><th>Conf</th><th>Dup match</th><th>Verification</th></tr></thead>
                <tbody>
                  {d.detections?.map((x) => (
                    <tr key={x.id}>
                      <td>{x.crop_url && <img src={x.crop_url} className="thumb" />}</td>
                      <td>#{x.inspection_id}{x.track_id != null && <span className="muted"> track {x.track_id}</span>}</td>
                      <td className="mono">{x.confidence.toFixed(2)}</td>
                      <td className="mono">{x.is_duplicate ? `sim ${x.match_score?.toFixed(2)}${x.match_distance_m != null ? `, ${x.match_distance_m} m` : ''}` : 'first report'}</td>
                      <td>{x.verification}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export function Skeleton({ rows = 5, h = 46 }: { rows?: number; h?: number }) {
  return (
    <div className="skel-list" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <span key={i} className="skel" style={{ height: h }} />)}
    </div>
  )
}

export function TierPill({ tier, conf }: { tier: 'high' | 'possible'; conf?: number | null }) {
  const pct = conf != null ? ` ${Math.round(conf * 100)}%` : ''
  return <span className={`pill tier ${tier}`}>{tier === 'high' ? 'High confidence' : 'Possible'}{pct}</span>
}
