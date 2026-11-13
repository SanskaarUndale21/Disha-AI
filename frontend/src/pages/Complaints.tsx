import { useEffect, useState } from 'react'
import { api, fmtDate, label } from '../api'
import { DefectMap, Pill } from '../components'
import { useLiveRefresh } from '../events'
import { useAuth } from '../auth'

const STATUSES = ['submitted', 'in_review', 'in_progress', 'resolved', 'rejected']
const STATUS_COL: Record<string, string> = {
  submitted: '#0a84ff', in_review: '#bf5af2', in_progress: '#ff9f0a', resolved: '#30d158', rejected: '#8b8f99',
}
const NEXT: Record<string, string[]> = {
  submitted: ['in_review', 'rejected'],
  in_review: ['in_progress', 'rejected'],
  in_progress: ['resolved'],
  resolved: ['in_progress'],
  rejected: ['in_review'],
}

export function StatusPill({ s }: { s: string }) {
  return <span className="pill" style={{ background: STATUS_COL[s] + '26', color: STATUS_COL[s], borderColor: 'transparent' }}>{s.replace('_', ' ')}</span>
}

export default function Complaints() {
  const { isOfficer } = useAuth()
  const [rows, setRows] = useState<any[]>([])
  const [status, setStatus] = useState('')
  const [sel, setSel] = useState<any>(null)
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')
  const load = () =>
    api.complaints(status ? `?status=${status}` : '').then((r) => {
      setRows(r)
      if (sel) setSel(r.find((x: any) => x.id === sel.id) ?? null)
    }).catch((e) => setErr(e.message))
  useEffect(() => {
    load()
  }, [status])
  useLiveRefresh(['complaint.', 'inspection.'], load)

  const open = (c: any) => {
    setSel(c)
    setNote(c.admin_note ?? '')
  }
  const move = async (st: string) => {
    setErr('')
    try {
      await api.patchComplaint(sel.id, { status: st, admin_note: note || undefined })
      load()
    } catch (e: any) {
      setErr(e.message)
    }
  }
  const counts = STATUSES.map((s) => [s, rows.filter((r) => r.status === s).length] as const)
  const geo = rows.filter((r) => r.lat != null).map((r) => ({
    id: r.id, uid: r.ticket, class_name: r.category, lat: r.lat, lon: r.lon, risk_level: r.findings?.some((f: any) => f.risk_level === 'High') ? 'High' : r.findings?.length ? 'Medium' : 'Low',
    risk_score: 0, severity: '', status: r.status === 'resolved' ? 'repaired' : 'active', trend: r.status, report_count: 1,
  })) as any

  return (
    <>
      <div className="page-h">
        <div>
          <h1>Citizen complaints</h1>
          <p>Reports from the citizen app and web portal, auto-analysed by the AI. Updates reach the citizen instantly.</p>
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">all statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
        </select>
      </div>
      <div className="grid g4" style={{ gridTemplateColumns: 'repeat(5, minmax(0,1fr))', marginBottom: 14 }}>
        {counts.map(([s, n]) => (
          <div key={s} className="card kpi" style={{ borderTop: `3px solid ${STATUS_COL[s]}`, cursor: 'pointer' }} onClick={() => setStatus(s)}>
            <div className="l">{s.replace('_', ' ')}</div>
            <div className="v">{n}</div>
          </div>
        ))}
      </div>
      {err && <div className="err" style={{ marginBottom: 10 }}>{err}</div>}
      <div className="grid g-wide">
        <div className="card scroll-x">
          <table className="t">
            <thead><tr><th>Ticket</th><th>Category</th><th>Description</th><th>Citizen</th><th>AI findings</th><th>Status</th><th>Filed</th></tr></thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className={`click ${sel?.id === c.id ? 'selrow' : ''}`} onClick={() => open(c)}>
                  <td><span className="uid">{c.ticket}</span></td>
                  <td>{c.category}</td>
                  <td style={{ maxWidth: 260 }}>{(c.description ?? '').slice(0, 80)}</td>
                  <td>{c.citizen_name ?? c.citizen_phone ?? 'anonymous'}</td>
                  <td>{c.findings?.length ? c.findings.map((f: any, i: number) => <Pill key={i} v={f.severity} />) : <span className="muted">{c.media?.some((m: any) => m.status !== 'done' && m.status !== 'stored') ? 'analysing...' : 'none'}</span>}</td>
                  <td><StatusPill s={c.status} /></td>
                  <td className="note">{fmtDate(c.created_at)}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={7} className="muted">No complaints yet.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="grid" style={{ alignContent: 'start' }}>
          {sel ? (
            <div className="card grid" style={{ gap: 10 }}>
              <div className="row">
                <span className="uid" style={{ fontSize: 15 }}>{sel.ticket}</span>
                <StatusPill s={sel.status} />
                <span className="spacer" />
                <button className="btn sm" onClick={() => setSel(null)}>Close</button>
              </div>
              <div><b>{sel.category}</b>, <span className="muted">{fmtDate(sel.created_at)}</span></div>
              <div>{sel.description}</div>
              <div className="note">
                {sel.citizen_name ?? 'Anonymous'} {sel.citizen_phone && `· ${sel.citizen_phone}`}
                {sel.address && <><br />{sel.address}</>}
                {sel.lat != null && <><br /><span className="mono">{sel.lat.toFixed(5)}, {sel.lon.toFixed(5)}</span></>}
              </div>
              <div className="grid g2">
                {sel.media?.map((m: any) => (
                  <div key={m.id}>
                    {m.annotated_url ? (
                      m.media_type === 'video' ? <video className="media" src={m.annotated_url} controls muted /> : <img className="media" src={m.annotated_url} />
                    ) : (
                      <div className="card muted">{m.status}{m.progress ? ` ${Math.round(m.progress * 100)}%` : ''}</div>
                    )}
                  </div>
                ))}
              </div>
              {sel.findings?.length > 0 && (
                <div className="row">
                  {sel.findings.map((f: any, i: number) => (
                    <span key={i} className="pill">{f.defect_uid} {label(f.class_name)}, {f.severity}, {f.risk_level} risk</span>
                  ))}
                </div>
              )}
              <label className="f">Note to citizen<textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Repair crew scheduled this week" /></label>
              {isOfficer ? (
                <div className="row">
                  {(NEXT[sel.status] ?? []).map((st) => (
                    <button key={st} className={`btn sm ${st === 'rejected' ? 'bad' : st === 'resolved' ? 'ok' : 'primary'}`} onClick={() => move(st)}>
                      Move to {st.replace('_', ' ')}
                    </button>
                  ))}
                  <button className="btn sm" onClick={() => move(sel.status)}>Save note</button>
                </div>
              ) : <div className="note">Sign in as an officer to update complaints.</div>}
            </div>
          ) : (
            <div className="card">
              <h3>Complaint map</h3>
              <DefectMap defects={geo} className="map sm" onSelect={(d: any) => open(rows.find((r) => r.id === d.id))} />
              <p className="note">Select a complaint to review the citizen's photos, AI findings and update its status.</p>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
