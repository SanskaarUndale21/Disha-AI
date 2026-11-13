import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { BellRinging, MapPin, SpeakerHigh, SpeakerSlash, Siren, X } from '@phosphor-icons/react'
import { safety, type Emergency } from './api'
import { useRealtime } from './events'

const KEY = 'rw-alarm-sound'
type AlarmCtx = { enabled: boolean; enable: () => void; disable: () => void; test: () => void; testing: boolean }
const Ctx = createContext<AlarmCtx>(null as any)
export const useAlarm = () => useContext(Ctx)

export function AlarmProvider({ children }: { children: ReactNode }) {
  const { subscribe } = useRealtime()
  const loc = useLocation()
  const [enabled, setEnabled] = useState(() => {
    try {
      return localStorage.getItem(KEY) === '1'
    } catch {
      return false
    }
  })
  const [alarms, setAlarms] = useState<Emergency[]>([])
  const [testing, setTesting] = useState(false)
  const [err, setErr] = useState('')
  const ctxRef = useRef<AudioContext | null>(null)
  const sirenRef = useRef<{ osc: OscillatorNode; gain: GainNode; timer: any } | null>(null)

  const audio = () => {
    const AC = window.AudioContext || (window as any).webkitAudioContext
    if (!AC) return null
    const c = ctxRef.current ?? (ctxRef.current = new AC())
    if (c.state === 'suspended') c.resume().catch(() => {})
    return c
  }
  const stop = useCallback(() => {
    const s = sirenRef.current
    if (!s) return
    clearInterval(s.timer)
    try {
      s.gain.gain.setTargetAtTime(0.0001, s.osc.context.currentTime, 0.03)
      s.osc.stop(s.osc.context.currentTime + 0.1)
    } catch {
      /* stopped */
    }
    sirenRef.current = null
  }, [])
  const start = useCallback(() => {
    if (sirenRef.current) return
    try {
      const c = audio()
      if (!c) return
      const osc = c.createOscillator()
      const gain = c.createGain()
      osc.type = 'square'
      osc.frequency.value = 600
      gain.gain.value = 0.35
      osc.connect(gain).connect(c.destination)
      osc.start()
      let hi = false
      const timer = setInterval(() => {
        hi = !hi
        osc.frequency.setValueAtTime(hi ? 1000 : 600, c.currentTime)
      }, 380)
      sirenRef.current = { osc, gain, timer }
    } catch {
      /* audio unavailable */
    }
  }, [])

  // the Live patrol page runs its own siren for the same event, so stay quiet there
  const onLive = loc.pathname.startsWith('/live')
  const ringing = enabled && ((alarms.length > 0 && !onLive) || testing)
  useEffect(() => {
    if (ringing) start()
    else stop()
    return stop
  }, [ringing, start, stop])

  useEffect(
    () =>
      subscribe((e) => {
        const d = e.data ?? {}
        if (e.type === 'emergency.fall') {
          const em: Emergency = {
            id: d.id,
            message: d.message ?? 'Fall detected near a pothole',
            level: d.level,
            status: 'open',
            snapshot_url: d.snapshot_url ?? null,
            lat: d.lat ?? null,
            lon: d.lon ?? null,
            pothole_id: d.pothole_id ?? null,
            created_at: d.created_at ?? new Date().toISOString(),
          }
          setAlarms((a) => (a.some((x) => x.id === em.id) ? a : [em, ...a]))
        } else if (e.type.startsWith('emergency.') && d.id != null) {
          setAlarms((a) => a.filter((x) => x.id !== d.id))
        }
      }),
    [subscribe],
  )

  const enable = () => {
    audio()
    try {
      localStorage.setItem(KEY, '1')
    } catch {
      /* ignore */
    }
    setEnabled(true)
  }
  const disable = () => {
    try {
      localStorage.setItem(KEY, '0')
    } catch {
      /* ignore */
    }
    setEnabled(false)
  }
  const test = () => {
    if (!enabled) enable()
    audio()
    setTesting(true)
    setTimeout(() => setTesting(false), 3000)
  }
  const ack = async (id: number) => {
    setErr('')
    try {
      await safety.ack(id)
      setAlarms((a) => a.filter((x) => x.id !== id))
    } catch (e: any) {
      setErr(`Could not acknowledge: ${e?.message ?? 'failed'}`)
    }
  }

  const top = alarms[0]
  const alarmRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const root = document.documentElement
    const el = alarmRef.current
    if (!top || !el) {
      root.style.setProperty('--alarm-h', '0px')
      return
    }
    const set = () => root.style.setProperty('--alarm-h', `${el.offsetHeight}px`)
    set()
    const ro = new ResizeObserver(set)
    ro.observe(el)
    return () => {
      ro.disconnect()
      root.style.setProperty('--alarm-h', '0px')
    }
  }, [!!top])
  return (
    <Ctx.Provider value={{ enabled, enable, disable, test, testing }}>
      {top && (
        <div className="fall-alarm" ref={alarmRef} role="alertdialog" aria-live="assertive" aria-label="Fall emergency">
          <Siren size={38} weight="fill" className="fa-icon" />
          {top.snapshot_url && (
            <a href={top.snapshot_url} target="_blank" rel="noopener noreferrer"><img src={top.snapshot_url} alt="Snapshot of the fall" /></a>
          )}
          <div className="fa-txt">
            <b>EMERGENCY: fall detected{alarms.length > 1 ? ` (${alarms.length} active)` : ''}</b>
            <span>{top.message}</span>
            {top.lat != null && top.lon != null && (
              <a href={`https://www.google.com/maps?q=${top.lat},${top.lon}`} target="_blank" rel="noopener noreferrer">
                <MapPin size={14} weight="fill" /> {top.lat.toFixed(5)}, {top.lon.toFixed(5)}
              </a>
            )}
            {err && <span className="fa-err">{err}</span>}
            {!enabled && <span className="fa-err">Sound is off. Use Enable alarm sound in the top bar.</span>}
          </div>
          <div className="fa-actions">
            <button className="btn" onClick={() => ack(top.id)}>Acknowledge</button>
            <button className="btn ghost" onClick={() => setAlarms((a) => a.filter((x) => x.id !== top.id))}><X size={14} weight="bold" /> Dismiss</button>
          </div>
        </div>
      )}
      {children}
    </Ctx.Provider>
  )
}

export function AlarmControl() {
  const { enabled, enable, disable, test } = useAlarm()
  return (
    <div className="alarm-ctl">
      {enabled ? (
        <button className="btn sm" onClick={disable} title="Alarm sound is on, click to mute"><SpeakerHigh size={15} weight="fill" /> <span className="hide-sm">Alarm on</span></button>
      ) : (
        <button className="btn sm go" onClick={enable} aria-label="Enable alarm sound" title="Enable alarm sound"><SpeakerSlash size={15} weight="fill" /> <span className="hide-sm">Enable alarm sound</span></button>
      )}
      <button className="btn sm" onClick={test} aria-label="Test alarm" title="Test alarm"><BellRinging size={15} weight="fill" /> <span className="hide-sm">Test alarm</span></button>
    </div>
  )
}
