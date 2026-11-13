import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChatCircleText, CheckCircle, FilePdf, Images, MapPin, SealCheck, Siren, VideoCamera, Warning, DownloadSimple,
} from '@phosphor-icons/react'
import { api, label, pub, type Defect, type PublicSummary } from '../api'
import { DefectDrawer, DefectMap } from '../components'
import { useLiveRefresh, useRealtime, type RtEvent } from '../events'
import { CLASS_HEX, RISK_HEX, Tile } from '../icons'

const EVENT_UI: Record<string, { icon: any; color: string; title: (d: any) => string; sub: (d: any) => string }> = {
  'complaint.created': { icon: ChatCircleText, color: '#f2cc8f', title: (d) => `Complaint ${d.ticket ?? ''}`, sub: (d) => d.category ?? 'New report from a citizen' },
  'complaint.updated': { icon: ChatCircleText, color: '#f2cc8f', title: (d) => `Complaint ${d.ticket ?? ''}`, sub: (d) => `Moved to ${String(d.status ?? '').replace('_', ' ')}` },
  'defect.created': { icon: Warning, color: '#e07a5f', title: (d) => `${d.uid} detected`, sub: (d) => `${label(d.class_name ?? '')}, ${d.severity} severity` },
  'defect.updated': { icon: MapPin, color: '#8e91b0', title: (d) => `${d.uid} updated`, sub: (d) => (d.status ? `Status ${d.status}` : 'Seen again by a new inspection') },
  'detection.verified': { icon: SealCheck, color: '#81b29a', title: (d) => `${d.uid} ${d.verification}`, sub: (d) => `By ${d.by ?? 'officer'}` },
  'inspection.processed': { icon: Images, color: '#b3b6d6', title: (d) => `Inspection ${d.id} analysed`, sub: (d) => `${d.summary?.total ?? 0} findings` },
  'screening.checked': { icon: SealCheck, color: '#f2cc8f', title: (d) => (d.verdict === 'pass' ? 'Citizen photo passed AI check' : d.verdict === 'rate_limited' ? 'Device blocked for fake reports' : 'Citizen photo refused'), sub: (d) => d.reason ?? '' },
  'emergency.fall': { icon: Siren, color: '#e07a5f', title: () => 'Emergency: fall near pothole', sub: (d) => d.message ?? `Pothole PH ${d.pothole_id ?? ''}` },
  'repair.verified': { icon: CheckCircle, color: '#81b29a', title: (d) => `${d.uid} repaired`, sub: (d) => `${d.passes} drives saw clean road` },
  'live.saved': { icon: VideoCamera, color: '#e07a5f', title: () => 'Live patrol saved', sub: (d) => `${d.defects} defects, ${d.new} new` },
}

function ago(iso?: string) {
  if (!iso) return ''
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'now'
  if (s < 3600) return `${Math.floor(s / 60)}m`
  if (s < 86400) return `${Math.floor(s / 3600)}h`
  return `${Math.floor(s / 86400)}d`
}

function FeedRow({ e }: { e: RtEvent }) {
  const ui = EVENT_UI[e.type]
  if (!ui) return null
  return (
    <div className="feed-row">
      <Tile icon={ui.icon} color={ui.color} />
      <div className="feed-txt">
        {ui.title(e.data ?? {})}
        <small>{ui.sub(e.data ?? {})}</small>
      </div>
      <span className="note">{ago(e.ts)}</span>
    </div>
  )
}

export default function Dashboard() {
  const [st, setSt] = useState<any>(null)
  const [defects, setDefects] = useState<Defect[]>([])
  const [sel, setSel] = useState<number | null>(null)
  const [pubSum, setPubSum] = useState<PublicSummary | null>(null)
  const [today, setToday] = useState<number | null>(null)
  const { feed } = useRealtime()
  const load = () => {
    api.stats().then(setSt).catch(() => {})
    api.defects().then(setDefects).catch(() => {})
    pub.summary().then(setPubSum).catch(() => {})
    pub.complaints(100).then((rows) => {
      const d0 = new Date().toDateString()
      const utc = (t: string) => new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(t) ? t : t + 'Z')
      setToday(rows.filter((r) => utc(r.created_at).toDateString() === d0).length)
    }).catch(() => {})
  }
  useEffect(load, [])
  useLiveRefresh(['defect.', 'inspection.', 'detection.', 'live.', 'complaint.'], load)

  const active = defects.filter((d) => d.status === 'active')
  const attention = active.slice(0, 12)
  const byClass = Object.entries(st?.by_class ?? {}) as [string, number][]
  const maxClass = Math.max(1, ...byClass.map(([, v]) => v))
  const events = feed.filter((e) => EVENT_UI[e.type]).slice(0, 12)

  const num = (v: number | null | undefined) => (v == null ? '-' : v)
  const complaints = pubSum?.complaints_today ?? today
  return (
    <div className="dash">
      <section className="hero">
        <div className="hero-top">
          <span className="eyebrow"><span className="dot ok" /> Command centre / live</span>
          <div className="hero-cta">
            <Link className="btn go" to="/live"><VideoCamera size={17} weight="fill" /> Start patrol</Link>
            <a className="btn" href="/api/reports/summary.pdf"><FilePdf size={17} weight="fill" /> Report</a>
            <a className="btn icon" href="/api/reports/defects.csv" title="Export CSV" aria-label="Export CSV"><DownloadSimple size={17} weight="bold" /></a>
          </div>
        </div>
        <h1 className="hero-title">Every road, <span className="hl">seen</span> <em>as it happens.</em></h1>
        <p className="hero-sub">Every patrol, upload and complaint appears here the moment it lands.</p>
        <div className="statstrip">
          <div className="bigstat"><span className="lbl">Open defects</span><span className="num">{num(st?.active)}</span><span className="sub">Unique, merged by location</span></div>
          <div className="bigstat warn"><span className="lbl">Serious</span><span className="num">{num(st?.high_risk)}</span><span className="sub">High risk, act first</span></div>
          <div className="bigstat ok"><span className="lbl">Repaired</span><span className="num">{num(st?.repaired)}</span><span className="sub">Confirmed fixed</span></div>
          <div className="bigstat key"><span className="lbl">Complaints today</span><span className="num">{num(complaints)}</span><span className="sub">From citizens</span></div>
        </div>
        {st && (
          <div className="minirow">
            <span><b>{st.pending_verification}</b>awaiting review</span>
            <span><b>{st.duplicates_prevented}</b>duplicates merged</span>
            {pubSum && (
              <Link to="/map" className="zone-chips" title="Open the live map">
                <span className="zc red"><i /><b>{pubSum.red_zones}</b>red</span>
                <span className="zc yellow"><i /><b>{pubSum.yellow_zones}</b>yellow</span>
                <span className="zc green"><i /><b>{pubSum.green_zones}</b>green</span>
                <span>zones</span>
              </Link>
            )}
          </div>
        )}
      </section>

      <div className="dash-grid">
        <div className="card">
          <div className="card-h"><h3>Live defect map</h3><Link className="btn sm" to="/map">Open full map</Link></div>
          <DefectMap defects={defects.filter((d) => d.status !== 'rejected')} onSelect={(d) => setSel(d.id)} className="map tall" />
          <div className="legend-row">
            {(['High', 'Medium', 'Low'] as const).map((k) => (
              <span key={k}><i style={{ background: RISK_HEX[k] }} />{k} risk</span>
            ))}
            <span><i style={{ background: RISK_HEX.Repaired }} />Repaired</span>
          </div>
          {byClass.length > 0 && (
            <div className="mix">
              <div className="eyebrow" style={{ marginBottom: 6 }}>Open defects by type</div>
              {byClass.map(([k, v]) => (
                <div key={k} className="hbar">
                  <span>{label(k)}</span>
                  <div className="tr"><div style={{ width: `${(v / maxClass) * 100}%`, background: CLASS_HEX[k] }} /></div>
                  <b>{v}</b>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="dash-side">
          <div className="card">
            <div className="card-h"><h3>Needs attention</h3><span className="eyebrow">{active.length} open</span></div>
            <div className="scroll">
              {attention.length === 0 && (
                <div className="empty"><CheckCircle size={30} weight="fill" color="#81b29a" />No open defects. Start a patrol or upload road media to begin.</div>
              )}
              {attention.map((d) => (
                <div key={d.id} className="attn" onClick={() => setSel(d.id)}>
                  {d.crop_url ? <img src={d.crop_url} alt="" /> : <span />}
                  <div style={{ minWidth: 0 }}>
                    <div className="t1">{d.uid}</div>
                    <div className="t2">{label(d.class_name)}, {d.severity.toLowerCase()} severity{d.report_count > 1 ? `, ${d.report_count} reports` : ''}</div>
                  </div>
                  <span className="score" style={{ color: RISK_HEX[d.risk_level] }}>{Math.round(d.risk_score)}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-h"><h3>Activity</h3><span className="eyebrow">Live feed</span></div>
            <div className="scroll">
              {events.length === 0 ? <div className="empty">New detections and complaints will stream in here.</div> : events.map((e, i) => <FeedRow key={i} e={e} />)}
            </div>
          </div>
        </div>
      </div>
      {sel != null && <DefectDrawer id={sel} onClose={() => setSel(null)} onChanged={load} />}
    </div>
  )
}
