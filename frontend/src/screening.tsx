import { useEffect, useState } from 'react'
import { CheckCircle, Prohibit, ShieldWarning, XCircle } from '@phosphor-icons/react'
import { label } from './api'
import { useLiveRefresh } from './events'
import { Tile } from './icons'

type Check = {
  id: number
  created_at: string
  verdict: 'pass' | 'fail' | 'rate_limited'
  reason: string
  media_type: string | null
  max_confidence: number | null
  damage: { class: string; confidence: number; severity?: string }[]
  complaint_id: number | null
  source: string
  device: string | null
  phone: string | null
  preview_url: string | null
}
type Stats = {
  last_24h: number
  passed: number
  failed: number
  rate_limited: number
  pass_rate: number | null
  flagged_devices: { device: string; fails: number; blocked_attempts: number; last: string }[]
  rules: { fail_limit: number; window_min: number; block_min: number }
}

const V = {
  pass: { text: 'Damage found', color: '#2e9a57', icon: CheckCircle },
  fail: { text: 'No damage', color: '#d92d20', icon: XCircle },
  rate_limited: { text: 'Blocked', color: '#5d636b', icon: Prohibit },
} as const

function ago(iso: string) {
  const s = (Date.now() - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

/** Officer view of the pre-submission AI check that stops photos without road damage. */
export function ScreeningPanel() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [rows, setRows] = useState<Check[]>([])
  const [filter, setFilter] = useState<'' | 'pass' | 'fail' | 'rate_limited'>('')
  const [err, setErr] = useState('')
  const load = () => {
    fetch('/api/screening/stats').then((r) => r.json()).then(setStats).catch(() => setErr('Screening data is not available.'))
    fetch(`/api/screening/checks?limit=24${filter ? `&verdict=${filter}` : ''}`).then((r) => r.json()).then(setRows).catch(() => {})
  }
  useEffect(load, [filter])
  useLiveRefresh(['screening.'], load)

  return (
    <div className="card scr">
      <div className="row" style={{ marginBottom: 12 }}>
        <Tile icon={ShieldWarning} color="#dd7a07" size={30} />
        <div>
          <h3 style={{ margin: 0 }}>AI screening before submission</h3>
          <div className="note">
            Every photo or video is checked for road damage before a citizen can submit. Plain road is refused, and{' '}
            {stats?.rules.fail_limit ?? 5} refusals within {stats?.rules.window_min ?? 60} minutes pause that device for{' '}
            {stats?.rules.block_min ?? 60} minutes.
          </div>
        </div>
      </div>
      {err && <div className="err">{err}</div>}
      {stats && (
        <div className="scr-stats">
          <button className={`scr-stat ${filter === '' ? 'on' : ''}`} onClick={() => setFilter('')}>
            <b>{stats.last_24h}</b><span>Checks in 24 h</span>
          </button>
          <button className={`scr-stat ${filter === 'pass' ? 'on' : ''}`} onClick={() => setFilter('pass')}>
            <b style={{ color: V.pass.color }}>{stats.passed}</b><span>Damage found</span>
          </button>
          <button className={`scr-stat ${filter === 'fail' ? 'on' : ''}`} onClick={() => setFilter('fail')}>
            <b style={{ color: V.fail.color }}>{stats.failed}</b><span>Refused, no damage</span>
          </button>
          <button className={`scr-stat ${filter === 'rate_limited' ? 'on' : ''}`} onClick={() => setFilter('rate_limited')}>
            <b>{stats.rate_limited}</b><span>Blocked attempts</span>
          </button>
          <div className="scr-stat static">
            <b>{stats.pass_rate == null ? '-' : `${Math.round(stats.pass_rate * 100)}%`}</b><span>Genuine rate</span>
          </div>
        </div>
      )}
      <div className="scr-grid">
        {rows.length === 0 && <div className="empty">No checks yet. They appear here live as citizens add photos.</div>}
        {rows.map((c) => {
          const v = V[c.verdict]
          const Icon = v.icon
          return (
            <div key={c.id} className="scr-item">
              <div className="scr-img">
                {c.preview_url ? <img src={c.preview_url} alt="" loading="lazy" /> : <div className="scr-noimg">No preview</div>}
                <span className="scr-badge" style={{ background: v.color }}><Icon size={13} weight="fill" /> {v.text}</span>
              </div>
              <div className="scr-meta">
                <div className="scr-reason">
                  {c.verdict === 'pass' && c.damage.length
                    ? c.damage.slice(0, 3).map((d) => `${label(d.class)} ${Math.round(d.confidence * 100)}%`).join(', ')
                    : c.reason}
                </div>
                <div className="note">
                  {ago(c.created_at)}
                  {c.device ? `, device ${c.device}` : c.phone ? `, ${c.phone}` : ''}
                  {c.source === 'server' ? ', checked at submit' : ''}
                  {c.complaint_id ? `, complaint ${c.complaint_id}` : ''}
                </div>
              </div>
            </div>
          )
        })}
      </div>
      {stats && stats.flagged_devices.length > 0 && (
        <div className="scr-flags">
          <b>Devices sending photos without damage</b>
          {stats.flagged_devices.map((d) => (
            <span key={d.device} className="pill High">
              {d.device}: {d.fails} refused{d.blocked_attempts ? `, ${d.blocked_attempts} blocked` : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
