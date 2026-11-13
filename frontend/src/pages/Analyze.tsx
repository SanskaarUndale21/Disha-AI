import { useEffect, useRef, useState } from 'react'
import { FilePdf } from '@phosphor-icons/react'
import { analysisPdfUrl, api, label, tierOf, type Inspection } from '../api'
import { RoadRecord } from '../roadrecord'
import { DefectDrawer, LocationPicker, Pill, Risk, TierPill } from '../components'
import { MeasurePanel } from '../measure'

export function InspectionResult({ insp, file, quality }: { insp: Inspection; file?: File | null; quality?: string }) {
  const [sel, setSel] = useState<number | null>(null)
  const [measure, setMeasure] = useState(false)
  const s = insp.summary ?? {}
  const [hiOnly, setHiOnly] = useState(false)
  const allDets = insp.detections ?? []
  const dets = hiOnly ? allDets.filter((d) => tierOf(d) === 'high') : allDets
  const isVideo = insp.media_type === 'video'
  const hasPothole = allDets.some((d) => d.class_name === 'pothole')
  const potholes = new Set(allDets.filter((d) => d.class_name === 'pothole').map((d) => d.defect_uid ?? `t${d.track_id ?? d.id}`)).size
  const uniqueDefects = s.unique_tracks ?? allDets.length
  const rawTracks = s.raw_track_ids ?? uniqueDefects
  const q = String(s.quality ?? quality ?? '').toLowerCase()
  const secs = insp.processing_ms != null ? insp.processing_ms / 1000 : null
  return (
    <div className="grid g-wide" style={{ marginTop: 14 }}>
      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Inspection #{insp.id} result</h3>
          <span className="spacer" />
          <a className="btn primary" href={analysisPdfUrl(insp.id)} target="_blank" rel="noreferrer"><FilePdf size={17} weight="fill" /> Download PDF report</a>
        </div>
        {!isVideo ? (
          <img className="media" src={insp.annotated_url ?? ''} alt="Annotated road photo with detected damage" />
        ) : (
          <video className="media" src={insp.annotated_url ?? ''} controls autoPlay muted loop playsInline />
        )}
        <p className="note">
          {isVideo ? 'Boxes and defect IDs are drawn on the video. ' : ''}
          {s.enhanced ? 'Low-light correction (CLAHE) applied. ' : ''}
          Location: {insp.lat != null ? `${insp.lat.toFixed(6)}, ${insp.lon!.toFixed(6)} via ${insp.location_source}` : 'unknown'}.
          {' '}Processed in {secs != null ? `${secs.toFixed(secs < 10 ? 1 : 0)} s` : '-'}{insp.model_name ? ` with ${insp.model_name}` : ''}
          {isVideo && insp.frames_processed ? `, ${insp.frames_processed} frames tracked` : ''}{isVideo && q ? `, ${q === '4k' ? '4K detailed' : '2K fast'} mode` : ''}.
          {insp.duplicate_of_inspection && <b> This exact image was already uploaded as inspection #{insp.duplicate_of_inspection}.</b>}
        </p>
      </div>
      <div className="grid" style={{ alignContent: 'start' }}>
        <div className="card ar-hero">
          <div className="ar-big num">{potholes}</div>
          <div>
            <div className="ar-hl">Unique potholes found</div>
            {isVideo ? (
              <div className="note">{rawTracks} raw tracks merged into {uniqueDefects} unique defect{uniqueDefects === 1 ? '' : 's'}. The same pothole seen in many frames is counted once.</div>
            ) : (
              <div className="note">{uniqueDefects} defect{uniqueDefects === 1 ? '' : 's'} of all types in this photo.</div>
            )}
          </div>
        </div>
        <div className="grid g3">
          <div className="card kpi"><div className="l">Detected</div><div className="v">{s.total ?? allDets.length}</div></div>
          <div className="card kpi"><div className="l">New defects</div><div className="v">{s.new_defects ?? 0}</div></div>
          <div className="card kpi"><div className="l">Already known</div><div className="v">{s.duplicates ?? 0}</div></div>
        </div>
        <div className="card">
          <h3>Counts by class</h3>
          <div className="row">
            {Object.entries(s.by_class ?? {}).map(([k, v]) => (
              <span key={k} className="pill">{label(k)}: <b className="num">{v as number}</b></span>
            ))}
            {allDets.length === 0 && <span className="muted">No road damage detected.</span>}
          </div>
        </div>
      </div>
      <div className="card scroll-x" style={{ gridColumn: '1 / -1' }}>
        <div className="row" style={{ justifyContent: 'space-between' }}><h3>Detected defects</h3><label className="toggle"><input type="checkbox" checked={hiOnly} onChange={(e) => setHiOnly(e.target.checked)} /> High confidence only ({allDets.filter((d) => tierOf(d) === 'high').length} of {allDets.length})</label></div>
        {dets.length === 0 ? (
          <div className="empty">Nothing was flagged. Try a clearer photo or a drive with more daylight.</div>
        ) : (
          <table className="t">
            <thead><tr><th></th><th>ID</th><th>Class</th><th>Confidence</th><th>Severity</th><th>Risk</th>{isVideo && <th>Frames seen</th>}</tr></thead>
            <tbody>
              {dets.map((d) => (
                <tr key={d.id} className="click" tabIndex={0} onClick={() => d.defect_id && setSel(d.defect_id)} onKeyDown={(e) => e.key === 'Enter' && d.defect_id && setSel(d.defect_id)}>
                  <td>{d.crop_url && <img className="thumb" src={d.crop_url} alt="" />}</td>
                  <td>
                    <span className="uid">{d.defect_uid}</span>
                    {d.is_duplicate && <div><span className="pill dup">already reported</span></div>}
                  </td>
                  <td>{label(d.class_name)}</td>
                  <td>
                    <span className="mono">{d.confidence.toFixed(2)}</span>{' '}
                    <TierPill tier={tierOf(d)} />
                  </td>
                  <td><Pill v={d.severity} /></td>
                  <td><Risk score={d.risk_score} level={d.risk_level} /></td>
                  {isVideo && <td className="mono">{d.frames_seen ?? '-'}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {insp.lat != null && insp.lon != null && (
        <div style={{ gridColumn: '1 / -1' }}><RoadRecord lat={insp.lat} lon={insp.lon} /></div>
      )}
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
  const [elapsed, setElapsed] = useState(0)
  const [quality, setQuality] = useState<'2k' | '4k'>('2k')
  const [doneQuality, setDoneQuality] = useState('2k')
  useEffect(() => {
    if (!busy) return
    const t0 = Date.now()
    setElapsed(0)
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000)
    return () => clearInterval(t)
  }, [busy])
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
    if (file.type.startsWith('video')) fd.append('quality', quality)
    setDoneQuality(quality)
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
              <div className="f" style={{ gridColumn: '1 / -1' }}>
                Video quality
                <div className="seg" role="group" aria-label="Video quality" style={{ alignSelf: 'flex-start' }}>
                  <button type="button" className={quality === '2k' ? 'on' : ''} aria-pressed={quality === '2k'} onClick={() => setQuality('2k')}>2K (fast)</button>
                  <button type="button" className={quality === '4k' ? 'on' : ''} aria-pressed={quality === '4k'} onClick={() => setQuality('4k')}>4K (detailed)</button>
                </div>
                <span className="note">2K analyses faster. 4K keeps more detail, so distant potholes are found more often.</span>
              </div>
            )}
            {isVideo && (
              <label className="f">GPX track (optional)<input type="file" accept=".gpx" onChange={(e) => setGpx(e.target.files?.[0] ?? null)} /></label>
            )}
            {isVideo && gpx && <label className="f">GPX time offset (s)<input type="number" value={form.gpx_offset_s} onChange={set('gpx_offset_s')} /></label>}
          </div>
          <div className="row">
            <button className="btn primary" disabled={!file || busy} onClick={submit}>{busy ? 'Analyzing...' : 'Run detection'}</button>
            {busy && !isVideo && <span className="note num">{elapsed}s elapsed</span>}
            {busy && isVideo && <div style={{ flex: 1 }}><div className="bar"><div style={{ width: `${prog * 100}%` }} /></div><div className="note num">{Math.round(prog * 100)}% of frames tracked, {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')} elapsed</div></div>}
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
      {res && <InspectionResult insp={res} file={file} quality={doneQuality} />}
    </>
  )
}
