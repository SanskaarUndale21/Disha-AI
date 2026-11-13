import { useEffect, useState } from 'react'
import { ArrowClockwise, BellRinging, Check, CheckCircle, Info, Warning, WarningOctagon } from '@phosphor-icons/react'
import { fmtDate, ops, timeAgo, type Alert, type AlertSummary } from '../api'
import { DefectDrawer } from '../components'
import { useLiveRefresh } from '../events'
import { Tile } from '../icons'

const TYPE_LABEL: Record<string, string> = {
  high_risk: 'High risk',
  new_defect: 'New defect',
  duplicate: 'Repeat report',
  worsening: 'Getting worse',
  repaired: 'Repaired',
  low_confidence: 'Needs review',
  repeat_road: 'Problem road',
  overdue: 'Overdue repair',
  weather_risk: 'Rain risk',
}
const typeLabel = (t: string) => TYPE_LABEL[t] ?? (t ? t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, ' ') : 'Alert')

const LEVEL_HEX: Record<string, string> = { critical: '#d92d20', warning: '#dd7a07', info: '#1f5fbf' }
const LEVEL_LABEL: Record<string, string> = { critical: 'Critical', warning: 'Warning', info: 'Info' }

const FILTERS = [
  { k: 'open', l: 'Open' },
  { k: 'acknowledged', l: 'Acknowledged' },
  { k: 'resolved', l: 'Resolved' },
  { k: 'all', l: 'All' },
]

export default function Alerts() {
  const [status, setStatus] = useState('open')
  const [rows, setRows] = useState<Alert[]>([])
  const [sum, setSum] = useState<AlertSummary | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [err, setErr] = useState('')
  const [actErr, setActErr] = useState('')
  const [busy, setBusy] = useState<number | 'scan' | null>(null)
  const [scanNote, setScanNote] = useState('')
  const [sel, setSel] = useState<number | null>(null)

  const load = () => {
    ops
      .alerts(status)
      .then((r) => {
        setRows(Array.isArray(r) ? r : [])
        setErr('')
      })
      .catch((e) => setErr(e?.message || 'Could not load alerts'))
      .finally(() => setLoaded(true))
    ops.alertSummary().then(setSum).catch(() => {})
  }
  useEffect(load, [status])
  useLiveRefresh(['alert.'], load)

  const act = async (id: number, s: 'acknowledged' | 'resolved') => {
    setBusy(id)
    setActErr('')
    try {
      await ops.setAlert(id, s)
      load()
    } catch (e: any) {
      setActErr(e?.message || 'Action failed')
    } finally {
      setBusy(null)
    }
  }

  const scan = async () => {
    setBusy('scan')
    setActErr('')
    setScanNote('')
    try {
      const s = await ops.scanAlerts()
      if (s && typeof s.open === 'number') setSum(s)
      setScanNote('Checked just now.')
      load()
    } catch (e: any) {
      setActErr(e?.message || 'Check failed')
    } finally {
      setBusy(null)
    }
  }

  const levels: { k: 'critical' | 'warning' | 'info'; icon: any }[] = [
    { k: 'critical', icon: WarningOctagon },
    { k: 'warning', icon: Warning },
    { k: 'info', icon: Info },
  ]

  return (
    <>
      <div className="page-h">
        <div>
          <h1>Alerts</h1>
          <p>Things that need an officer's attention: dangerous defects, roads getting worse, repairs running late.</p>
        </div>
        <div className="row">
          {scanNote && <span className="note">{scanNote}</span>}
          <button className="btn primary" disabled={busy === 'scan'} onClick={scan}>
            <ArrowClockwise size={16} weight="bold" /> {busy === 'scan' ? 'Checking...' : 'Check now'}
          </button>
        </div>
      </div>

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi al-kpi">
          <Tile icon={BellRinging} color="#16181b" size={34} />
          <div><div className="l">Open</div><div className="v">{sum?.open ?? '-'}</div></div>
        </div>
        {levels.map(({ k, icon }) => (
          <div key={k} className="card kpi al-kpi">
            <Tile icon={icon} color={LEVEL_HEX[k]} size={34} />
            <div><div className="l">{LEVEL_LABEL[k]}</div><div className="v" style={{ color: k === 'info' ? undefined : LEVEL_HEX[k] }}>{sum?.[k] ?? '-'}</div></div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <div className="seg">
            {FILTERS.map((f) => (
              <button key={f.k} className={status === f.k ? 'on' : ''} onClick={() => setStatus(f.k)}>{f.l}</button>
            ))}
          </div>
          <span className="spacer" />
          <span className="note">{rows.length} shown</span>
        </div>
        {err && <div className="err" style={{ marginBottom: 12 }}>Alerts are not available right now. {err}</div>}
        {actErr && <div className="err" style={{ marginBottom: 12 }}>{actErr}</div>}
        <div className="al-list">
          {rows.map((a) => (
            <div key={a.id} className={`al-row ${a.status}`} style={{ ['--lv' as any]: LEVEL_HEX[a.level] ?? '#8a9097' }}>
              <div className="al-main">
                <div className="row" style={{ gap: 10 }}>
                  <span className="al-level">{LEVEL_LABEL[a.level] ?? a.level}</span>
                  <b className="al-type">{typeLabel(a.type)}</b>
                  {a.uid && (
                    <button className="al-uid uid" onClick={() => a.defect_id != null && setSel(a.defect_id)} disabled={a.defect_id == null}>{a.uid}</button>
                  )}
                  {a.status !== 'open' && <span className="pill">{a.status}</span>}
                </div>
                <div className="al-msg">{a.message}</div>
                <div className="note" title={fmtDate(a.created_at)}>{timeAgo(a.created_at)}</div>
              </div>
              <div className="al-act">
                {a.status === 'open' && (
                  <button className="btn sm" disabled={busy === a.id} onClick={() => act(a.id, 'acknowledged')}><Check size={14} weight="bold" /> Acknowledge</button>
                )}
                {a.status !== 'resolved' && (
                  <button className="btn sm" disabled={busy === a.id} onClick={() => act(a.id, 'resolved')}><CheckCircle size={14} weight="bold" /> Resolve</button>
                )}
              </div>
            </div>
          ))}
          {rows.length === 0 && (
            <div className="empty">{!loaded ? 'Loading...' : err ? 'Nothing to show.' : status === 'open' ? 'No open alerts. All clear.' : 'No alerts here.'}</div>
          )}
        </div>
      </div>

      {sel != null && <DefectDrawer id={sel} onClose={() => setSel(null)} />}
    </>
  )
}
