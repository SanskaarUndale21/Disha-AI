import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js'

export type Profile = {
  id: string
  email: string
  full_name: string | null
  phone: string | null
  role: 'citizen' | 'officer' | 'admin'
  ward: string | null
  active: boolean
}

let client: SupabaseClient | null = null
let token: string | null = null
export const authToken = () => token

type Ctx = {
  ready: boolean
  enabled: boolean
  session: Session | null
  profile: Profile | null
  isOfficer: boolean
  isAdmin: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (email: string, password: string, full_name: string) => Promise<string>
  signOut: () => Promise<void>
  refresh: () => Promise<void>
}
const AuthCtx = createContext<Ctx>(null as any)
export const useAuth = () => useContext(AuthCtx)

async function loadProfile(): Promise<Profile | null> {
  if (!token) return null
  const r = await fetch('/api/me', { headers: { Authorization: `Bearer ${token}` } })
  return r.ok ? r.json() : null
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [session, setSession] = useState<Session | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)

  useEffect(() => {
    let unsub = () => {}
    fetch('/api/auth/config')
      .then((r) => r.json())
      .then(async (cfg) => {
        if (!cfg.supabase_url) {
          setReady(true)
          return
        }
        setEnabled(true)
        client = createClient(cfg.supabase_url, cfg.supabase_key)
        const { data } = await client.auth.getSession()
        token = data.session?.access_token ?? null
        setSession(data.session)
        setProfile(await loadProfile())
        const sub = client.auth.onAuthStateChange(async (_e, s) => {
          token = s?.access_token ?? null
          setSession(s)
          setProfile(await loadProfile())
        })
        unsub = () => sub.data.subscription.unsubscribe()
        setReady(true)
      })
      .catch(() => setReady(true))
    return () => unsub()
  }, [])

  const value: Ctx = {
    ready,
    enabled,
    session,
    profile,
    isOfficer: !enabled || profile?.role === 'officer' || profile?.role === 'admin',
    isAdmin: !enabled || profile?.role === 'admin',
    signIn: async (email, password) => {
      const { error } = await client!.auth.signInWithPassword({ email, password })
      if (error) throw error
    },
    signUp: async (email, password, full_name) => {
      const { data, error } = await client!.auth.signUp({ email, password, options: { data: { full_name } } })
      if (error) throw error
      return data.session ? 'Account created, you are signed in.' : 'Account created. Check your email to confirm it, then sign in.'
    },
    signOut: async () => {
      await client?.auth.signOut()
      token = null
      setProfile(null)
    },
    refresh: async () => setProfile(await loadProfile()),
  }
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}
