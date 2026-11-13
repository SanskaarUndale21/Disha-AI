import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from './auth'

export type RtEvent = { type: string; data: any; ts: string; audience?: string }
type Listener = (e: RtEvent) => void

const Ctx = createContext<{ connected: boolean; feed: RtEvent[]; subscribe: (fn: Listener) => () => void }>(null as any)
export const useRealtime = () => useContext(Ctx)

/** Re-run `fn` whenever an event whose type starts with one of `prefixes` arrives. */
export function useLiveRefresh(prefixes: string[], fn: () => void) {
  const { subscribe } = useRealtime()
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    let t: any
    return subscribe((e) => {
      if (prefixes.some((p) => e.type.startsWith(p))) {
        clearTimeout(t)
        t = setTimeout(() => ref.current(), 250) // coalesce bursts
      }
    })
  }, [prefixes.join(',')])
}

type Toast = { id: number; title: string; body: string; tone: string; to?: string }

function describe(e: RtEvent): Omit<Toast, 'id'> | null {
  const d = e.data ?? {}
  switch (e.type) {
    case 'complaint.created':
      return { title: `New complaint ${d.ticket ?? ''}`, body: `${d.category ?? 'issue'}: ${(d.description ?? '').slice(0, 70)}`, tone: 'info', to: '/complaints' }
    case 'complaint.updated':
      return { title: `Complaint ${d.ticket ?? ''} updated`, body: `status: ${d.status}`, tone: 'info', to: '/complaints' }
    case 'defect.created':
      return { title: `New ${d.risk_level ?? ''} risk defect ${d.uid}`, body: `${(d.class_name ?? '').replace('_', ' ')}, severity ${d.severity}, risk ${Math.round(d.risk_score ?? 0)}`, tone: d.risk_level === 'High' ? 'high' : 'med', to: '/defects' }
    case 'detection.verified':
      return { title: `${d.uid} ${d.verification}`, body: `by ${d.by ?? 'officer'}`, tone: 'ok' }
    case 'screening.checked':
      if (d.verdict === 'pass') return null
      return d.verdict === 'rate_limited'
        ? { title: 'Device blocked for fake reports', body: d.reason ?? '', tone: 'high', to: '/complaints' }
        : { title: 'Photo refused: no road damage', body: `device ${d.device ?? 'unknown'}`, tone: 'med', to: '/complaints' }
    case 'live.saved':
      return { title: 'Live patrol saved', body: `${d.defects} defects (${d.new} new) from inspection #${d.inspection_id}`, tone: 'ok', to: '/inspections' }
    default:
      return null
  }
}

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const { session, enabled, ready } = useAuth()
  const [connected, setConnected] = useState(false)
  const [feed, setFeed] = useState<RtEvent[]>([])
  const [toasts, setToasts] = useState<Toast[]>([])
  const listeners = useRef(new Set<Listener>())
  const nav = useNavigate()

  useEffect(() => {
    if (!ready) return
    let ws: WebSocket | null = null
    let stop = false
    let retry = 1000
    let ping: any
    const open = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const tok = session?.access_token
      ws = new WebSocket(`${proto}://${location.host}/ws/events${tok ? `?token=${tok}` : ''}`)
      ws.onopen = () => {
        setConnected(true)
        retry = 1000
        ping = setInterval(() => ws?.readyState === 1 && ws.send('ping'), 25000)
      }
      ws.onmessage = (m) => {
        const e = JSON.parse(m.data)
        if (e.type === 'hello') {
          setFeed((e.recent ?? []).slice().reverse())
          return
        }
        setFeed((f) => [e, ...f].slice(0, 60))
        listeners.current.forEach((fn) => fn(e))
        const t = describe(e)
        if (t) {
          const id = Date.now() + Math.random()
          setToasts((x) => [...x.slice(-3), { id, ...t }])
          setTimeout(() => setToasts((x) => x.filter((y) => y.id !== id)), 6000)
        }
      }
      ws.onclose = () => {
        setConnected(false)
        clearInterval(ping)
        if (!stop) setTimeout(open, (retry = Math.min(retry * 2, 15000)))
      }
    }
    open()
    return () => {
      stop = true
      clearInterval(ping)
      ws?.close()
    }
  }, [ready, enabled, session?.access_token])

  const subscribe = (fn: Listener) => {
    listeners.current.add(fn)
    return () => {
      listeners.current.delete(fn)
    }
  }

  return (
    <Ctx.Provider value={{ connected, feed, subscribe }}>
      {children}
      <div className="toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.tone}`} onClick={() => t.to && nav(t.to)}>
            <b>{t.title}</b>
            <span>{t.body}</span>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}
