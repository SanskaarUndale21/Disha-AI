import { useRef, useState } from 'react'
import { api, label, type Inspection } from '../api'
import { DefectDrawer, LocationPicker, Pill, Risk } from '../components'
import { MeasurePanel } from '../measure'

export function InspectionResult({ insp, file }: { insp: Inspection; file?: File | null }) {
  const [sel, setSel] = useState<number | null>(null)
  const [measure, setMeasure] = useState(false)
  const hasPothole = (insp.detections ?? []).some((d) => d.class_name === 'pothole')
  const s = insp.summary ?? {}
  const dets = insp.detections ?? []
  return (
    <div className="grid g-wide" style={{ marginTop: 14 }}>
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <h3 style={{ margin: 0 }}>Inspection #{insp.id} result</h3>
          <span className="spacer" />
          <a className="btn sm" href={`/api/reports/inspection/${insp.id}.pdf`}>PDF</a>
        </div>
        {insp.media_type !== 'video' ? (
          <img className="media" src={insp.annotated_url ?? ''} />
        ) : (
          <video className="media" src={insp.annotated_url ?? ''} controls autoPlay muted loop />
        )}
        <p className="note">
          {insp.media_type === 'video'
            ? `${insp.frames_processed} frames tracked with ByteTrack, ${s.raw_track_ids ?? 0} raw track IDs filtered to ${s.unique_tracks ?? 0} unique defects. `
            : ''}
          {s.enhanced ? 'Low-light/contrast correction (CLAHE) applied. ' : ''}
          Location: {insp.lat != null ? `${insp.lat.toFixed(6)}, ${insp.lon!.toFixed(6)} via ${insp.location_source}` : 'unknown'}.
          Processed in {insp.processing_ms} ms with {insp.model_name}.
          {insp.duplicate_of_inspection && <b> This exact image was already uploaded as inspection #{insp.duplicate_of_inspection}.</b>}
        </p>
      </div>
      <div className="grid" style={{ alignContent: 'start' }}>
        <div className="grid g3">
          <div className="card kpi"><div className="l">Detected</div><div className="v">{s.total ?? 0}</div></div>
          <div className="card kpi"><div className="l">New defects</div><div className="v">{s.new_defects ?? 0}</div></div>
          <div className="card kpi"><div className="l">Duplicates</div><div className="v">{s.duplicates ?? 0}</div></div>
        </div>
        <div className="card">
          <h3>Counts by category</h3>
          <div className="row">
            {Object.entries(s.by_class ?? {}).map(([k, v]) => (
              <span key={k} className="pill">{label(k)}: {v as number}</span>
            ))}
            {dets.length === 0 && <span className="muted">No road damage detected.</span>}
          </div>
        </div>
        <div className="card scroll-x">
          <h3>Detections</h3>
          <table className="t">
            <thead><tr><th></th><th>Defect</th><th>Class</th><th>Conf</th><th>Severity</th><th>Risk</th></tr></thead>
            <tbody>
              {dets.map((d) => (
                <tr key={d.id} className="click" onClick={() => d.defect_id && setSel(d.defect_id)}>
                  <td>{d.crop_url && <img className="thumb" src={d.crop_url} />}</td>
                  <td>
                    <span className="uid">{d.defect_uid}</span>
                    {d.is_duplicate && <div><span className="pill dup">already reported</span></div>}
                    {d.track_id != null && <div className="note">track #{d.track_id}, {d.frames_seen} frames</div>}
                  </td>
                  <td>{label(d.class_name)}</td>
                  <td className="mono">{d.confidence.toFixed(2)}</td>
                  <td><Pill v={d.severity} /></td>
                  <td><Risk score={d.risk_score} level={d.risk_level} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {insp.media_type === 'image' && file && hasPothole && (
        <div className="card" style={{ gridColumn: '1 / -1' }}>
          <div className="row">
            <h3 style={{ margin: 0 }}>Pothole size and depth</h3>
            <span className="spacer" />
            {!measure && <button className="btn primary" onClick={() => setMeasure(true)}>Measure size and depth</button>}
          </div>
          {measure && <div style={{ marginTop: 10 }}><MeasurePanel file={file} /></div>}
        </div>
      )}
      {sel != null && <DefectDrawer id={sel} onClose={() => setSel(null)} />}
    </div>
  )
}

export default function Analyze() {
  const [file, setFile] = useState<File | null>(null)
  const [gpx, setGpx] = useState<File | null>(null)
  const [loc, setLoc] = useState<[number, number] | null>(null)
  const [form, setForm] = useState({ captured_at: '', road_name: '', road_type: 'unknown', traffic_level: 'unknown', inspector: '', gpx_offset_s: '0' })
  const [busy, setBusy] = useState(false)
  const [prog, setProg] = useState(0)
  const [err, setErr] = useState('')
  const [res, setRes] = useState<Inspection | null>(null)
  const [drag, setDrag] = useState(false)
  const inp = useRef<HTMLInputElement>(null)
  const preview = file ? URL.createObjectURL(file) : null
  const isVideo = file?.type.startsWith('video')

  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.value })

  const useMyLocation = () =>
    navigator.geolocation?.getCurrentPosition(
      (p) => setLoc([p.coords.latitude, p.coords.longitude]),
      () => setErr('Browser location unavailable. Click the map instead.'),
    )

  const submit = async () => {
    if (!file) return
    setBusy(true)
    setErr('')
    setRes(null)
    setProg(0)
    const fd = new FormData()
    fd.append('file', file)
    if (gpx) fd.append('gpx_file', gpx)
    if (loc) {
      fd.append('lat', String(loc[0]))
      fd.append('lon', String(loc[1]))
    }
    Object.entries(form).forEach(([k, v]) => v && fd.append(k, v))
    try {
      const r = await api.upload(fd)
      if (r.status === 'done') setRes(r.inspection)
      else {
        // video job: poll
        while (true) {
          await new Promise((ok) => setTimeout(ok, 1200))
          const j = await api.job(r.job_id)
          setProg(j.progress ?? 0)
          if (j.status === 'done') {
            setRes(j.inspection)
            break
          }
          if (j.status === 'error') throw new Error(j.error)
        }
      }
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-h">
        <div>
          <h1>Upload media</h1>
          <p>Add a road photo or dashcam clip. The AI finds the damage, rates it and files it in the registry.</p>
        </div>
      </div>
      <div className="grid g2">
        <div className="card grid">
          <div
            className={`drop ${drag ? 'on' : ''}`}
            onClick={() => inp.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDrag(true)
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDrag(false)
              setFile(e.dataTransfer.files[0] ?? null)
            }}
          >
            {preview ? (
              isVideo ? <video src={preview} className="media" style={{ maxHeight: 260 }} muted /> : <img src={preview} className="media" style={{ maxHeight: 260 }} />
            ) : (
              <>
                <b style={{ fontSize: 16 }}>Drop a photo or video</b>
                <div className="note">or click to choose a file. Photos and videos up to a few minutes.</div>
              </>
            )}
            <input ref={inp} type="file" accept="image/*,video/*" capture="environment" hidden onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          {file && <div className="note mono">{file.name} ({(file.size / 1e6).toFixed(1)} MB)</div>}
          <div className="grid g2">
            <label className="f">Inspection date/time<input type="datetime-local" value={form.captured_at} onChange={set('captured_at')} /></label>
            <label className="f">Inspector<input value={form.inspector} onChange={set('inspector')} placeholder="name" /></label>
            <label className="f">Road name<input value={form.road_name} onChange={set('road_name')} placeholder="e.g. MG Road" /></label>
            <label className="f">Road type
              <select value={form.road_type} onChange={set('road_type')}>
                {['unknown', 'highway', 'arterial', 'collector', 'local'].map((x) => <option key={x}>{x}</option>)}
              </select>
            </label>
            <label className="f">Traffic level
              <select value={form.traffic_level} onChange={set('traffic_level')}>
                {['unknown', 'high', 'medium', 'low'].map((x) => <option key={x}>{x}</option>)}
              </select>
            </label>
            {isVideo && (
              <label className="f">GPX track (optional)<input type="file" accept=".gpx" onChange={(e) => setGpx(e.target.files?.[0] ?? null)} /></label>
            )}
            {isVideo && gpx && <label className="f">GPX time offset (s)<input type="number" value={form.gpx_offset_s} onChange={set('gpx_offset_s')} /></label>}
          </div>
          <div className="row">
            <button className="btn primary" disabled={!file || busy} onClick={submit}>{busy ? 'Analyzing...' : 'Run detection'}</button>
            {busy && isVideo && <div style={{ flex: 1 }}><div className="bar"><div style={{ width: `${prog * 100}%` }} /></div><div className="note">{Math.round(prog * 100)}% of frames tracked</div></div>}
          </div>
          {err && <div className="err">{err}</div>}
        </div>
        <div className="card grid" style={{ alignContent: 'start' }}>
          <div className="row">
            <h3 style={{ margin: 0 }}>Where was this taken?</h3>
            <span className="spacer" />
            <button className="btn sm" onClick={useMyLocation}>Use my location</button>
            {loc && <button className="btn sm" onClick={() => setLoc(null)}>Clear</button>}
          </div>
          <LocationPicker value={loc} onChange={setLoc} />
          <div className="note">
            {loc ? <span className="mono">{loc[0].toFixed(6)}, {loc[1].toFixed(6)} (manual pin)</span> : 'Photos taken with location on are placed automatically. Otherwise tap the map to drop a pin.'}
            
          </div>
        </div>
      </div>
      {res && <InspectionResult insp={res} file={file} />}
    </>
  )
}
