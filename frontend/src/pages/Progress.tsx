import { useEffect, useState } from 'react'
import { Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, fmtDate, fmtDay, label, type Defect } from '../api'
import { DefectDrawer, DefectMap, Risk, Trend } from '../components'

export default function Progress() {
  const [all, setAll] = useState<Defect[]>([])
  const [pt, setPt] = useState<[number, number] | null>(null)
  const [radius, setRadius] = useState(50)
  const [res, setRes] = useState<any>(null)
  const [sel, setSel] = useState<number | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    api.defects().then((r) => { setAll(Array.isArray(r) ? r : []); setErr('') }).catch((e) => setErr(e?.message || 'Could not load defects.'))
  }, [])
  useEffect(() => {
    if (pt) api.progress(pt[0], pt[1], radius).then(setRes).catch((e) => setErr(e?.message || 'Could not compare this spot.'))
  }, [pt, radius])
  const changed = all.filter((d) => ['worsening', 'improving', 'repaired', 'stable'].includes(d.trend))
  return (
    <>
      <div className="page-h">
        <div>
          <h1>Repair progress</h1>
          <p>See whether a stretch of road is getting worse, improving or has been fixed, by comparing inspections over time.</p>
        </div>
      </div>
      {err && <div className="err" role="alert" style={{ marginBottom: 14 }}>{err}</div>}
      <div className="grid g-wide">
        <div className="card">
          <div className="row" style={{ marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>Choose a spot on the map</h3>
            <span className="spacer" />
            <label className="row note">radius
              <select value={radius} onChange={(e) => setRadius(+e.target.value)}>
                {[15, 30, 50, 100, 250, 500].map((x) => <option key={x} value={x}>{x} m</option>)}
              </select>
            </label>
          </div>
          <DefectMap defects={all} marker={pt} onClick={(a, b) => setPt([a, b])} onSelect={(d) => setPt([d.lat!, d.lon!])} />
        </div>
        <div className="card" style={{ alignSelf: 'start' }}>
          <h3>Comparison</h3>
          {!res ? (
            <p className="muted">Pick a point on the map.</p>
          ) : (
            <>
              <div className={`verdict trend-${res.verdict === 'unchanged' ? '' : res.verdict}`}>{res.verdict.replace('_', ' ')}</div>
              <p className="note">{res.snapshots.length} inspection(s) within {radius} m. First vs latest compared by defect count and damaged area.</p>
              {res.snapshots.length > 0 && (
                <div style={{ height: 200 }}>
                  <ResponsiveContainer>
                    <ComposedChart data={res.snapshots.map((s: any) => ({ ...s, day: fmtDay(s.date), area: +(s.total_area * 100).toFixed(2) }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                      <XAxis dataKey="day" fontSize={11} />
                      <YAxis yAxisId="l" allowDecimals={false} fontSize={11} />
                      <YAxis yAxisId="r" orientation="right" fontSize={11} />
                      <Tooltip />
                      <Legend />
                      <Bar yAxisId="l" dataKey="count" name="defects" fill="#f2cc8f" />
                      <Line yAxisId="r" dataKey="area" name="damaged area %" stroke="#e07a5f" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}
              <div className="grid g2" style={{ marginTop: 8 }}>
                {res.snapshots.map((s: any) => (
                  <div key={s.inspection_id}>
                    {s.annotated_url && (s.annotated_url.endsWith('.mp4') ? <video className="media" src={s.annotated_url} muted /> : <img className="media" src={s.annotated_url} />)}
                    <div className="note">#{s.inspection_id} {fmtDate(s.date)} | {s.count} defects</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
      <div className="card scroll-x" style={{ marginTop: 14 }}>
        <h3>Defects with change history</h3>
        <table className="t">
          <thead><tr><th>ID</th><th>Class</th><th>Trend</th><th>Risk</th><th>Reports</th><th>First seen</th><th>Last seen</th></tr></thead>
          <tbody>
            {changed.map((d) => (
              <tr key={d.id} className="click" onClick={() => setSel(d.id)}>
                <td><span className="uid">{d.uid}</span></td>
                <td>{label(d.class_name)}</td>
                <td><Trend t={d.trend} /></td>
                <td><Risk score={d.risk_score} level={d.risk_level} /></td>
                <td className="mono">{d.report_count}</td>
                <td>{fmtDay(d.first_seen)}</td>
                <td>{fmtDay(d.last_seen)}</td>
              </tr>
            ))}
            {changed.length === 0 && <tr><td colSpan={7} className="muted">No defect has been re-inspected yet.</td></tr>}
          </tbody>
        </table>
      </div>
      {sel != null && <DefectDrawer id={sel} onClose={() => setSel(null)} />}
    </>
  )
}
