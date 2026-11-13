import { useEffect, useState } from 'react'
import { Certificate, RoadHorizon } from '@phosphor-icons/react'
import { roads, type RoadRecordData } from './api'
import { Tile } from './icons'

const cr = (n?: number) => (n == null ? '-' : `Rs ${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })} crore`)

/** Road asset record: who built it, when, for how much, and whether the contractor still owes free repairs. */
export function RoadRecord({ lat, lon, defectId }: { lat?: number | null; lon?: number | null; defectId?: number | null }) {
  const [r, setR] = useState<RoadRecordData | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(true)
  useEffect(() => {
    let live = true
    setBusy(true)
    setErr('')
    setR(null)
    const p = defectId != null ? roads.forDefect(defectId) : lat != null && lon != null ? roads.asset(lat, lon) : null
    if (!p) {
      setBusy(false)
      return
    }
    p.then((x) => live && setR(x))
      .catch((e) => live && setErr(e?.message || 'Road record unavailable'))
      .finally(() => live && setBusy(false))
    return () => {
      live = false
    }
  }, [lat, lon, defectId])

  if (defectId == null && (lat == null || lon == null)) return null
  const rows: [string, string | undefined][] = r?.found
    ? [
        ['Built', r.built_year ? `${r.built_year}${r.age_years != null ? `, ${r.age_years} years old` : ''}` : undefined],
        ['Contractor', r.contractor],
        ['Scheme', r.scheme_full ? `${r.scheme ?? ''} ${r.scheme ? '(' : ''}${r.scheme_full}${r.scheme ? ')' : ''}` : r.scheme],
        ['Sanctioned cost', r.sanctioned_cost_cr != null ? cr(r.sanctioned_cost_cr) : undefined],
        ['Completed cost', r.completed_cost_cr != null ? cr(r.completed_cost_cr) : undefined],
        ['Length', r.length_km != null ? `${r.length_km} km` : undefined],
        ['Lanes', r.lane_count != null ? String(r.lane_count) : undefined],
        ['Surface', r.surface],
        ['Last resurfaced', r.last_resurfaced_year ? String(r.last_resurfaced_year) : undefined],
        ['Authority', r.authority],
      ]
    : []
  return (
    <div className="card rr-card">
      <div className="row" style={{ marginBottom: 10 }}>
        <Tile icon={RoadHorizon} color="#b3b6d6" />
        <b className="rr-title">Road record</b>
        <span className="spacer" />
        {r?.found && <span className="rr-sample">Sample data for demonstration</span>}
      </div>
      {busy && <div className="skel-stack"><i className="skel" style={{ width: '60%' }} /><i className="skel" style={{ width: '90%' }} /><i className="skel" style={{ width: '75%' }} /></div>}
      {!busy && err && <div className="note">Road record could not be loaded. {err}</div>}
      {!busy && !err && r && !r.found && <div className="note">No road record matches this location yet.</div>}
      {r?.found && (
        <>
          <div className="rr-name">
            {r.name}
            {r.ref && <span className="pill">{r.ref}</span>}
          </div>
          <div className={`rr-banner ${r.under_liability ? 'ok' : ''}`}>
            <Certificate size={20} weight="duotone" />
            <span>
              {r.under_liability
                ? `Contractor is liable for free repairs until ${r.defect_liability_until ?? 'the end of the liability period'}`
                : r.liability_note || 'Defect liability period has ended. Repairs are paid from the maintenance budget.'}
            </span>
          </div>
          {r.under_liability && r.liability_note && <div className="note" style={{ marginTop: 4 }}>{r.liability_note}</div>}
          <dl className="rr-dl">
            {rows.filter(([, v]) => v).map(([k, v]) => (
              <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
            ))}
          </dl>
          <div className="rr-note">{r.disclaimer || 'Sample data for demonstration. Not an official record.'}</div>
        </>
      )}
    </div>
  )
}
