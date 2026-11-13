import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { Moon, SignIn, SignOut, Sun } from '@phosphor-icons/react'
import { api } from './api'
import { useAuth } from './auth'
import { useLiveRefresh, useRealtime } from './events'
import { NAV_GROUPS, Tile } from './icons'
import Dashboard from './pages/Dashboard'
import Analyze from './pages/Analyze'
import Live from './pages/Live'
import Defects from './pages/Defects'
import Verify from './pages/Verify'
import Progress from './pages/Progress'
import Inspections from './pages/Inspections'
import Model from './pages/Model'
import Complaints from './pages/Complaints'
import Login from './pages/Login'
import Users from './pages/Users'

function Officer({ children }: { children: ReactNode }) {
  const { isOfficer, ready } = useAuth()
  if (!ready) return null
  if (!isOfficer)
    return (
      <div className="login-wrap">
        <div className="card login">
          <img className="logo" src="/logo.svg" alt="" />
          <h2>Officer sign-in required</h2>
          <p>This area holds citizen data and approval actions. Sign in with an officer account to continue.</p>
          <Link className="btn primary wide" to="/login">Sign in</Link>
        </div>
      </div>
    )
  return <>{children}</>
}

function useTheme() {
  const [theme, setTheme] = useState<string>(() => {
    try {
      return localStorage.getItem('rw-theme') ?? 'light'
    } catch {
      return 'auto'
    }
  })
  useEffect(() => {
    const el = document.documentElement
    if (theme === 'auto') el.removeAttribute('data-theme')
    else el.setAttribute('data-theme', theme)
    try {
      localStorage.setItem('rw-theme', theme)
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new Event('rw-theme'))
  }, [theme])
  const dark = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  return { dark, toggle: () => setTheme(dark ? 'light' : 'dark') }
}

export default function App() {
  const { profile, enabled, signOut, isAdmin, isOfficer } = useAuth()
  const { connected } = useRealtime()
  const { dark, toggle } = useTheme()
  const [badges, setBadges] = useState<Record<string, number>>({})
  const loc = useLocation()
  const loadBadges = () => {
    api.stats().then((s) => setBadges((b) => ({ ...b, pending: s.pending_verification }))).catch(() => {})
    if (isOfficer)
      api.complaints('?status=submitted').then((r) => setBadges((b) => ({ ...b, complaints: r.length }))).catch(() => {})
  }
  useEffect(loadBadges, [isOfficer])
  useLiveRefresh(['complaint.', 'detection.', 'inspection.'], loadBadges)
  const initials = (profile?.full_name || profile?.email || '?').split(/[\s@.]/).filter(Boolean).slice(0, 2).map((x) => x[0]?.toUpperCase()).join('')
  const flush = loc.pathname === '/'

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <img src="/logo.svg" alt="" />
          <div>
            <b>RoadWatch</b>
            <small>Municipal road console</small>
          </div>
        </div>
        {NAV_GROUPS.map((g) => (
          <div key={g.title}>
            <div className="nav-group">{g.title}</div>
            <nav className="nav">
              {g.items.filter((n) => !n.admin || isAdmin).map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === '/'}>
                  <Tile icon={n.icon} color={n.color} />
                  <span className="lbl">{n.label}</span>
                  {n.badge && badges[n.badge] ? <span className="badge">{badges[n.badge]}</span> : null}
                </NavLink>
              ))}
            </nav>
          </div>
        ))}
        <div className="foot">
          <div className="status-line">
            <span className={`dot ${connected ? 'ok' : ''}`} />
            <span>{connected ? 'Live updates on' : 'Reconnecting'}</span>
            <span className="spacer" />
            <button className="icon-btn" onClick={toggle} aria-label="Toggle appearance" title="Toggle appearance">
              {dark ? <Sun size={16} weight="bold" /> : <Moon size={16} weight="bold" />}
            </button>
          </div>
          {enabled &&
            (profile ? (
              <div className="userbox">
                <div className="avatar">{initials}</div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div className="who">{profile.full_name || profile.email}</div>
                  <div className="role">{profile.role}{profile.ward ? `, ${profile.ward}` : ''}</div>
                </div>
                <button className="icon-btn" onClick={signOut} aria-label="Sign out" title="Sign out"><SignOut size={16} weight="bold" /></button>
              </div>
            ) : (
              <Link className="btn primary wide" to="/login"><SignIn size={16} weight="bold" /> Officer sign in</Link>
            ))}
        </div>
      </aside>
      <main className={`main ${flush ? 'flush' : ''}`}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/live" element={<Live />} />
          <Route path="/complaints" element={<Officer><Complaints /></Officer>} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/defects" element={<Defects />} />
          <Route path="/verify" element={<Officer><Verify /></Officer>} />
          <Route path="/progress" element={<Progress />} />
          <Route path="/inspections" element={<Inspections />} />
          <Route path="/model" element={<Model />} />
          <Route path="/login" element={<Login />} />
          <Route path="/users" element={<Officer><Users /></Officer>} />
        </Routes>
      </main>
    </div>
  )
}
