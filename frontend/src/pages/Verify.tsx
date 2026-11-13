import { useEffect, useState } from 'react'
import { useLiveRefresh } from '../events'
import { api, CLASSES, fmtDate, label, type Detection } from '../api'
import { Pill, Risk } from '../components'

function Item({ d, onDone }: { d: Detection; onDone: () => void }) {
  const [cls, setCls] = useState(d.final_class)
  const [sev, setSev] = useState(d.final_severity)
  const [note, setNote] = useState(d.verify_note ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const act = async (action: string) => {
    setBusy(true)
    setErr('')
    try {
      const body: any = { action, note, verified_by: 'admin' }
      if (action === 'correct') {
        body.corrected_class = cls !== d.class_name ? cls : null
        body.corrected_severity = sev !== d.severity ? sev : null
        if (!body.corrected_class && !body.corrected_severity) {
          setErr('Change the class or severity to save a correction.')
          setBusy(false)
          return
        }
      }
      await api.verify(d.id, body)
      onDone()
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="card vcard">
      <div className="grid" style={{ gap: 6 }}>
        <img src={d.crop_url ?? ''} title="defect crop" />
        {d.annotated_url && d.media_type === 'image' && <a className="note" href={d.annotated_url} target="_blank">open full frame</a>}
      </div>
      <div className="grid" style={{ gap: 8 }}>
        <div className="row">
          <span className="uid">{d.defect_uid}</span>
          <b>{label(d.class_name)}</b>
          <span className="mono muted">conf {d.confidence.toFixed(2)}</span>
          <Pill v={d.severity} />
          <Risk score={d.risk_score} level={d.risk_level} />
          {d.is_duplicate && <span className="pill dup">repeat sighting</span>}
          <span className="spacer" />
          <span className="note">inspection #{d.inspection_id}{d.track_id != null ? `, track ${d.track_id}` : ''}</span>
        </div>
        {d.verification !== 'pending' && (
          <div className="note">
            {d.verification} by {d.verified_by} at {fmtDate(d.verified_at)}
            {d.corrected_class && ` | class -> ${label(d.corrected_class)}`}
            {d.corrected_severity && ` | severity -> ${d.corrected_severity}`}
          </div>
        )}
        <div className="row">
          <select value={cls} onChange={(e) => setCls(e.target.value)}>
            {CLASSES.map((c) => <option key={c} value={c}>{label(c)}</option>)}
          </select>
          <select value={sev} onChange={(e) => setSev(e.target.value)}>
            {['Low', 'Medium', 'High'].map((x) => <option key={x}>{x}</option>)}
          </select>
          <input style={{ flex: 1, minWidth: 120 }} placeholder="note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="row">
          <button className="btn ok sm" disabled={busy} onClick={() => act('confirm')}>Confirm</button>
          <button className="btn sm" disabled={busy} onClick={() => act('correct')}>Save correction</button>
          <button className="btn bad sm" disabled={busy} onClick={() => act('reject')}>Reject (false positive)</button>
          {d.verification !== 'pending' && <button className="btn sm" disabled={busy} onClick={() => act('reset')}>Reset</button>}
        </div>
        {err && <div className="err">{err}</div>}
      </div>
    </div>
  )
}

export default function Verify() {
  const [status, setStatus] = useState('pending')
  const [rows, setRows] = useState<Detection[]>([])
  const load = () => api.queue(status).then(setRows)
  useLiveRefresh(['inspection.', 'detection.', 'defect.'], () => load())
  useEffect(() => {
    load()
  }, [status])
  return (
    <>
      <div className="page-h">
        <div>
          <h1>Manual verification</h1>
          <p>Confirm, reject or correct AI detections. Verified labels are exported in YOLO format for re-training.</p>
        </div>
        <div className="row">
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {['pending', 'confirmed', 'corrected', 'rejected', 'all'].map((x) => <option key={x}>{x}</option>)}
          </select>
          <a className="btn" href="/api/training/export">Export verified labels (YOLO)</a>
        </div>
      </div>
      <div className="grid">
        {rows.map((d) => <Item key={`${d.id}-${d.verification}`} d={d} onDone={load} />)}
        {rows.length === 0 && <div className="card muted">Queue is empty.</div>}
      </div>
    </>
  )
}
