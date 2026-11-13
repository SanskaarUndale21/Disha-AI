import { useEffect, useMemo, useState } from 'react'
import { CaretDown, CaretRight, Calculator, Wrench } from '@phosphor-icons/react'
import { inr, label, ops, type BudgetPlan, type CostRow } from '../api'
import { DefectDrawer, Pill, Risk } from '../components'
import { useLiveRefresh } from '../events'
import { Tile } from '../icons'

const num = (v: unknown, d = 1) => (typeof v === 'number' && isFinite(v) ? v.toFixed(d) : '-')
const pretty = (k: string) => {
  const s = k.replace(/_/g, ' ').trim()
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function RateValue({ v }: { v: any }) {
  if (v == null) return <span className="muted">-</span>
  if (Array.isArray(v))
    return (
      <ul className="rp-list">
        {v.map((x, i) => <li key={i}>{typeof x === 'object' ? JSON.stringify(x) : String(x)}</li>)}
      </ul>
    )
  if (typeof v === 'object')
    return (
      <table className="t rp-sub">
        <tbody>
          {Object.entries(v).map(([k, x]) => (
            <tr key={k}><td className="muted">{pretty(k)}</td><td className="mono"><RateValue v={x} /></td></tr>
          ))}
        </tbody>
      </table>
    )
  if (typeof v === 'number') return <span className="mono">{v.toLocaleString('en-IN')}</span>
  return <span>{String(v)}</span>
}

export default function Repairs() {
  const [rows, setRows] = useState<CostRow[]>([])
  const [loaded, setLoaded] = useState(false)
  const [err, setErr] = useState('')
  const [budget, setBudget] = useState(50000)
  const [plan, setPlan] = useState<BudgetPlan | null>(null)
  const [planErr, setPlanErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [view, setView] = useState<'all' | 'plan'>('all')
  const [rates, setRates] = useState<Record<string, any> | null>(null)
  const [ratesErr, setRatesErr] = useState('')
  const [showRates, setShowRates] = useState(false)
  const [sel, setSel] = useState<number | null>(null)

  const load = () =>
    ops
      .costs('active')
      .then((r) => {
        setRows(Array.isArray(r) ? r : [])
        setErr('')
      })
      .catch((e) => setErr(e?.message || 'Could not load repair costs'))
      .finally(() => setLoaded(true))

  useEffect(() => {
    load()
  }, [])
  useLiveRefresh(['defect.'], load)

  const openRates = () => {
    setShowRates((x) => !x)
    if (!rates && !ratesErr)
      ops.rates().then((r) => setRates(r ?? {})).catch((e) => setRatesErr(e?.message || 'Could not load rates'))
  }

  const runPlan = async () => {
    setBusy(true)
    setPlanErr('')
    try {
      const p = await ops.budget(Math.max(0, Number(budget) || 0))
      setPlan({ ...p, selected: Array.isArray(p?.selected) ? p.selected : [] })
      setView('plan')
    } catch (e: any) {
      setPlanErr(e?.message || 'Could not plan repairs')
    } finally {
      setBusy(false)
    }
  }

  const total = useMemo(() => rows.reduce((a, r) => a + (r.total_cost || 0), 0), [rows])
  const inPlan = useMemo(() => new Set((plan?.selected ?? []).map((r) => r.defect_id)), [plan])
  const share = plan && plan.risk_total > 0 ? Math.min(1, plan.risk_covered / plan.risk_total) : 0
  const shown = view === 'plan' && plan ? (plan.selected.length ? plan.selected : []) : rows

  return (
    <>
      <div className="page-h">
        <div>
          <h1>Repairs and budget</h1>
          <p>Estimated repair cost for every open defect, and the best set to fix within a budget.</p>
        </div>
      </div>

      {err && <div className="err" style={{ marginBottom: 16 }}>Repair costs are not available right now. {err}</div>}

      <div className="grid g4" style={{ marginBottom: 16 }}>
        <div className="card kpi"><div className="l">Open defects with a cost</div><div className="v">{rows.length}</div></div>
        <div className="card kpi"><div className="l">Total estimated cost</div><div className="v">{inr(total)}</div></div>
        <div className="card kpi"><div className="l">Average per defect</div><div className="v">{rows.length ? inr(total / rows.length) : '-'}</div></div>
        <div className="card kpi"><div className="l">High risk defects</div><div className="v">{rows.filter((r) => r.risk_level === 'High').length}</div></div>
      </div>

      <div className="card rp-plan" style={{ marginBottom: 16 }}>
        <div className="rp-plan-in">
          <div className="row" style={{ gap: 12 }}>
            <Tile icon={Calculator} color="#dd7a07" size={34} />
            <div>
              <h3 style={{ margin: 0 }}>Plan within a budget</h3>
              <div className="note">Picks the defects that remove the most risk for the money.</div>
            </div>
          </div>
          <div className="row rp-form">
            <label className="f">
              Budget in rupees
              <input type="number" min={0} step={1000} value={budget} onChange={(e) => setBudget(Number(e.target.value))} onKeyDown={(e) => e.key === 'Enter' && runPlan()} />
            </label>
            <button className="btn primary" disabled={busy} onClick={runPlan}><Wrench size={16} weight="bold" /> {busy ? 'Planning...' : 'Plan repairs'}</button>
          </div>
        </div>
        {planErr && <div className="err" style={{ marginTop: 14 }}>Could not plan repairs. {planErr}</div>}
        {plan && (
          <div className="rp-result">
            <div className="rp-stat"><span>Selected</span><b>{plan.selected.length}</b></div>
            <div className="rp-stat"><span>Cost used</span><b>{inr(plan.total_cost)}</b></div>
            <div className="rp-stat"><span>Budget left</span><b>{inr(plan.left)}</b></div>
            <div className="rp-stat rp-share">
              <span>Share of total risk covered</span>
              <b>{Math.round(share * 100)}%</b>
              <div className="bar rp-bar"><div style={{ width: `${share * 100}%` }} /></div>
            </div>
          </div>
        )}
      </div>

      <div className="card scroll-x" style={{ marginBottom: 16 }}>
        <div className="row" style={{ marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>Cost per defect</h3>
          <span className="spacer" />
          <div className="seg">
            <button className={view === 'all' ? 'on' : ''} onClick={() => setView('all')}>All defects</button>
            <button className={view === 'plan' ? 'on' : ''} disabled={!plan} onClick={() => setView('plan')}>In plan{plan ? ` (${plan.selected.length})` : ''}</button>
          </div>
        </div>
        <table className="t">
          <thead>
            <tr><th></th><th>ID</th><th>Class</th><th>Severity</th><th>Area m2</th><th>Depth cm</th><th>Material</th><th>Total cost</th><th>Risk</th></tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.defect_id} className={`click ${plan && inPlan.has(r.defect_id) ? 'selrow' : ''}`} onClick={() => setSel(r.defect_id)}>
                <td>{r.crop_url ? <img className="thumb" src={r.crop_url} alt="" /> : <div className="thumb" />}</td>
                <td><span className="uid">{r.uid}</span></td>
                <td>{label(r.class_name)}</td>
                <td><Pill v={r.severity} /></td>
                <td className="mono">{num(r.area_m2, 2)}</td>
                <td className="mono">{num(r.depth_cm, 1)}</td>
                <td>{r.material || '-'}</td>
                <td className="mono"><b>{inr(r.total_cost)}</b></td>
                <td><Risk score={r.risk_score} level={r.risk_level} /></td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr><td colSpan={9}><div className="empty">{!loaded ? 'Loading...' : view === 'plan' ? 'Nothing fits in this budget.' : err ? 'No cost data to show.' : 'No open defects need repair.'}</div></td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <button className="rp-toggle" onClick={openRates} aria-expanded={showRates}>
          {showRates ? <CaretDown size={16} weight="bold" /> : <CaretRight size={16} weight="bold" />}
          <span>How costs are estimated</span>
        </button>
        {showRates && (
          <div style={{ marginTop: 12 }}>
            <p className="note" style={{ marginTop: 0 }}>These are planning assumptions, not quotes. Real costs depend on the contractor and site.</p>
            {ratesErr ? (
              <div className="err">Rates are not available right now. {ratesErr}</div>
            ) : !rates ? (
              <div className="muted">Loading...</div>
            ) : Object.keys(rates).length === 0 ? (
              <div className="muted">No rates published.</div>
            ) : (
              <table className="t">
                <tbody>
                  {Object.entries(rates).map(([k, v]) => (
                    <tr key={k}><td className="muted" style={{ width: '32%', verticalAlign: 'top' }}>{pretty(k)}</td><td><RateValue v={v} /></td></tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>

      {sel != null && <DefectDrawer id={sel} onClose={() => setSel(null)} onChanged={load} />}
    </>
  )
}
