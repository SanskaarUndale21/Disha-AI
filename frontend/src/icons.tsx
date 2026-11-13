import type { Icon } from '@phosphor-icons/react'
import {
  BellRinging, ChartLineUp, ChartPolar, ChatCircleText, Cpu, Images, MapPinArea, MapTrifold, Phone, RoadHorizon, SealCheck, UploadSimple, UsersThree, VideoCamera, Wrench,
} from '@phosphor-icons/react'

/** macOS Settings-style icon tile: white glyph on a coloured squircle. */
export function Tile({ icon: I, color, size = 26 }: { icon: Icon; color: string; size?: number }) {
  return (
    <span className="tile" style={{ width: size, height: size, background: `${color}1f`, color }}>
      <I size={size * 0.66} weight="duotone" />
    </span>
  )
}

export type NavItem = { to: string; icon: Icon; color: string; label: string; officer?: boolean; admin?: boolean; badge?: string }

export const NAV_GROUPS: { title: string; items: NavItem[] }[] = [
  {
    title: 'Operations',
    items: [
      { to: '/', icon: MapTrifold, color: '#007aff', label: 'Command center' },
      { to: '/map', icon: MapPinArea, color: '#1f5fbf', label: 'Live map' },
      { to: '/alerts', icon: BellRinging, color: '#d92d20', label: 'Alerts', badge: 'alerts' },
      { to: '/live', icon: VideoCamera, color: '#ff3b30', label: 'Live patrol' },
      { to: '/complaints', icon: ChatCircleText, color: '#ff9500', label: 'Citizen complaints', badge: 'complaints' },
      { to: '/phone', icon: Phone, color: '#0f8a8a', label: 'Phone complaints', badge: 'phone' },
      { to: '/verify', icon: SealCheck, color: '#34c759', label: 'Review detections', badge: 'pending' },
      { to: '/repairs', icon: Wrench, color: '#dd7a07', label: 'Repairs and budget' },
      { to: '/insights', icon: ChartPolar, color: '#81b29a', label: 'City insights' },
    ],
  },
  {
    title: 'Records',
    items: [
      { to: '/defects', icon: RoadHorizon, color: '#5856d6', label: 'Defect registry' },
      { to: '/inspections', icon: Images, color: '#30b0c7', label: 'Inspections' },
      { to: '/progress', icon: ChartLineUp, color: '#af52de', label: 'Repair progress' },
      { to: '/analyze', icon: UploadSimple, color: '#636366', label: 'Upload media' },
    ],
  },
  {
    title: 'System',
    items: [
      { to: '/model', icon: Cpu, color: '#ff2d55', label: 'AI model' },
      { to: '/users', icon: UsersThree, color: '#8e8e93', label: 'Users and roles', admin: true },
    ],
  },
]

export const CLASS_HEX: Record<string, string> = {
  pothole: '#e07a5f',
  alligator_crack: '#f2cc8f',
  transverse_crack: '#b3b6d6',
  longitudinal_crack: '#81b29a',
  manhole: '#8e91b0',
  speed_breaker: '#d9b56b',
  debris: '#a58e6f',
  barricade: '#a9abc0',
}
export const RISK_HEX: Record<string, string> = { High: '#e07a5f', Medium: '#f2cc8f', Low: '#81b29a', Repaired: '#b3b6d6' }
