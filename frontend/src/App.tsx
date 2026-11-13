import { Component, useEffect, useState, type ReactNode } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { ArrowSquareOut, BellRinging, ChatCircleText, DotsThreeOutline, MapPinArea, CaretLeft, CaretRight, MapTrifold, Moon, SignIn, SignOut, Sun, UsersThree, VideoCamera } from '@phosphor-icons/react'
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
import Insights from './pages/Insights'
import { DepthFX } from './depth'

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

/** A page that throws shows a plain message instead of a blank screen. */
class Boundary extends Component<{ children: ReactNode; onRetry: () => void }, { bad: boolean }> {
  state = { bad: false }
  static getDerivedStateFromError() { return { bad: true } }
  componentDidCatch(e: unknown) { console.warn('page error', e) }
  render() {
    if (!this.state.bad) return this.props.children
    return (
      <div className="card empty" role="alert">
        <b>This page could not be shown.</b>
        <span>Something unexpected happened while loading it. Your data is safe.</span>
        <button className="btn sm" onClick={() => { this.setState({ bad: false }); this.props.onRetry() }}>Try again</button>
      </div>
    )
  }
}

/** Plain-language notice when a request fails, with a retry that reloads the current page's data. */
function ApiNotice({ onRetry }: { onRetry: () => void }) {
  const [msg, setMsg] = useState('')
  const loc = useLocation()
  useEffect(() => {
    let t: any
    const on = (e: Event) => {
      const d = (e as CustomEvent).detail
      setMsg(d?.message || 'Something went wrong.')
      clearTimeout(t)
      t = setTimeout(() => setMsg(''), 20000)
    }
    window.addEventListener('rw-api-error', on)
    return () => {
      window.removeEventListener('rw-api-error', on)
      clearTimeout(t)
    }
  }, [])
  useEffect(() => setMsg(''), [loc.pathname])
  if (!msg) return null
  return (
    <div className="api-notice" role="alert">
      <span>{msg}</span>
      <span className="spacer" />
      {msg.startsWith('Sign in') && <Link className="btn sm" to="/login">Sign in</Link>}
      <button className="btn sm" onClick={() => { setMsg(''); onRetry() }}>Retry</button>
      <button className="icon-btn sm" onClick={() => setMsg('')} aria-label="Dismiss">x</button>
    </div>
  )
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
      return localStorage.getItem('rw-theme') === 'light' ? 'light' : 'dark'
    } catch {
      return 'dark'
    }
  })
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try {
      localStorage.setItem('rw-theme', theme)
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new Event('rw-theme'))
  }, [theme])
  return { dark: theme === 'dark', toggle: () => setTheme(theme === 'dark' ? 'light' : 'dark') }
}

/** Tables collapse to stacked cards on phones: copy each header label onto its cells so CSS can show it. */
function useTableLabels(root: string) {
  useEffect(() => {
    const el = document.querySelector(root)
    if (!el) return
    let raf = 0
    const run = () => {
      el.querySelectorAll('table.t').forEach((t) => {
        const heads = Array.from(t.querySelectorAll('thead th')).map((h) => (h.textContent ?? '').trim())
        if (!heads.length) return
        t.classList.add('stack')
        t.querySelectorAll('tbody tr').forEach((tr) => {
          Array.from(tr.children).forEach((td, i) => {
            if (td.hasAttribute('colspan')) return
            const l = heads[i] ?? ''
            if (td.getAttribute('data-label') !== l) td.setAttribute('data-label', l)
          })
        })
      })
    }
    const obs = new MutationObserver(() => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(run)
    })
    obs.observe(el, { childList: true, subtree: true })
    run()
    return () => {
      obs.disconnect()
      cancelAnimationFrame(raf)
    }
  }, [root])
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
  useTableLabels('#main')
  const [reload, setReload] = useState(0)
  const [tip, setTip] = useState<{ t: string; x: number; y: number } | null>(null)
  const showTip = (t: string) => (e: { currentTarget: HTMLElement }) => {
    if (!rail && window.innerWidth > 1180) return
    const r = e.currentTarget.getBoundingClientRect()
    setTip({ t, x: r.right + 12, y: r.top + r.height / 2 })
  }
  const hideTip = () => setTip(null)
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const bg = document.querySelector<HTMLElement>('.drawer-bg')
      if (bg) bg.click()
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [])
  const initials = (profile?.full_name || profile?.email || '?').split(/[\s@.]/).filter(Boolean).slice(0, 2).map((x) => x[0]?.toUpperCase()).join('')
  const isMap = loc.pathname === '/map'
  const flush = isMap
  const [menu, setMenu] = useState(false)
  const [rail, setRail] = useState<boolean>(() => {
    try { return localStorage.getItem('rw-rail') === '1' } catch { return false }
  })
  useEffect(() => {
    try { localStorage.setItem('rw-rail', rail ? '1' : '0') } catch { /* ignore */ }
  }, [rail])
  useEffect(() => setMenu(false), [loc.pathname])
  useEffect(() => {
    if (!menu) return
    const k = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(false)
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [menu])
  const title = NAV_GROUPS.flatMap((g) => g.items).find((n) => (n.to === '/' ? loc.pathname === '/' : loc.pathname.startsWith(n.to)))?.label ?? 'Disha AI'

  return (
    <div className={`shell ${rail ? 'collapsed' : ''}`}>
      <a className="skip-link" href="#main">Skip to content</a>
      <DepthFX />
      {tip && <div className="rail-tip" role="tooltip" style={{ left: tip.x, top: tip.y }}>{tip.t}</div>}
      <aside className="rail" aria-label="Sidebar">
        <Link className="brandmark" to="/" aria-label="Disha AI home">
          <img src="/logo.svg" alt="" />
          <b className="rl">Disha<em>AI</em></b>
        </Link>
        <div className="rail-scroll">
          {NAV_GROUPS.map((g) => (
            <div key={g.title} className="rail-group">
              <h6 className="rl">{g.title}</h6>
              <nav aria-label={g.title}>
                {g.items.filter((n) => !n.admin || isAdmin).map((n) => (
                  <NavLink key={n.to} to={n.to} end={n.to === '/'} aria-label={n.label} onMouseEnter={showTip(n.label)} onFocus={showTip(n.label)} onMouseLeave={hideTip} onBlur={hideTip} onClick={hideTip}>
                    <n.icon size={20} weight="duotone" />
                    <span className="lbl rl">{n.label}</span>
                    {n.badge && badges[n.badge] ? <span className="nb">{badges[n.badge]}</span> : null}
                  </NavLink>
                ))}
              </nav>
            </div>
          ))}
        </div>
        <div className="rail-foot">
          <a className="rail-link" href={panelUrl(5174)} target="_blank" rel="noopener noreferrer" title="Citizen portal"><UsersThree size={18} weight="bold" /><span className="rl">Citizen portal</span></a>
          {enabled &&
            (profile ? (
              <div className="userbox">
                <div className="avatar">{initials}</div>
                <div className="rl" style={{ minWidth: 0, flex: 1 }}>
                  <div className="who">{profile.full_name || profile.email}</div>
                  <div className="role">{profile.role}{profile.ward ? `, ${profile.ward}` : ''}</div>
                </div>
                <button className="icon-btn" onClick={signOut} aria-label="Sign out" title="Sign out"><SignOut size={16} weight="bold" /></button>
              </div>
            ) : (
              <Link className="btn primary wide" to="/login" title="Officer sign in"><SignIn size={16} weight="bold" /><span className="rl">Officer sign in</span></Link>
            ))}
          <div className="rail-ctl">
            <button className="icon-btn" onClick={toggle} aria-label="Toggle appearance" title="Toggle appearance">{dark ? <Sun size={17} weight="bold" /> : <Moon size={17} weight="bold" />}</button>
            <button className="icon-btn" onClick={() => setRail(!rail)} aria-label={rail ? 'Expand sidebar' : 'Collapse sidebar'} title={rail ? 'Expand sidebar' : 'Collapse sidebar'}>{rail ? <CaretRight size={16} weight="bold" /> : <CaretLeft size={16} weight="bold" />}</button>
          </div>
        </div>
      </aside>
      <div className="content">
      <header className="topbar">
        <Link className="brandmark mob" to="/" aria-label="Disha AI home"><img src="/logo.svg" alt="" /></Link>
        <span className="title-m">{title}</span>
        <span className="spacer" />
        <span className="sys-live" title={connected ? 'Live updates on' : 'Reconnecting'}>
          <span className={`dot ${connected ? 'ok' : ''}`} />
          <span className="t">{connected ? 'System live' : 'Reconnecting'}</span>
        </span>
        <a className="btn sm tb-link" href={panelUrl(5175)} target="_blank" rel="noopener noreferrer"><ArrowSquareOut size={14} weight="bold" /> Feed panel</a>
        <AlarmControl />
        <button className="icon-btn tb-theme" onClick={toggle} aria-label="Toggle appearance">{dark ? <Sun size={17} weight="bold" /> : <Moon size={17} weight="bold" />}</button>
      </header>
      <div className={`side-scrim ${menu ? 'on' : ''}`} onClick={() => setMenu(false)} />
      <aside className={`sheet ${menu ? 'open' : ''}`} aria-label="All pages" aria-hidden={!menu}>
        <div className="sheet-grip" />
        {NAV_GROUPS.map((g) => (
          <div key={g.title}>
            <h6>{g.title}</h6>
            <nav className="sheet-grid" aria-label={g.title}>
              {g.items.filter((n) => !n.admin || isAdmin).map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === '/'} tabIndex={menu ? 0 : -1}>
                  <Tile icon={n.icon} color={n.color} />
                  <span className="lbl">{n.label}</span>
                  {n.badge && badges[n.badge] ? <span className="badge">{badges[n.badge]}</span> : null}
                </NavLink>
              ))}
            </nav>
          </div>
        ))}
        <div className="sheet-ext">
          <a className="btn sm" href={panelUrl(5175)} target="_blank" rel="noopener noreferrer" tabIndex={menu ? 0 : -1}><ArrowSquareOut size={15} weight="bold" /> Feed panel</a>
          <a className="btn sm" href={panelUrl(5174)} target="_blank" rel="noopener noreferrer" tabIndex={menu ? 0 : -1}><UsersThree size={15} weight="bold" /> Citizen portal</a>
        </div>
        <div className="sheet-foot">
          <div className="status-line">
            <span className={`dot ${connected ? 'ok' : ''}`} />
            <span>{connected ? 'System live' : 'Reconnecting'}</span>
            <span className="spacer" />
            <button className="icon-btn" onClick={toggle} aria-label="Toggle appearance" title="Toggle appearance" tabIndex={menu ? 0 : -1}>
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
                <button className="icon-btn" onClick={signOut} aria-label="Sign out" title="Sign out" tabIndex={menu ? 0 : -1}><SignOut size={16} weight="bold" /></button>
              </div>
            ) : (
              <Link className="btn primary wide" to="/login" tabIndex={menu ? 0 : -1}><SignIn size={16} weight="bold" /> Officer sign in</Link>
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
        {!isMap && <ApiNotice onRetry={() => { setReload((n) => n + 1); loadBadges() }} />}
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="*" element={<AdminGate><Boundary key={loc.pathname + reload} onRetry={() => setReload((n) => n + 1)}><AdminRoutes /></Boundary></AdminGate>} />
        </Routes>
      </main>
      </div>
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
          <Route path="/insights" element={<Insights />} />
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
