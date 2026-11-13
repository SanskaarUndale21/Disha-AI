import { useEffect, useRef, useState } from 'react'
import { authHeaders } from './api'

export type PotholeSize = {
  index: number
  confidence: number
  box: number[]
  width_cm: number
  length_cm: number
  area_m2: number
  depth_reliable: boolean
  size_reliable: boolean
  depth_source: string
  depth_max_cm: number | null
  depth_mean_cm: number | null
  depth_max_range_cm: [number, number]
  depth_mean_range_cm: [number, number]
  depth_width_ratio: number | null
  width_range_cm: [number, number]
  length_range_cm: [number, number]
  volume_litres: number | null
  volume_range_litres: [number, number]
  cold_mix_kg: number | null
  cold_mix_range_kg: [number, number]
  scale_mode: string
  scale_mode_label: string
  uncertainty_pct: number
  depth_uncertainty_pct: number
  depth_confidence: string
  water: boolean
  notes: string[]
}

export type MeasureResult = {
  potholes: PotholeSize[]
  annotated_url: string | null
  image_size: [number, number]
  method: Record<string, any>
  ms: number
}

const REFS = [
  { v: 'a4', t: 'A4 sheet (29.7 cm long side)' },
  { v: 'credit_card', t: 'Credit card (8.56 cm long side)' },
  { v: 'bottle_500ml', t: '500 ml bottle (21 cm tall)' },
  { v: 'foot', t: 'Shoe or foot (about 27 cm)' },
  { v: 'custom', t: 'Custom length' },
]

async function parse(r: Response): Promise<MeasureResult> {
  if (!r.ok) {
    let msg = r.statusText
    try {
      const j = await r.json()
      msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j)
    } catch {
      /* ignore */
    }
    throw new Error(msg)
  }
  return r.json()
}

const rng = (r: [number, number] | undefined, unit: string) =>
  r ? `${r[0].toFixed(r[1] < 10 ? 1 : 0)} to ${r[1].toFixed(r[1] < 10 ? 1 : 0)} ${unit}` : ''

function Row({ p }: { p: PotholeSize }) {
  const est = !p.depth_reliable
  return (
    <div className="ms-item">
      <div className="row">
        <b>Pothole {p.index + 1}</b>
        <span className="pill">{p.scale_mode_label}</span>
        <span className="spacer" />
        <span className="note">detector confidence {p.confidence.toFixed(2)}</span>
      </div>
      <div className="ms-grid">
        <div className="ms-stat">
          <div className="l">Width x length</div>
          <div className="v">{p.width_cm.toFixed(0)} x {p.length_cm.toFixed(0)} cm</div>
          <div className="note">plus or minus {p.uncertainty_pct}%</div>
        </div>
        <div className="ms-stat">
          <div className="l">Area</div>
          <div className="v">{p.area_m2.toFixed(2)} m2</div>
        </div>
        <div className="ms-stat">
          <div className="l">{est ? 'Depth (estimate)' : 'Depth max / mean'}</div>
          <div className="v">
            {est ? '~' : ''}
            {p.depth_max_cm?.toFixed(1)} / {p.depth_mean_cm?.toFixed(1)} cm
          </div>
          <div className="note">{est ? `typical range ${rng(p.depth_max_range_cm, 'cm')}` : `max ${rng(p.depth_max_range_cm, 'cm')}`}</div>
        </div>
        <div className="ms-stat">
          <div className="l">Volume</div>
          <div className="v">{est ? '~' : ''}{p.volume_litres?.toFixed(1)} litres</div>
          <div className="note">{rng(p.volume_range_litres, 'litres')}</div>
        </div>
        <div className="ms-stat">
          <div className="l">Cold mix needed</div>
          <div className="v">{est ? '~' : ''}{p.cold_mix_kg?.toFixed(1)} kg</div>
          <div className="note">{rng(p.cold_mix_range_kg, 'kg')}</div>
        </div>
      </div>
      <div className="row" style={{ marginTop: 6 }}>
        <span className={`pill ${est ? 'Medium' : 'Low'}`}>
          {est ? 'Depth not reliable, shown as an estimate' : `Depth confidence ${p.depth_confidence}`}
        </span>
        {p.depth_width_ratio != null && <span className="note">depth is {(p.depth_width_ratio * 100).toFixed(0)}% of width</span>}
        {p.water && <span className="pill dup">standing water</span>}
        {!p.size_reliable && <span className="pill Medium">size is a rough guess</span>}
      </div>
      {p.notes.length > 0 && (
        <ul className="ms-notes">
          {p.notes.map((n, i) => <li key={i}>{n}</li>)}
        </ul>
      )}
    </div>
  )
}

/** Measures every pothole in a photo (file) or one defect's best photo (defectId) and shows size, depth and material. */
export function MeasurePanel({ file, defectId, auto = true }: { file?: File | null; defectId?: number; auto?: boolean }) {
  const [res, setRes] = useState<MeasureResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [refType, setRefType] = useState('')
  const [refLen, setRefLen] = useState('')
  const [refBox, setRefBox] = useState<number[] | null>(null)
  const [drag, setDrag] = useState<{ x: number; y: number; x2: number; y2: number } | null>(null)
  const [pick, setPick] = useState(false)
  const imgRef = useRef<HTMLImageElement>(null)
  const canRef = !!file

  const run = async (withRef: boolean) => {
    setBusy(true)
    setErr('')
    try {
      let r: Response
      if (file) {
        const fd = new FormData()
        fd.append('file', file)
        if (withRef && refType && refBox) {
          fd.append('reference_type', refType)
          if (refType === 'custom') fd.append('reference_length_cm', refLen)
          fd.append('ref_box', refBox.map((v) => Math.round(v)).join(','))
        }
        r = await fetch('/api/measure', { method: 'POST', body: fd, headers: authHeaders() })
      } else if (defectId != null) {
        r = await fetch(`/api/measure/defect/${defectId}`, { headers: authHeaders() })
      } else return
      setRes(await parse(r))
    } catch (e: any) {
      setErr(e?.message || 'Measurement failed')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    fetch('/api/measure/warmup', { method: 'POST', headers: authHeaders() }).catch(() => {})
    if (auto) run(false)
  }, [file, defectId])

  const toImg = (e: React.PointerEvent) => {
    const el = imgRef.current
    if (!el || !res) return null
    const b = el.getBoundingClientRect()
    return {
      x: Math.min(Math.max(0, ((e.clientX - b.left) / b.width) * res.image_size[0]), res.image_size[0]),
      y: Math.min(Math.max(0, ((e.clientY - b.top) / b.height) * res.image_size[1]), res.image_size[1]),
    }
  }
  const pct = (v: number, i: number) => `${(v / (res?.image_size[i] ?? 1)) * 100}%`
  const shown = drag ?? (refBox ? { x: refBox[0], y: refBox[1], x2: refBox[2], y2: refBox[3] } : null)
  const needLen = refType === 'custom' && !(parseFloat(refLen) > 0)

  return (
    <div className="ms-panel">
      {busy && <div className="note">Measuring. The first run loads the depth model and can take a few seconds.</div>}
      {err && <div className="err">{err}</div>}
      {res && (
        <>
          {res.annotated_url && (
            <div className="ms-imgwrap">
              <img ref={imgRef} className="media" src={res.annotated_url} alt="Annotated measurement" draggable={false} />
              {pick && (
                <div
                  className="ms-overlay"
                  onPointerDown={(e) => {
                    const p = toImg(e)
                    if (p) {
                      ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
                      setDrag({ x: p.x, y: p.y, x2: p.x, y2: p.y })
                    }
                  }}
                  onPointerMove={(e) => {
                    const p = toImg(e)
                    if (p && drag) setDrag({ ...drag, x2: p.x, y2: p.y })
                  }}
                  onPointerUp={() => {
                    if (drag && Math.abs(drag.x2 - drag.x) + Math.abs(drag.y2 - drag.y) > 8) {
                      setRefBox([Math.min(drag.x, drag.x2), Math.min(drag.y, drag.y2), Math.max(drag.x, drag.x2), Math.max(drag.y, drag.y2)])
                      setPick(false)
                    }
                    setDrag(null)
                  }}
                />
              )}
              {shown && (
                <div
                  className="ms-refbox"
                  style={{ left: pct(Math.min(shown.x, shown.x2), 0), top: pct(Math.min(shown.y, shown.y2), 1), width: pct(Math.abs(shown.x2 - shown.x), 0), height: pct(Math.abs(shown.y2 - shown.y), 1) }}
                />
              )}
            </div>
          )}
          {res.potholes.length === 0 && <div className="note">No pothole found in this photo, nothing to measure.</div>}
          {res.potholes.map((p) => <Row key={p.index} p={p} />)}
          <div className="note">
            Camera height {res.method.camera_height_m} m ({res.method.camera}), horizon from {res.method.horizon_source}. Done in {res.ms} ms.
            These are estimates from a single photo, not survey measurements.
          </div>
        </>
      )}
      {canRef && (
        <details className="ms-ref">
          <summary>Add a reference object for a more accurate scale</summary>
          <div className="note">Place a known object on the road next to the pothole, pick it here, then drag a box around its long side on the image.</div>
          <div className="row" style={{ marginTop: 8 }}>
            <select value={refType} onChange={(e) => { setRefType(e.target.value); setRefBox(null) }}>
              <option value="">Choose an object</option>
              {REFS.map((r) => <option key={r.v} value={r.v}>{r.t}</option>)}
            </select>
            {refType === 'custom' && (
              <input type="number" min="1" step="0.1" placeholder="length in cm" value={refLen} onChange={(e) => setRefLen(e.target.value)} style={{ width: 120 }} />
            )}
            <button className="btn sm" disabled={!refType || needLen || !res} onClick={() => setPick(true)}>
              {pick ? 'Drag on the image...' : refBox ? 'Redraw box' : 'Draw box'}
            </button>
            <button className="btn sm primary" disabled={!refType || needLen || !refBox || busy} onClick={() => run(true)}>Re-measure</button>
            {refBox && <button className="btn sm" onClick={() => { setRefBox(null); run(false) }}>Clear</button>}
          </div>
        </details>
      )}
      {!auto && !res && !busy && <button className="btn primary" onClick={() => run(false)}>Measure size and depth</button>}
    </div>
  )
}
