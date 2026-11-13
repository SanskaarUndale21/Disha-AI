import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChatCircleText, CheckCircle, FilePdf, Images, MapPin, SealCheck, Siren, VideoCamera, Warning, DownloadSimple,
} from '@phosphor-icons/react'
import { api, label, type Defect } from '../api'
import { DefectDrawer, DefectMap } from '../components'
import { useLiveRefresh, useRealtime, type RtEvent } from '../events'
import { CLASS_HEX, RISK_HEX, Tile } from '../icons'

const EVENT_UI: Record<string, { icon: any; color: string; title: (d: any) => string; sub: (d: any) => string }> = {
  'complaint.created': { icon: ChatCircleText, color: '#ff9500', title: (d) => `Complaint ${d.ticket ?? ''}`, sub: (d) => d.category ?? 'New report from a citizen' },
  'complaint.updated': { icon: ChatCircleText, color: '#ff9500', title: (d) => `Complaint ${d.ticket ?? ''}`, sub: (d) => `Moved to ${String(d.status ?? '').replace('_', ' ')}` },
  'defect.created': { icon: Warning, color: '#ff3b30', title: (d) => `${d.uid} detected`, sub: (d) => `${label(d.class_name ?? '')}, ${d.severity} severity` },
  'defect.updated': { icon: MapPin, color: '#5856d6', title: (d) => `${d.uid} updated`, sub: (d) => (d.status ? `Status ${d.status}` : 'Seen again by a new inspection') },
  'detection.verified': { icon: SealCheck, color: '#34c759', title: (d) => `${d.uid} ${d.verification}`, sub: (d) => `By ${d.by ?? 'officer'}` },
  'inspection.processed': { icon: Images, color: '#30b0c7', title: (d) => `Inspection ${d.id} analysed`, sub: (d) => `${d.summary?.total ?? 0} findings` },
  'screening.checked': { icon: SealCheck, color: '#dd7a07', title: (d) => (d.verdict === 'pass' ? 'Citizen photo passed AI check' : d.verdict === 'rate_limited' ? 'Device blocked for fake reports' : 'Citizen photo refused'), sub: (d) => d.reason ?? '' },
  'emergency.fall': { icon: Siren, color: '#d92d20', title: () => 'Emergency: fall near pothole', sub: (d) => d.message ?? `Pothole PH ${d.pothole_id ?? ''}` },
  'live.saved': { icon: VideoCamera, color: '#ff3b30', title: () => 'Live patrol saved', sub: (d) => `${d.defects} defects, ${d.new} new` },
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
  const { feed } = useRealtime()
  const load = () => {
    api.stats().then(setSt).catch(() => {})
    api.defects().then(setDefects).catch(() => {})
  }
  useEffect(load, [])
  useLiveRefresh(['defect.', 'inspection.', 'detection.', 'live.', 'complaint.'], load)

  const active = defects.filter((d) => d.status === 'active')
  const attention = active.slice(0, 12)
  const byClass = Object.entries(st?.by_class ?? {}) as [string, number][]
  const maxClass = Math.max(1, ...byClass.map(([, v]) => v))
  const events = feed.filter((e) => EVENT_UI[e.type]).slice(0, 12)

  return (
    <div className="cc">
      <DefectMap defects={defects.filter((d) => d.status !== 'rejected')} onSelect={(d) => setSel(d.id)} className="map-full" />
      <div className="cc-layer">
        <div className="cc-head">
          <div className="glass cc-title">
            <h1>Command center</h1>
            <p>Every patrol, upload and complaint appears here as it happens.</p>
          </div>
          {st && (
            <div className="glass stats">
              <div className="stat"><b>{st.active}</b><span>Open defects</span></div>
              <div className="stat alert"><b>{st.high_risk}</b><span>High risk</span></div>
              <div className="stat"><b>{st.pending_verification}</b><span>Awaiting review</span></div>
              <div className="stat"><b>{st.repaired}</b><span>Repaired</span></div>
              <div className="stat"><b>{st.duplicates_prevented}</b><span>Duplicates merged</span></div>
            </div>
          )}
        </div>

        <div className="cc-side">
          <div className="cc-actions">
            <Link className="btn go" to="/live"><VideoCamera size={17} weight="fill" /> Start patrol</Link>
            <a className="btn" href="/api/reports/summary.pdf"><FilePdf size={17} weight="fill" /> Report</a>
            <a className="btn icon" href="/api/reports/defects.csv" title="Export CSV" aria-label="Export CSV"><DownloadSimple size={17} weight="bold" /></a>
          </div>
          <div className="card grow">
            <h3>Needs attention</h3>
            <div className="scroll">
              {attention.length === 0 && (
                <div className="empty"><CheckCircle size={30} weight="fill" color="#34c759" />No open defects. Start a patrol or upload road media to begin.</div>
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
          <div className="card" style={{ maxHeight: '34%' }}>
            <h3>Activity</h3>
            <div className="scroll">
              {events.length === 0 ? <div className="empty">New detections and complaints will stream in here.</div> : events.map((e, i) => <FeedRow key={i} e={e} />)}
            </div>
          </div>
        </div>

        <div className="cc-bottom">
          <div className="glass legend-glass">
            {(['High', 'Medium', 'Low'] as const).map((k) => (
              <span key={k}><i style={{ background: RISK_HEX[k] }} />{k} risk</span>
            ))}
            <span><i style={{ background: '#007aff' }} />Repaired</span>
          </div>
          {byClass.length > 0 && (
            <div className="glass mini">
              <h4>Open defects by type</h4>
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
      </div>
      {sel != null && <DefectDrawer id={sel} onClose={() => setSel(null)} onChanged={load} />}
    </div>
  )
}
