import { useEffect, useRef, useState } from 'react'
import { ArrowCounterClockwise, Camera, CheckCircle, Crosshair, FileVideo, FilmStrip, FloppyDisk, ImageSquare, Lightning, MapPin, Pause, Play, Siren, SpeakerHigh, SpeakerSlash, Warning } from '@phosphor-icons/react'
import { authHeaders, label } from '../api'

type Track = {
  id: number | null
  tid: number
  cls: string
  conf: number
  box: number[]
  poly: number[][][]
  severity: string
  sev: number
  size: number
  depth: number
  risk: string
  risk_score: number
  risk_parts: Record<string, number>
  hits: number
  confirmed: boolean
}
type FrameMsg = {
  type: 'frame'
  w: number
  h: number
  tracks: Track[]
  unique: number
  by_class: Record<string, number>
  infer_ms: number
  frame: number
  cracks: boolean
  people?: { box: number[]; fallen: boolean }[]
  emergency?: Emergency
}
type Emergency = { id: number; type: string; pothole_id: number; message: string; snapshot_url: string }

export const CLASS_COLOR: Record<string, string> = {
  pothole: '#ff3b30',
  alligator_crack: '#ff9500',
  transverse_crack: '#0a84ff',
  longitudinal_crack: '#bf5af2',
  manhole: '#1f8cc7',
  speed_breaker: '#f2b705',
  debris: '#8c7a3c',
  barricade: '#c8c8c8',
}
export const PREFIX: Record<string, string> = { pothole: 'PH', alligator_crack: 'AC', transverse_crack: 'TC', longitudinal_crack: 'LC', manhole: 'MH', speed_breaker: 'SB', debris: 'DB', barricade: 'BR' }
const SEV_W: Record<string, number> = { Low: 2, Medium: 3, High: 4.5, Minor: 2, Moderate: 2.8, Severe: 3.8, Critical: 5 }
const SEV_COL: Record<string, string> = { Minor: '#2e9a57', Moderate: '#f2b705', Severe: '#dd7a07', Critical: '#d92d20', Low: '#2e9a57', Medium: '#dd7a07', High: '#d92d20' }
const RISK_COL: Record<string, string> = { High: '#ff3b30', Medium: '#ff9500', Low: '#34c759' }
const SEND_W = 640
const IN_FLIGHT = 2

function drawOverlay(cv: HTMLCanvasElement, video: HTMLVideoElement, m: FrameMsg | null, trails: Map<number, number[][]>, t: number) {
  const rect = video.getBoundingClientRect()
  const dpr = window.devicePixelRatio || 1
  const W = Math.round(rect.width * dpr), H = Math.round(rect.height * dpr)
  if (cv.width !== W || cv.height !== H) {
    cv.width = W
    cv.height = H
  }
  const ctx = cv.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, rect.width, rect.height)
  if (!m || !video.videoWidth) return
  const s = Math.min(rect.width / m.w, rect.height / m.h)
  const ox = (rect.width - m.w * s) / 2
  const oy = (rect.height - m.h * s) / 2
  const P = (x: number, y: number): [number, number] => [ox + x * s, oy + y * s]

  // motion trails (proof of tracking)
  for (const [tid, pts] of trails) {
    const tr = m.tracks.find((x) => x.tid === tid)
    if (!tr || !tr.confirmed || pts.length < 2) continue
    const col = CLASS_COLOR[tr.cls] ?? '#fff'
    ctx.lineWidth = 2
    for (let i = 1; i < pts.length; i++) {
      ctx.strokeStyle = col + Math.round((i / pts.length) * 200).toString(16).padStart(2, '0')
      ctx.beginPath()
      ctx.moveTo(...P(pts[i - 1][0], pts[i - 1][1]))
      ctx.lineTo(...P(pts[i][0], pts[i][1]))
      ctx.stroke()
    }
  }

  // people (pose model): white, red when fallen
  for (const p of m.people ?? []) {
    const [X, Y] = P(p.box[0], p.box[1])
    const Wd = (p.box[2] - p.box[0]) * s, Ht = (p.box[3] - p.box[1]) * s
    ctx.strokeStyle = p.fallen ? '#ff3b30' : '#ffffff'
    ctx.lineWidth = p.fallen ? 3 : 1.5
    ctx.setLineDash(p.fallen ? [] : [6, 4])
    ctx.strokeRect(X, Y, Wd, Ht)
    ctx.setLineDash([])
    if (p.fallen) {
      ctx.font = '700 13px -apple-system, "SF Pro Text", Inter, "Segoe UI", sans-serif'
      ctx.fillStyle = '#ff3b30'
      ctx.fillRect(X, Y - 20, ctx.measureText('Fallen').width + 12, 20)
      ctx.fillStyle = '#fff'
      ctx.fillText('Fallen', X + 6, Y - 6)
    }
  }

  for (const tr of m.tracks) {
    const [x1, y1, x2, y2] = tr.box
    const [X, Y] = P(x1, y1)
    const Wd = (x2 - x1) * s, Ht = (y2 - y1) * s
    const col = CLASS_COLOR[tr.cls] ?? '#fff'
    if (!tr.confirmed) {
      ctx.setLineDash([4, 4])
      ctx.strokeStyle = col + '88'
      ctx.lineWidth = 1.5
      ctx.strokeRect(X, Y, Wd, Ht)
      ctx.setLineDash([])
      continue
    }
    const lw = SEV_W[tr.severity] ?? 2
    // damage outline from the OpenCV segmentation
    for (const poly of tr.poly ?? []) {
      if (poly.length < 3) continue
      ctx.beginPath()
      poly.forEach(([px, py], i) => (i ? ctx.lineTo(...P(px, py)) : ctx.moveTo(...P(px, py))))
      ctx.closePath()
      ctx.fillStyle = col + '40'
      ctx.fill()
      ctx.strokeStyle = col
      ctx.lineWidth = 1.5
      ctx.stroke()
    }
    if (tr.risk === 'High') {
      ctx.shadowColor = col
      ctx.shadowBlur = 12 + 8 * Math.sin(t / 160)
    }
    ctx.strokeStyle = col
    ctx.lineWidth = 1
    ctx.strokeRect(X, Y, Wd, Ht)
    const c = Math.max(10, Math.min(Wd, Ht) * 0.25)
    ctx.lineWidth = lw + 2
    ctx.lineCap = 'round'
    ctx.beginPath()
    ctx.moveTo(X, Y + c); ctx.lineTo(X, Y); ctx.lineTo(X + c, Y)
    ctx.moveTo(X + Wd - c, Y); ctx.lineTo(X + Wd, Y); ctx.lineTo(X + Wd, Y + c)
    ctx.moveTo(X, Y + Ht - c); ctx.lineTo(X, Y + Ht); ctx.lineTo(X + c, Y + Ht)
    ctx.moveTo(X + Wd - c, Y + Ht); ctx.lineTo(X + Wd, Y + Ht); ctx.lineTo(X + Wd, Y + Ht - c)
    ctx.stroke()
    ctx.shadowBlur = 0
    // tag: ID + severity + risk
    const tag = `${PREFIX[tr.cls] ?? 'RD'} ${tr.id}`
    const sub = `${tr.severity} severity, risk ${Math.round(tr.risk_score)}`
    ctx.font = '600 13px -apple-system, "SF Pro Text", Inter, "Segoe UI", sans-serif'
    const tw = ctx.measureText(tag).width
    ctx.font = '500 11px -apple-system, "SF Pro Text", Inter, "Segoe UI", sans-serif'
    const sw = ctx.measureText(sub).width
    const bw = Math.max(tw, sw) + 16
    const by = Y - 40 < 0 ? Y + Ht + 4 : Y - 40
    ctx.fillStyle = 'rgba(28,28,30,.78)'
    ctx.beginPath()
    ctx.roundRect(X, by, bw, 36, 9)
    ctx.fill()
    ctx.fillStyle = col
    ctx.beginPath()
    ctx.arc(X + 9, by + 11, 3.5, 0, Math.PI * 2)
    ctx.fill()
    ctx.fillStyle = '#fff'
    ctx.font = '600 13px -apple-system, "SF Pro Text", Inter, "Segoe UI", sans-serif'
    ctx.fillText(tag, X + 17, by + 15)
    ctx.fillStyle = RISK_COL[tr.risk] ?? '#ddd'
    ctx.font = '500 11px -apple-system, "SF Pro Text", Inter, "Segoe UI", sans-serif'
    ctx.fillText(sub, X + 8, by + 30)
  }
}

export default function Live() {
  const video = useRef<HTMLVideoElement>(null)
  const overlay = useRef<HTMLCanvasElement>(null)
  const grab = useRef<HTMLCanvasElement>(document.createElement('canvas'))
  const ws = useRef<WebSocket | null>(null)
  const last = useRef<FrameMsg | null>(null)
  const trails = useRef<Map<number, number[][]>>(new Map())
  const running = useRef(false)
  const inflight = useRef(0)
  const times = useRef<number[]>([])
  const [msg, setMsg] = useState<FrameMsg | null>(null)
  const [fps, setFps] = useState(0)
  const [src, setSrc] = useState<'none' | 'camera' | 'file'>('none')
  const [status, setStatus] = useState('idle')
  const [saved, setSaved] = useState<any>(null)
  const [meta, setMeta] = useState({ road_name: '', road_type: 'unknown', traffic_level: 'unknown' })
  const [loc, setLoc] = useState<[number, number] | null>(null)
  const [seen, setSeen] = useState<Record<number, Track>>({})
  const [cracks, setCracks] = useState(true)
  const fileIn = useRef<HTMLInputElement>(null)
  // "pothole ahead" warning: banner for 2 s plus a short beep, at most once every 3 s per track
  const [ahead, setAhead] = useState<string | null>(null)
  const [sound, setSound] = useState(true)
  const soundRef = useRef(true)
  soundRef.current = sound
  const lastWarn = useRef<Map<number, number>>(new Map())
  const aheadTimer = useRef<any>(null)
  const audio = useRef<AudioContext | null>(null)
  // fall near a pothole: red takeover banner + two-tone siren until acknowledged
  const [emergency, setEmergency] = useState<Emergency | null>(null)
  const [ackErr, setAckErr] = useState<string | null>(null)
  const siren = useRef<{ osc: OscillatorNode; gain: GainNode; timer: any } | null>(null)

  const stopSiren = () => {
    const sn = siren.current
    if (!sn) return
    clearInterval(sn.timer)
    try {
      sn.gain.gain.setTargetAtTime(0.0001, sn.osc.context.currentTime, 0.03)
      sn.osc.stop(sn.osc.context.currentTime + 0.1)
    } catch {
      /* already stopped */
    }
    siren.current = null
  }

  const startSiren = () => {
    if (siren.current) return
    try {
      const AC = window.AudioContext || (window as any).webkitAudioContext
      if (!AC) return
      const ctx = audio.current ?? (audio.current = new AC())
      if (ctx.state === 'suspended') ctx.resume().catch(() => {})
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'square'
      osc.frequency.value = 650
      gain.gain.value = 0.08
      osc.connect(gain).connect(ctx.destination)
      osc.start()
      let hi = false
      const timer = setInterval(() => {
        hi = !hi
        osc.frequency.setValueAtTime(hi ? 950 : 650, ctx.currentTime)
      }, 450)
      siren.current = { osc, gain, timer }
    } catch {
      /* audio unavailable */
    }
  }

  useEffect(() => {
    if (emergency && sound) startSiren()
    else stopSiren()
  }, [emergency, sound])

  const acknowledge = async () => {
    if (!emergency) return
    setAckErr(null)
    try {
      const r = await fetch(`/api/safety/emergencies/${emergency.id}/ack`, { method: 'POST', headers: authHeaders() })
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText)
      setEmergency(null)
    } catch (e: any) {
      setAckErr(`Could not acknowledge: ${e.message}`)
    }
  }

  const beep = () => {
    try {
      const AC = window.AudioContext || (window as any).webkitAudioContext
      if (!AC) return
      const ctx = audio.current ?? (audio.current = new AC())
      if (ctx.state === 'suspended') ctx.resume().catch(() => {})
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = 880
      const t0 = ctx.currentTime
      gain.gain.setValueAtTime(0.0001, t0)
      gain.gain.exponentialRampToValueAtTime(0.25, t0 + 0.01)
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.15)
      osc.connect(gain).connect(ctx.destination)
      osc.start(t0)
      osc.stop(t0 + 0.16)
    } catch {
      /* audio unavailable */
    }
  }

  const checkAhead = (m: FrameMsg) => {
    const now = performance.now()
    for (const tr of m.tracks) {
      if (!tr.confirmed || tr.cls !== 'pothole') continue
      if (!(tr.severity === 'Severe' || tr.severity === 'Critical' || tr.risk === 'High')) continue
      const cx = (tr.box[0] + tr.box[2]) / 2, cy = (tr.box[1] + tr.box[3]) / 2
      if (cy < m.h * 0.55 || cx < m.w * 0.25 || cx > m.w * 0.75) continue
      const key = tr.id ?? -tr.tid - 1
      if (now - (lastWarn.current.get(key) ?? -1e9) < 3000) continue
      lastWarn.current.set(key, now)
      setAhead(`${PREFIX.pothole} ${tr.id ?? tr.tid}`)
      clearTimeout(aheadTimer.current)
      aheadTimer.current = setTimeout(() => setAhead(null), 2000)
      if (soundRef.current) beep()
      break
    }
  }

  useEffect(() => () => {
    clearTimeout(aheadTimer.current)
    stopSiren()
    audio.current?.close().catch(() => {})
  }, [])

  useEffect(() => {
    let raf = 0
    const loop = (t: number) => {
      if (overlay.current && video.current) drawOverlay(overlay.current, video.current, last.current, trails.current, t)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [])

  useEffect(() => () => stop(), [])

  const connect = () =>
    new Promise<WebSocket>((ok, bad) => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const s = new WebSocket(`${proto}://${location.host}/ws/live`)
      s.binaryType = 'arraybuffer'
      s.onopen = () => {
        s.send(JSON.stringify({ type: 'config', cracks }))
        ok(s)
      }
      s.onerror = () => bad(new Error('Cannot reach the detection server'))
      s.onclose = () => {
        if (ws.current && ws.current !== s) return // a newer session replaced this socket: ignore its late close
        running.current = false
        setStatus((x) => (x === 'live' ? 'disconnected' : x))
      }
      s.onmessage = (e) => {
        if (ws.current && ws.current !== s) return // stale socket from a previous source
        const m = JSON.parse(e.data)
        if (m.type === 'frame') {
          inflight.current = Math.max(0, inflight.current - 1)
          last.current = m
          for (const tr of m.tracks as Track[]) {
            const cx = (tr.box[0] + tr.box[2]) / 2, cy = (tr.box[1] + tr.box[3]) / 2
            const arr = trails.current.get(tr.tid) ?? []
            arr.push([cx, cy])
            if (arr.length > 18) arr.shift()
            trails.current.set(tr.tid, arr)
          }
          setMsg(m)
          checkAhead(m)
          if (m.emergency) setEmergency(m.emergency)
          const now = performance.now()
          times.current = [...times.current.filter((x) => now - x < 1000), now]
          setFps(times.current.length)
          setSeen((prev) => {
            const nx = { ...prev }
            for (const t of m.tracks) if (t.confirmed && t.id != null) nx[t.id] = t
            return nx
          })
          pump()
        } else if (m.type === 'error') {
          inflight.current = Math.max(0, inflight.current - 1)
          pump()
        } else if (m.type === 'saved') {
          setSaved(m)
          setStatus('saved')
        }
      }
    })

  const sendOne = () => {
    const v = video.current
    const s = ws.current
    if (!running.current || !v || !s || s.readyState !== 1 || !v.videoWidth) return false
    if (v.paused || v.ended) return false
    const g = grab.current
    const sc = Math.min(1, SEND_W / v.videoWidth)
    g.width = Math.round(v.videoWidth * sc)
    g.height = Math.round(v.videoHeight * sc)
    g.getContext('2d')!.drawImage(v, 0, 0, g.width, g.height)
    inflight.current++
    g.toBlob((b) => {
      if (b && s.readyState === 1) b.arrayBuffer().then((buf) => s.send(buf))
      else inflight.current--
    }, 'image/jpeg', 0.72)
    return true
  }

  function pump() {
    while (running.current && inflight.current < IN_FLIGHT) {
      if (!sendOne()) {
        if (running.current) setTimeout(pump, 80)
        return
      }
    }
  }

  // share the browser position with the session so an emergency carries a location
  const sendGps = (s: WebSocket) => {
    const push = (lat: number, lon: number) => s.readyState === 1 && s.send(JSON.stringify({ type: 'gps', lat, lon }))
    if (loc) push(loc[0], loc[1])
    navigator.geolocation?.getCurrentPosition(
      (p) => {
        setLoc([p.coords.latitude, p.coords.longitude])
        push(p.coords.latitude, p.coords.longitude)
      },
      () => {},
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  const begin = async () => {
    setSaved(null)
    setSeen({})
    trails.current.clear()
    last.current = null
    inflight.current = 0
    try {
      ws.current = await connect()
      sendGps(ws.current)
      running.current = true
      setStatus('live')
      pump()
    } catch (e: any) {
      setStatus(e.message)
    }
  }

  const startCamera = async () => {
    stop()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      })
      const v = video.current!
      v.removeAttribute('src')
      v.srcObject = stream
      await v.play()
      setSrc('camera')
      await begin()
    } catch (e: any) {
      setStatus(`camera unavailable: ${e.message}`)
    }
  }

  const startUrl = async (url: string, file?: File) => {
    stop()
    const v = video.current!
    v.srcObject = null
    v.src = url
    v.loop = true
    v.playbackRate = 0.6 // recorded clips play a little slower so boxes stay on the potholes
    try {
      await v.play()
    } catch {
      if (!file) {
        setStatus('this video cannot be played')
        return
      }
      // the browser cannot decode this codec (MPEG-4 Part 2, HEVC...): convert it on the server to H.264
      setStatus('converting video for the browser...')
      try {
        const fd = new FormData()
        fd.append('file', file)
        const r = await fetch('/api/live/transcode', { method: 'POST', body: fd })
        if (!r.ok) throw new Error((await r.json()).detail ?? 'conversion failed')
        const { url: playable } = await r.json()
        v.src = playable
        v.playbackRate = 0.6
        await v.play()
      } catch (e: any) {
        setStatus(`video could not be played: ${e.message}`)
        return
      }
    }
    setSrc('file')
    await begin()
  }

  function stop() {
    running.current = false
    ws.current?.close()
    ws.current = null
    const v = video.current
    if (v?.srcObject) (v.srcObject as MediaStream).getTracks().forEach((t) => t.stop())
    if (v) v.pause()
    setStatus((s) => (s === 'live' ? 'stopped' : s))
  }

  const togglePause = () => {
    const v = video.current
    if (!v) return
    if (running.current) {
      running.current = false
      v.pause()
      setStatus('paused')
    } else {
      v.play()
      running.current = true
      setStatus('live')
      pump()
    }
  }

  const setMode = (c: boolean) => {
    setCracks(c)
    ws.current?.readyState === 1 && ws.current.send(JSON.stringify({ type: 'config', cracks: c }))
  }

  const save = () => {
    const s = ws.current
    if (!s || s.readyState !== 1) return
    running.current = false
    video.current?.pause()
    setStatus('saving')
    s.send(JSON.stringify({ type: 'finish', ...meta, lat: loc?.[0] ?? null, lon: loc?.[1] ?? null, location_source: loc ? 'gps' : null }))
  }

  const reset = () => {
    ws.current?.send(JSON.stringify({ type: 'reset' }))
    setSeen({})
    trails.current.clear()
    last.current = null
  }

  const gps = () =>
    navigator.geolocation?.getCurrentPosition(
      (p) => setLoc([p.coords.latitude, p.coords.longitude]),
      () => setStatus('location unavailable'),
      { enableHighAccuracy: true },
    )

  const list = Object.values(seen).sort((a, b) => b.risk_score - a.risk_score)
  const isLive = status === 'live'
  const visible = new Set((msg?.tracks ?? []).filter((t) => t.confirmed).map((t) => t.id))

  return (
    <div className="live-page">
      <div className="live-main">
        <div className="live-toolbar">
          <div className="live-title">
            <span className={`dot ${isLive ? 'on' : ''}`} />
            <b>Live patrol</b>
            <span className="muted">{isLive ? 'Detecting in real time' : status === 'idle' ? 'Ready' : status}</span>
          </div>
          <div className="row">
            <button className="btn primary" onClick={startCamera}><Camera size={17} weight="fill" /> Camera</button>
            <button className="btn" onClick={() => startUrl('/media/samples/pothole_drive.mp4')}><FilmStrip size={17} weight="fill" /> Demo drive</button>
            <button className="btn" onClick={() => fileIn.current?.click()}><FileVideo size={17} weight="fill" /> Video file</button>
            <input ref={fileIn} type="file" accept="video/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) startUrl(URL.createObjectURL(f), f); e.target.value = '' }} />
          </div>
        </div>
        <div className="live-wrap">
          <video ref={video} className="live-video" playsInline muted />
          <canvas ref={overlay} className="live-overlay" />
          {src === 'none' && (
            <div className="live-empty">
              <Crosshair size={44} weight="thin" />
              <div className="big">Point a camera at the road</div>
              <div>Or play the demo drive to see detection on real dashcam footage.</div>
            </div>
          )}
          {emergency && (
            <div className="fall-banner" role="alertdialog" aria-live="assertive">
              <Siren size={30} weight="fill" className="fall-icon" />
              {emergency.snapshot_url && <img src={emergency.snapshot_url} alt="Snapshot of the fall" />}
              <div className="fall-txt">
                <b>Fall detected near pothole {PREFIX.pothole} {emergency.pothole_id}</b>
                <span>Emergency 112 notified (mock, not dialled). Check on the person now.</span>
                {ackErr && <span className="fall-err">{ackErr}</span>}
              </div>
              <div className="fall-actions">
                <button className="btn" onClick={acknowledge}><CheckCircle size={16} weight="fill" /> Acknowledge</button>
                <button className="btn" onClick={() => window.open(emergency.snapshot_url, '_blank', 'noopener')}><ImageSquare size={16} weight="fill" /> Open alert</button>
              </div>
            </div>
          )}
          {ahead && (
            <div className="ahead-banner" role="alert">
              <Warning size={22} weight="fill" />
              <span>Pothole ahead</span>
              <b>{ahead}</b>
            </div>
          )}
          <div className="hud">
            <div><b>{fps}</b><span>fps</span></div>
            <div><b>{msg?.infer_ms ?? '-'}</b><span>ms</span></div>
            <div><b>{msg?.unique ?? 0}</b><span>unique</span></div>
            <div><b>{msg?.frame ?? 0}</b><span>frames</span></div>
          </div>
        </div>
        <div className="live-controls">
          <button className="btn" disabled={src === 'none'} onClick={togglePause}>{isLive ? <><Pause size={15} weight="fill" /> Pause</> : <><Play size={15} weight="fill" /> Resume</>}</button>
          <button className="btn" disabled={!ws.current} onClick={reset}><ArrowCounterClockwise size={15} weight="bold" /> Reset IDs</button>
          <div className="seg">
            <button className={!cracks ? 'on' : ''} onClick={() => setMode(false)}><Lightning size={14} weight="fill" /> Potholes only</button>
            <button className={cracks ? 'on' : ''} onClick={() => setMode(true)}>All damage</button>
          </div>
          <button className="btn" onClick={() => setSound((x) => !x)} aria-pressed={sound} title="Warning sound for potholes ahead and the emergency siren">
            {sound ? <SpeakerHigh size={15} weight="fill" /> : <SpeakerSlash size={15} weight="fill" />} {sound ? 'Sound on' : 'Sound off'}
          </button>
          <span className="spacer" />
          <div className="legend">
            {Object.entries(CLASS_COLOR).map(([k, c]) => (
              <span key={k}><i style={{ background: c }} />{label(k)} <b className="mono">{msg?.by_class?.[k] ?? 0}</b></span>
            ))}
          </div>
        </div>
      </div>

      <aside className="live-side">
        <div className="side-h">
          <span>Tracked defects</span>
          <span className="count">{list.length}</span>
        </div>
        <div className="cards">
          {list.length === 0 && <div className="empty">A defect is listed after the camera has seen it in three frames.</div>}
          {list.map((t) => (
            <div key={t.id} className={`dcard ${visible.has(t.id) ? 'vis' : ''}`} style={{ ['--cls' as any]: CLASS_COLOR[t.cls] }}>
              <div className="row">
                <b style={{ color: CLASS_COLOR[t.cls] }}>{PREFIX[t.cls]} {t.id}</b>
                <span>{label(t.cls)}</span>
                <span className="spacer" />
                <span className="riskbadge" style={{ background: RISK_COL[t.risk] }}>{Math.round(t.risk_score)}</span>
              </div>
              <div className="meter"><div style={{ width: `${Math.round(t.sev * 100)}%`, background: SEV_COL[t.severity] ?? '#8a9097' }} /></div>
              <div className="dmeta">
                <span>{t.severity} severity</span>
                <span>size {Math.round(t.size * 100)}</span>
                <span>depth {Math.round(t.depth * 100)}</span>
                <span>{t.hits} frames</span>
              </div>
              {t.risk_parts && (
                <div className="parts">
                  {Object.entries(t.risk_parts).filter(([, v]) => v > 0).map(([k, v]) => (
                    <span key={k} title={k}>{k.replace('_', ' ')} <b>{v}</b></span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="save-box">
          <div className="grid g2" style={{ gap: 6 }}>
            <input placeholder="Road name" value={meta.road_name} onChange={(e) => setMeta({ ...meta, road_name: e.target.value })} />
            <button className="btn sm" onClick={gps}><MapPin size={14} weight="fill" /> {loc ? `${loc[0].toFixed(4)}, ${loc[1].toFixed(4)}` : 'Use my location'}</button>
            <select value={meta.road_type} onChange={(e) => setMeta({ ...meta, road_type: e.target.value })}>
              {['unknown', 'highway', 'arterial', 'collector', 'local'].map((x) => <option key={x} value={x}>road: {x}</option>)}
            </select>
            <select value={meta.traffic_level} onChange={(e) => setMeta({ ...meta, traffic_level: e.target.value })}>
              {['unknown', 'high', 'medium', 'low'].map((x) => <option key={x} value={x}>traffic: {x}</option>)}
            </select>
          </div>
          <button className="btn primary wide" disabled={!ws.current || !msg?.unique} onClick={save}><FloppyDisk size={16} weight="fill" /> Save {msg?.unique ?? 0} defects to registry</button>
          {saved && (
            <div className="note">
              {saved.inspection_id ? (
                <>Saved as inspection #{saved.inspection_id}. {saved.defects.filter((d: any) => d.duplicate).length} matched existing records.</>
              ) : 'Nothing confirmed to save.'}
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}
