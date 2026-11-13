import { useEffect, useRef } from 'react'
import { mapUrl } from '../api'
import { authToken, useAuth } from '../auth'

/** Full-bleed embed of the backend's Google-Maps style map. Officers get repair actions: the token is handed to the map page. */
export default function LiveMap() {
  const ref = useRef<HTMLIFrameElement>(null)
  const { isOfficer } = useAuth()
  const send = () => {
    const w = ref.current?.contentWindow
    if (w) w.postMessage({ type: 'rw-auth', token: isOfficer ? authToken() : null }, '*')
  }
  useEffect(() => {
    send()
    const t = setInterval(send, 4000) // the map may load after this page; keep the token fresh
    return () => clearInterval(t)
  })
  return <iframe ref={ref} onLoad={send} className="map-embed" src={mapUrl()} title="Live road map" allow="geolocation; fullscreen" />
}
