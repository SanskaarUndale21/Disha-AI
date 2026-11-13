import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import 'leaflet/dist/leaflet.css'
import './index.css'
import App from './App'
import { AuthProvider } from './auth'
import { RealtimeProvider } from './events'
import { AlarmProvider } from './alarm'

const _base: string = ((import.meta as any).env?.VITE_API_BASE ?? '').replace(/\/+$/, '')
if (_base) {
  const _fetch = window.fetch.bind(window)
  window.fetch = ((input: any, init?: any) =>
    _fetch(typeof input === 'string' && input.startsWith('/api') ? _base + input : input, init)) as typeof fetch
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <RealtimeProvider>
          <AlarmProvider>
            <App />
          </AlarmProvider>
        </RealtimeProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
