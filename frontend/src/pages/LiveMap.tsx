import { mapUrl } from '../api'

/** Full-bleed embed of the backend's Google-Maps style map (search, directions, route damage, 3D). */
export default function LiveMap() {
  return <iframe className="map-embed" src={mapUrl()} title="Live road map" allow="geolocation; fullscreen" />
}
