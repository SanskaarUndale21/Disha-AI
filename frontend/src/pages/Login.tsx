import { useState } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth'

export default function Login() {
  const { session, profile, signIn, signUp, enabled } = useAuth()
  const [mode, setMode] = useState<'in' | 'up'>('in')
  const [f, setF] = useState({ email: '', password: '', name: '' })
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  if (!enabled) return <div className="card">Authentication is not configured on the server.</div>
  if (session && profile && profile.role !== 'citizen') return <Navigate to="/" replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setErr('')
    setMsg('')
    try {
      if (mode === 'in') await signIn(f.email, f.password)
      else setMsg(await signUp(f.email, f.password, f.name))
    } catch (e: any) {
      setErr(e.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <img className="logo" src="/logo.svg" alt="" />
        <h2>Sign in to the admin panel</h2>
        <p>Use your municipal account. New accounts get officer access once an administrator approves them.</p>
        <p className="note"><b>Citizens:</b> use the citizen portal at <a href="http://localhost:5174">http://localhost:5174</a></p>
        {session && profile?.role === 'citizen' && (
          <div className="err">{profile.email} does not have officer access yet. Ask an administrator to approve it.</div>
        )}
        <div className="seg">
          <button type="button" className={mode === 'in' ? 'on' : ''} onClick={() => setMode('in')}>Sign in</button>
          <button type="button" className={mode === 'up' ? 'on' : ''} onClick={() => setMode('up')}>Create account</button>
        </div>
        {mode === 'up' && (
          <label className="f">Full name<input required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        )}
        <label className="f">Email<input type="email" required autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
        <label className="f">Password<input type="password" required minLength={6} autoComplete={mode === 'in' ? 'current-password' : 'new-password'} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></label>
        <button className="btn primary wide" disabled={busy}>{busy ? 'Please wait...' : mode === 'in' ? 'Sign in' : 'Create account'}</button>
        {msg && <div className="note">{msg}</div>}
        {err && <div className="err">{err}</div>}
      </form>
    </div>
  )
}
