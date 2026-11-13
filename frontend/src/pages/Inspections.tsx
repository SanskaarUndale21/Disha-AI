import { useEffect, useState } from 'react'
import { useLiveRefresh } from '../events'
import { api, fmtDate, type Inspection } from '../api'
import { InspectionResult } from './Analyze'
import { Skeleton } from '../components'

export default function Inspections() {
  const [rows, setRows] = useState<Inspection[]>([])
  const [open, setOpen] = useState<Inspection | null>(null)
  const [err, setErr] = useState('')
  const [loaded, setLoaded] = useState(false)
  const load = () => api.inspections().then((r) => { setRows(Array.isArray(r) ? r : []); setErr('') }).catch((e) => setErr(e?.message || 'Could not load inspections.')).finally(() => setLoaded(true))
  useLiveRefresh(['inspection.', 'live.'], () => load())
  useEffect(() => {
    load()
  }, [])
  const show = async (id: number) => { try { setOpen(await api.inspection(id)) } catch (e: any) { setErr(e?.message || 'Could not open this inspection.') } }
  const del = async (id: number) => {
    try { await api.deleteInspection(id) } catch (e: any) { setErr(e?.message || 'Could not delete.'); return }
    setOpen(null)
    load()
  }
  return (
    <>
      <div className="page-h">
        <div>
          <h1>Inspections</h1>
          <p>All analysed road samples with date, location source and results.</p>
        </div>
      </div>
      <div className="card scroll-x">
        <table className="t">
          <thead><tr><th></th><th>#</th><th>File</th><th>Type</th><th>Date</th><th>Location</th><th>Road</th><th>Detections</th><th>New</th><th>Dup</th><th></th></tr></thead>
          <tbody>
            {rows.map((i) => (
              <tr key={i.id} className="click" onClick={() => show(i.id)}>
                <td>{i.media_type === 'image' && i.annotated_url && <img className="thumb" src={i.annotated_url} />}</td>
                <td className="mono">{i.id}</td>
                <td>{i.original_name}</td>
                <td>{i.media_type}</td>
                <td>{fmtDate(i.captured_at)}</td>
                <td className="note">{i.lat != null ? `${i.lat.toFixed(5)}, ${i.lon!.toFixed(5)} (${i.location_source})` : 'unknown'}</td>
                <td>{i.road_name ?? '-'} <span className="note">{i.road_type}</span></td>
                <td className="mono">{i.summary?.total ?? '...'}</td>
                <td className="mono">{i.summary?.new_defects ?? '-'}</td>
                <td className="mono">{i.summary?.duplicates ?? '-'}</td>
                <td><a className="btn sm" href={`/api/reports/inspection/${i.id}.pdf`} onClick={(e) => e.stopPropagation()}>PDF</a></td>
              </tr>
            ))}
            {!loaded && <tr><td colSpan={11}><Skeleton rows={5} /></td></tr>}
            {loaded && err && <tr><td colSpan={11}><div className="empty">{err}<button className="btn sm" onClick={load}>Retry</button></div></td></tr>}
            {loaded && !err && rows.length === 0 && <tr><td colSpan={11} className="muted">No inspections yet.</td></tr>}
          </tbody>
        </table>
      </div>
      {open && (
        <>
          <div className="row" style={{ marginTop: 14 }}>
            <span className="spacer" />
            <button className="btn bad sm" onClick={() => del(open.id)}>Delete inspection #{open.id}</button>
            <button className="btn sm" onClick={() => setOpen(null)}>Close</button>
          </div>
          <InspectionResult insp={open} />
        </>
      )}
    </>
  )
}
