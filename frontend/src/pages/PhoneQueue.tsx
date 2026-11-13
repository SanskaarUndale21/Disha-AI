import { Fragment, useEffect, useState } from 'react'
import { CaretDown, CaretRight, ChatText, Copy, DownloadSimple, MapPin, SealCheck } from '@phosphor-icons/react'
import { fmtDate, timeAgo, voice, type PhoneComplaint } from '../api'
import { useLiveRefresh } from '../events'

const VER: Record<string, { label: string; color: string }> = {
  unverified: { label: 'Unverified', color: '#a9abc0' },
  corroborated: { label: 'Corroborated', color: '#b3b6d6' },
  photo_verified: { label: 'Photo verified', color: '#81b29a' },
  field_verified: { label: 'Field verified', color: '#5f9a80' },
}

function VerPill({ v }: { v: string }) {
  const m = VER[v] ?? VER.unverified
  const solid = v === 'field_verified'
  return (
    <span className="pill" style={{ background: solid ? m.color : `color-mix(in srgb, ${m.color} 20%, transparent)`, color: solid ? '#12241b' : `color-mix(in srgb, ${m.color} 50%, var(--ink))` }}>
      {m.label}
    </span>
  )
}

const EXAMPLE = `[
  {
    "caller_name": "Ravi",
    "caller_phone": "9812345621",
    "location_text": "MG Road",
    "landmark": "near Trinity metro",
    "area_city": "Bengaluru",
    "issue_type": "pothole",
    "severity_description": "very deep",
    "call_id": "manual-001"
  }
]`

export default function PhoneQueue() {
  const [filter, setFilter] = useState<'needs_check' | 'all'>('needs_check')
  const [rows, setRows] = useState<PhoneComplaint[]>([])
  const [loaded, setLoaded] = useState(false)
  const [err, setErr] = useState('')
  const [note, setNote] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const [busy, setBusy] = useState<number | 'import' | null>(null)
  const [showImport, setShowImport] = useState(false)
  const [importText, setImportText] = useState('')

  const load = () => {
    voice
      .queue(filter)
      .then((r) => {
        setRows(Array.isArray(r) ? r : [])
        setErr('')
      })
      .catch((e) => setErr(e?.message || 'Could not load phone complaints'))
      .finally(() => setLoaded(true))
  }
  useEffect(load, [filter])
  useLiveRefresh(['complaint.'], load)

  const copy = async (text: string, what: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setNote(`${what} copied.`)
    } catch {
      window.prompt(`Copy the ${what.toLowerCase()}`, text)
    }
  }

  const copySms = async (r: PhoneComplaint) => {
    try {
      const l = await voice.link(r.ticket)
      copy(l.sms_text, 'SMS text')
    } catch (e: any) {
      setErr(e?.message || 'Could not build the SMS text')
    }
  }

  const markField = async (r: PhoneComplaint) => {
    const n = window.prompt(`Field check note for ${r.ticket} (optional)`, '')
    if (n === null) return
    setBusy(r.complaint_id)
    try {
      await voice.verify(r.complaint_id, n)
      setNote(`${r.ticket} marked field verified.`)
      load()
    } catch (e: any) {
      setErr(e?.message || 'Could not mark field verified')
    } finally {
      setBusy(null)
    }
  }

  const doImport = async () => {
    let calls: unknown
    try {
      calls = JSON.parse(importText)
    } catch {
      setErr('That is not valid JSON. Paste an array of call objects.')
      return
    }
    if (!Array.isArray(calls)) calls = [calls]
    setBusy('import')
    try {
      const r = await voice.importCalls(calls as unknown[])
      const failed = r.results.filter((x) => x.error).length
      setNote(`Imported ${r.created} new call${r.created === 1 ? '' : 's'}${failed ? `, ${failed} skipped` : ''}.`)
      setShowImport(false)
      setImportText('')
      setErr('')
      load()
    } catch (e: any) {
      setErr(e?.message || 'Import failed')
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <div className="page-h">
        <div>
          <h1>Phone complaints</h1>
          <p>Calls to the helpline climb a ladder of proof: unverified, corroborated by nearby AI detections or other callers, photo verified by the citizen's upload, then field verified by an officer.</p>
        </div>
        <div className="row">
          {note && <span className="note">{note}</span>}
          <button className="btn" onClick={() => setShowImport((v) => !v)}>
            <DownloadSimple size={16} weight="bold" /> Import calls
          </button>
        </div>
      </div>

      {showImport && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="note" style={{ marginBottom: 8 }}>
            Paste a JSON array of calls when the voice agent could not reach this server. Calls with a known call_id are not duplicated.
          </div>
          <textarea
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            placeholder={EXAMPLE}
            rows={10}
            style={{ width: '100%', fontFamily: 'ui-monospace, monospace', fontSize: 13, padding: 10, borderRadius: 8, border: '1px solid var(--line-2)', background: 'var(--surface)', color: 'var(--ink)', boxSizing: 'border-box' }}
          />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="btn go" disabled={busy === 'import' || !importText.trim()} onClick={doImport}>
              {busy === 'import' ? 'Importing...' : 'Import'}
            </button>
            <button className="btn" onClick={() => setShowImport(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <div className="seg">
            <button className={filter === 'needs_check' ? 'on' : ''} onClick={() => setFilter('needs_check')}>Needs field check</button>
            <button className={filter === 'all' ? 'on' : ''} onClick={() => setFilter('all')}>All</button>
          </div>
          <span className="spacer" />
          <span className="note">{rows.length} shown</span>
        </div>
        {err && <div className="err" style={{ marginBottom: 12 }}>{err}</div>}
        <div style={{ overflowX: 'auto' }}>
          <table className="t">
            <thead>
              <tr>
                <th />
                <th>Ticket</th>
                <th>When</th>
                <th>Caller</th>
                <th>Location</th>
                <th>Issue</th>
                <th>Urgency</th>
                <th>Verification</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isOpen = open === r.complaint_id
                return (
                  <Fragment key={r.complaint_id}>
                    <tr className="click" onClick={() => setOpen(isOpen ? null : r.complaint_id)}>
                      <td style={{ width: 20 }}>{isOpen ? <CaretDown size={14} /> : <CaretRight size={14} />}</td>
                      <td><span className="uid">{r.ticket}</span></td>
                      <td title={fmtDate(r.created_at)}>{timeAgo(r.created_at)}</td>
                      <td>
                        <div>{r.caller_name || 'Unknown'}</div>
                        <div className="note">{r.caller_phone || '-'}</div>
                      </td>
                      <td style={{ maxWidth: 260 }}>
                        <div>{r.location_text || r.address || '-'}</div>
                        {r.landmark && <div className="note">{r.landmark}</div>}
                      </td>
                      <td>{r.issue_type || r.category}</td>
                      <td>{r.urgency === 'high' ? <span className="pill High">High</span> : <span className="pill">Normal</span>}</td>
                      <td title={r.evidence.join('\n')}>
                        <VerPill v={r.verification} />
                        <div className="note">{r.evidence.length} evidence item{r.evidence.length === 1 ? '' : 's'}</div>
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
                          <button className="btn sm" onClick={() => copy(r.upload_url, 'Upload link')} title={r.upload_url}>
                            <Copy size={14} weight="bold" /> Copy upload link
                          </button>
                          <button className="btn sm" onClick={() => copySms(r)} title="Copy a ready-to-send SMS">
                            <ChatText size={14} weight="bold" /> SMS
                          </button>
                          {r.verification !== 'field_verified' && (
                            <button className="btn sm ok" disabled={busy === r.complaint_id} onClick={() => markField(r)}>
                              <SealCheck size={14} weight="bold" /> Mark field verified
                            </button>
                          )}
                          {r.lat != null && r.lon != null && (
                            <a className="btn sm" target="_blank" rel="noreferrer" href={`https://www.openstreetmap.org/?mlat=${r.lat}&mlon=${r.lon}#map=18/${r.lat}/${r.lon}`}>
                              <MapPin size={14} weight="bold" /> Map
                            </a>
                          )}
                        </div>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr>
                        <td />
                        <td colSpan={8}>
                          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
                            <div>
                              <div className="note">Evidence</div>
                              <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                                {r.evidence.map((e, i) => <li key={i}>{e}</li>)}
                              </ul>
                            </div>
                            <div>
                              <div className="note">What the caller said</div>
                              <div>{r.description || '-'}</div>
                              {r.summary && <div className="note" style={{ marginTop: 4 }}>{r.summary}</div>}
                            </div>
                            <div>
                              <div className="note">Resolved address ({r.geocode_source === 'none' ? 'not located' : r.geocode_source})</div>
                              <div>{r.address || '-'}</div>
                              <div className="note" style={{ marginTop: 4 }}>
                                Status {r.status.replace(/_/g, ' ')}, {r.media_count} photo{r.media_count === 1 ? '' : 's'} or video{r.media_count === 1 ? '' : 's'}
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
        {rows.length === 0 && (
          <div className="empty">
            {!loaded ? 'Loading...' : err ? 'Nothing to show.' : filter === 'needs_check' ? 'No phone complaints waiting for a field check.' : 'No phone complaints yet.'}
          </div>
        )}
      </div>
    </>
  )
}
