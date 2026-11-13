import { useEffect } from 'react'

/** Surfaces that tilt toward the pointer. Cards that hold maps, tables, video or inputs stay flat. */
const SEL = '.card, .bigstat, .scr-stat, .acc, .al-row, .tilt'
const FLAT = '.leaflet-container, video, canvas, table, input, select, textarea, iframe, .drop, .drawer-bg, .live-wrap'
const MAX_DEG = 6

/**
 * One delegated pointer listener drives everything with transform and opacity:
 * a perspective tilt plus moving specular highlight on the surface under the mouse,
 * and a smoothed parallax value pair (--px, --py) on the command-centre hero.
 */
export function DepthFX() {
  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)')
    const fine = window.matchMedia('(hover: hover) and (pointer: fine)')
    if (reduce.matches || !fine.matches) return

    let active: HTMLElement | null = null
    let px = 0
    let py = 0
    let raf = 0
    let nx = 0
    let ny = 0
    let cx = 0
    let cy = 0
    let hero: HTMLElement | null = null
    let loop = 0
    const flatCache = new WeakMap<Element, boolean>()

    const release = (el: HTMLElement | null) => {
      if (!el) return
      el.classList.remove('is-tilt')
      el.style.removeProperty('--rx')
      el.style.removeProperty('--ry')
    }

    const paint = () => {
      raf = 0
      if (!active) return
      const r = active.getBoundingClientRect()
      const x = (px - r.left) / r.width
      const y = (py - r.top) / r.height
      const k = Math.min(1, 420 / Math.max(r.width, r.height)) // big surfaces lean less
      active.style.setProperty('--ry', `${((x - 0.5) * 2 * MAX_DEG * k).toFixed(2)}deg`)
      active.style.setProperty('--rx', `${((0.5 - y) * 2 * MAX_DEG * k).toFixed(2)}deg`)
      active.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`)
      active.style.setProperty('--my', `${(y * 100).toFixed(1)}%`)
    }

    const heroLoop = () => {
      loop = 0
      cx += (nx - cx) * 0.08
      cy += (ny - cy) * 0.08
      if (hero) {
        hero.style.setProperty('--px', cx.toFixed(3))
        hero.style.setProperty('--py', cy.toFixed(3))
      }
      if (Math.abs(nx - cx) > 0.002 || Math.abs(ny - cy) > 0.002) loop = requestAnimationFrame(heroLoop)
    }

    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse') return
      px = e.clientX
      py = e.clientY
      const t = e.target as Element | null
      let el = (t?.closest?.(SEL) as HTMLElement | null) ?? null
      if (el) {
        let flat = flatCache.get(el)
        if (flat === undefined) {
          flat = !!el.querySelector(FLAT) || el.matches(FLAT)
          flatCache.set(el, flat)
        }
        if (flat) el = null
      }
      if (el !== active) {
        release(active)
        active = el
        if (active) active.classList.add('is-tilt')
      }
      if (active && !raf) raf = requestAnimationFrame(paint)

      hero = hero && hero.isConnected ? hero : (document.querySelector('.hero') as HTMLElement | null)
      if (hero) {
        nx = (e.clientX / window.innerWidth - 0.5) * 2
        ny = (e.clientY / window.innerHeight - 0.5) * 2
        if (!loop) loop = requestAnimationFrame(heroLoop)
      }
    }
    const onLeave = () => {
      release(active)
      active = null
      nx = 0
      ny = 0
      if (!loop) loop = requestAnimationFrame(heroLoop)
    }
    document.addEventListener('pointermove', onMove, { passive: true })
    document.documentElement.addEventListener('pointerleave', onLeave)
    window.addEventListener('blur', onLeave)
    return () => {
      document.removeEventListener('pointermove', onMove)
      document.documentElement.removeEventListener('pointerleave', onLeave)
      window.removeEventListener('blur', onLeave)
      cancelAnimationFrame(raf)
      cancelAnimationFrame(loop)
      release(active)
    }
  }, [])
  return null
}

/** Isometric stack of floating glass slabs showing the live counts. Decorative; the real numbers sit in the stat strip. */
export function Hero3D({ open, serious, repaired, ready }: { open: number | null; serious: number | null; repaired: number | null; ready: boolean }) {
  const v = (n: number | null) => (ready && n != null ? n : '··')
  return (
    <div className="h3d" aria-hidden="true">
      <div className="h3d-scene">
        <div className="h3d-floor" />
        <div className="h3d-slab s1"><span>Repaired</span><b>{v(repaired)}</b></div>
        <div className="h3d-slab s2"><span>Serious</span><b>{v(serious)}</b></div>
        <div className="h3d-slab s3"><span>Open</span><b>{v(open)}</b></div>
      </div>
    </div>
  )
}
