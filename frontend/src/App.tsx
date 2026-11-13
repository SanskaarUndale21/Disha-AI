import { useEffect, useState, type ReactNode } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { ArrowSquareOut, BellRinging, ChatCircleText, DotsThreeOutline, List, MapPinArea, MapTrifold, Moon, SignIn, SignOut, Sun, UsersThree, VideoCamera, X } from '@phosphor-icons/react'
import { api, ops, panelUrl, voice } from './api'
import { AlarmControl } from './alarm'
import { useAuth } from './auth'
import { useLiveRefresh, useRealtime } from './events'
import { NAV_GROUPS, Tile } from './icons'
import Dashboard from './pages/Dashboard'
import Analyze from './pages/Analyze'
import Live from './pages/Live'
import LiveMap from './pages/LiveMap'
import Defects from './pages/Defects'
import Verify from './pages/Verify'
import Progress from './pages/Progress'
import Inspections from './pages/Inspections'
import Model from './pages/Model'
import Complaints from './pages/Complaints'
import Login from './pages/Login'
import Users from './pages/Users'
import Repairs from './pages/Repairs'
import Alerts from './pages/Alerts'
import PhoneQueue from './pages/PhoneQueue'

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

/** Admin panel only: when sign-in is enabled every page except /login needs an officer or admin account. */
function AdminGate({ children }: { children: ReactNode }) {
  const { enabled, ready, isOfficer } = useAuth()
  if (!enabled) return <>{children}</>
  if (!ready) return null
  if (!isOfficer) return <Navigate to="/login" replace />
  return <>{children}</>
}

const TABS: { to: string; icon: any; short: string; badge?: string }[] = [
  { to: '/', icon: MapTrifold, short: 'Home' },
  { to: '/map', icon: MapPinArea, short: 'Map' },
  { to: '/alerts', icon: BellRinging, short: 'Alerts', badge: 'alerts' },
  { to: '/live', icon: VideoCamera, short: 'Patrol' },
  { to: '/complaints', icon: ChatCircleText, short: 'Reports', badge: 'complaints' },
]

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
    ops.alertSummary().then((s) => setBadges((b) => ({ ...b, alerts: (s?.critical ?? 0) + (s?.warning ?? 0) }))).catch(() => {})
    voice.count().then((r) => setBadges((b) => ({ ...b, phone: r?.needs_check ?? 0 }))).catch(() => {})
  }
  useEffect(loadBadges, [isOfficer])
  useLiveRefresh(['complaint.', 'detection.', 'inspection.', 'alert.'], loadBadges)
  const initials = (profile?.full_name || profile?.email || '?').split(/[\s@.]/).filter(Boolean).slice(0, 2).map((x) => x[0]?.toUpperCase()).join('')
  const flush = loc.pathname === '/' || loc.pathname === '/map'
  const isMap = loc.pathname === '/map'
  const [menu, setMenu] = useState(false)
  useEffect(() => setMenu(false), [loc.pathname])
  useEffect(() => {
    if (!menu) return
    const k = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(false)
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [menu])
  const title = NAV_GROUPS.flatMap((g) => g.items).find((n) => (n.to === '/' ? loc.pathname === '/' : loc.pathname.startsWith(n.to)))?.label ?? 'Disha AI'

  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <header className="topbar">
        <button className="icon-btn" onClick={() => setMenu(true)} aria-label="Open menu" aria-expanded={menu}><List size={18} weight="bold" /></button>
        <img src="/logo.svg" alt="" />
        <b>{title}</b>
        <span className="spacer" />
        <a className="btn sm go tb-link" href={panelUrl(5175)} target="_blank" rel="noopener noreferrer"><ArrowSquareOut size={14} weight="bold" /> Feed panel</a>
        <AlarmControl />
        <button className="icon-btn tb-theme" onClick={toggle} aria-label="Toggle appearance">{dark ? <Sun size={16} weight="bold" /> : <Moon size={16} weight="bold" />}</button>
      </header>
      {menu && <div className="side-scrim" onClick={() => setMenu(false)} />}
      <aside className={`side ${menu ? 'open' : ''}`}>
        <button className="icon-btn side-close" onClick={() => setMenu(false)} aria-label="Close menu"><X size={16} weight="bold" /></button>
        <div className="brand">
          <img src="/logo.svg" alt="" />
          <div>
            <b>Disha AI</b>
            <small>Admin panel</small>
          </div>
        </div>
        {NAV_GROUPS.map((g) => (
          <div key={g.title}>
            <div className="nav-group">{g.title}</div>
            <nav className="nav" aria-label={g.title}>
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
        <div className="ext-links">
          <a className="feed-link" href={panelUrl(5175)} target="_blank" rel="noopener noreferrer"><ArrowSquareOut size={18} weight="bold" /> <span><b>Open Feed panel</b><small>Field feed, port 5175</small></span></a>
          <a className="cit-link" href={panelUrl(5174)} target="_blank" rel="noopener noreferrer"><UsersThree size={16} weight="bold" /> Citizen portal</a>
        </div>
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
      <nav className="tabbar" aria-label="Main">
        {TABS.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'} className="tab">
            <n.icon size={24} weight="duotone" />
            <span>{n.short}</span>
            {n.badge && badges[n.badge] ? <i className="tb-badge">{badges[n.badge]}</i> : null}
          </NavLink>
        ))}
        <button className={`tab ${menu ? 'on' : ''}`} onClick={() => setMenu(true)} aria-label="More">
          <DotsThreeOutline size={24} weight="duotone" />
          <span>More</span>
        </button>
      </nav>
      <main id="main" className={`main ${flush ? 'flush' : ''} ${isMap ? 'map-page' : ''}`}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<AdminGate><AdminRoutes /></AdminGate>} />
        </Routes>
      </main>
    </div>
  )
}

function AdminRoutes() {
  const loc = useLocation()
  return (
    <div key={loc.pathname} className="page-anim">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/map" element={<LiveMap />} />
          <Route path="/live" element={<Live />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/repairs" element={<Repairs />} />
          <Route path="/complaints" element={<Officer><Complaints /></Officer>} />
          <Route path="/phone" element={<Officer><PhoneQueue /></Officer>} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/defects" element={<Defects />} />
          <Route path="/verify" element={<Officer><Verify /></Officer>} />
          <Route path="/progress" element={<Progress />} />
          <Route path="/inspections" element={<Inspections />} />
          <Route path="/model" element={<Model />} />
          <Route path="/users" element={<Officer><Users /></Officer>} />
        </Routes>
    </div>
  )
}
