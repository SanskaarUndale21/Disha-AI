import { useEffect, useState } from 'react'
import { useLiveRefresh } from '../events'
import { api, CLASSES, fmtDay, label, type Defect } from '../api'
import { DefectDrawer, DefectMap, Pill, Risk, Skeleton, TierPill, Trend } from '../components'

export default function Defects() {
  const [rows, setRows] = useState<Defect[]>([])
  const [f, setF] = useState({ status: 'active', risk: '', cls: '' })
  const [sel, setSel] = useState<number | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [hi, setHi] = useState(false)
  const [view, setView] = useState<'table' | 'map'>('table')
  const load = () => {
    const q = new URLSearchParams(Object.entries(f).filter(([, v]) => v) as any).toString()
    api.defects(q ? `?${q}` : '').then(setRows).finally(() => setLoaded(true))
  }
  useLiveRefresh(['defect.', 'detection.'], () => load())
  useEffect(load, [f])
  const isHigh = (d: Defect) => (d.tier ? d.tier === 'high' : d.confidence != null ? d.confidence >= 0.4 : true)
  const shown = hi ? rows.filter(isHigh) : rows
  const set = (k: string) => (e: any) => setF({ ...f, [k]: e.target.value })
  return (
    <>
      <div className="page-h">
        <div>
          <h1>Defect registry</h1>
          <p>Each row is one unique physical defect. Repeat sightings are merged by location + visual similarity.</p>
        </div>
        <div className="row">
          <select value={f.status} onChange={set('status')}>
            <option value="">all status</option>
            {['active', 'repaired', 'rejected'].map((x) => <option key={x}>{x}</option>)}
          </select>
          <select value={f.risk} onChange={set('risk')}>
            <option value="">all risk</option>
            {['High', 'Medium', 'Low'].map((x) => <option key={x}>{x}</option>)}
          </select>
          <select value={f.cls} onChange={set('cls')}>
            <option value="">all classes</option>
            {CLASSES.map((x) => <option key={x} value={x}>{label(x)}</option>)}
          </select>
          <label className="toggle"><input type="checkbox" checked={hi} onChange={(e) => setHi(e.target.checked)} /> High confidence only</label>
          <button className="btn" onClick={() => setView(view === 'table' ? 'map' : 'table')}>{view === 'table' ? 'Map view' : 'Table view'}</button>
        </div>
      </div>
      {view === 'map' ? (
        <div className="card"><DefectMap defects={shown} onSelect={(d) => setSel(d.id)} className="map" /></div>
      ) : (
        <div className="card scroll-x">
          <table className="t">
            <thead>
              <tr><th></th><th>ID</th><th>Class</th><th>Confidence</th><th>Severity</th><th>Risk</th><th>Trend</th><th>Status</th><th>Reports</th><th>Location</th><th>Last seen</th><th>Verified</th></tr>
            </thead>
            <tbody>
              {shown.map((d) => (
                <tr key={d.id} className="click" onClick={() => setSel(d.id)}>
                  <td>{d.crop_url && <img className="thumb" src={d.crop_url} />}</td>
                  <td><span className="uid">{d.uid}</span></td>
                  <td>{label(d.class_name)}</td>
                  <td>{d.tier || d.confidence != null ? <TierPill tier={d.tier ?? (d.confidence! >= 0.4 ? 'high' : 'possible')} conf={d.confidence} /> : <span className="note">-</span>}</td>
                  <td><Pill v={d.severity} /></td>
                  <td><Risk score={d.risk_score} level={d.risk_level} /></td>
                  <td><Trend t={d.trend} /></td>
                  <td>{d.status}</td>
                  <td className="mono">{d.report_count}</td>
                  <td className="mono note">{d.lat != null ? `${d.lat.toFixed(5)}, ${d.lon!.toFixed(5)}` : 'unknown'}</td>
                  <td>{fmtDay(d.last_seen)}</td>
                  <td>{d.verified ? 'yes' : '-'}</td>
                </tr>
              ))}
              {!loaded && <tr><td colSpan={12}><Skeleton rows={6} /></td></tr>}
              {loaded && shown.length === 0 && <tr><td colSpan={12} className="muted">No defects match.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {sel != null && <DefectDrawer id={sel} onClose={() => setSel(null)} onChanged={load} />}
    </>
  )
}
