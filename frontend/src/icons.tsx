import type { Icon } from '@phosphor-icons/react'
import {
  ChartLineUp, ChatCircleText, Cpu, Images, MapTrifold, RoadHorizon, SealCheck, UploadSimple, UsersThree, VideoCamera,
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
      { to: '/live', icon: VideoCamera, color: '#ff3b30', label: 'Live patrol' },
      { to: '/complaints', icon: ChatCircleText, color: '#ff9500', label: 'Citizen complaints', badge: 'complaints' },
      { to: '/verify', icon: SealCheck, color: '#34c759', label: 'Review detections', badge: 'pending' },
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
  pothole: '#ff3b30',
  alligator_crack: '#ff9500',
  transverse_crack: '#007aff',
  longitudinal_crack: '#af52de',
}
export const RISK_HEX: Record<string, string> = { High: '#ff3b30', Medium: '#ff9500', Low: '#34c759' }
