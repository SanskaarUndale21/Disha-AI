import { useEffect, useState } from 'react'
import { api, fmtDate } from '../api'
import { useAuth, type Profile } from '../auth'

export default function Users() {
  const { profile, isAdmin } = useAuth()
  const [rows, setRows] = useState<Profile[]>([])
  const [role, setRole] = useState('')
  const [err, setErr] = useState('')
  const load = () => api.users(role).then(setRows).catch((e) => setErr(e.message))
  useEffect(() => {
    if (isAdmin) load()
  }, [role, isAdmin])
  if (!isAdmin) return <div className="card">Admin access required.</div>
  const patch = async (id: string, body: any) => {
    setErr('')
    try {
      await api.patchUser(id, body)
      load()
    } catch (e: any) {
      setErr(e.message)
    }
  }
  return (
    <>
      <div className="page-h">
        <div>
          <h1>Users and roles</h1>
          <p>Everyone who has signed in (dashboard or citizen app). Promote officers and assign their ward.</p>
        </div>
        <select value={role} onChange={(e) => setRole(e.target.value)}>
          <option value="">all roles</option>
          {['citizen', 'officer', 'admin'].map((r) => <option key={r}>{r}</option>)}
        </select>
      </div>
      {err && <div className="err" style={{ marginBottom: 10 }}>{err}</div>}
      <div className="card scroll-x">
        <table className="t">
          <thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Role</th><th>Ward</th><th>Active</th><th>Last seen</th></tr></thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id}>
                <td>{u.full_name ?? '-'}</td>
                <td className="mono">{u.email}</td>
                <td>{u.phone ?? '-'}</td>
                <td>
                  <select value={u.role} disabled={u.id === profile?.id} onChange={(e) => patch(u.id, { role: e.target.value })}>
                    {['citizen', 'officer', 'admin'].map((r) => <option key={r}>{r}</option>)}
                  </select>
                </td>
                <td><input defaultValue={u.ward ?? ''} placeholder="ward / zone" onBlur={(e) => e.target.value !== (u.ward ?? '') && patch(u.id, { ward: e.target.value })} /></td>
                <td><input type="checkbox" checked={u.active} disabled={u.id === profile?.id} onChange={(e) => patch(u.id, { active: e.target.checked })} /></td>
                <td className="note">{fmtDate((u as any).last_seen)}</td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={7} className="muted">No users yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}
