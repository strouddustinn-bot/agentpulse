/**
 * AgentPulse dashboard — read-only fleet screens + post-pay account console.
 *
 * Auth: Worker HttpOnly cookie + in-memory CSRF. No browser bearer storage.
 *
 * Routes:
 *   /                    session landing
 *   /signup              public checkout transition
 *   /connect /claim      checkout claim
 *   /account             subscription, enrollment, billing portal
 *   /servers             server inventory
 *   /servers/:agentId    server detail
 *   /incidents           incident list
 *   /incidents/:id       incident detail
 */

import { useEffect, useState } from 'react'
import { BrowserRouter, Link, Navigate, NavLink, Route, Routes, useNavigate } from 'react-router'
import { Shield } from 'lucide-react'
import { disconnectSession, getAccount } from './api/client'
import RequireSession from './components/RequireSession'
import AccountPage from './pages/AccountPage'
import ServerInventoryPage from './pages/ServerInventoryPage'
import ServerDetailPage from './pages/ServerDetailPage'
import IncidentListPage from './pages/IncidentListPage'
import IncidentDetailPage from './pages/IncidentDetailPage'
import ConnectPage from './pages/ConnectPage'
import SignupPage from './pages/SignupPage'

function Layout({ children }: { children: React.ReactNode }) {
  const [logoutError, setLogoutError] = useState<string | null>(null)
  const navigate = useNavigate()
  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `px-4 py-1.5 rounded-full text-sm transition-colors ${
      isActive
        ? 'bg-[#1a1d27] text-[#e2e8f0] border border-[#2d3048]'
        : 'text-[#64748b] hover:text-[#e2e8f0] border border-transparent'
    }`

  async function disconnect() {
    setLogoutError(null)
    try {
      await disconnectSession()
      navigate('/connect')
    } catch (reason) {
      setLogoutError(reason instanceof Error ? reason.message : 'Disconnect failed')
    }
  }

  return (
    <div className="min-h-screen bg-[#0a0b0f] text-[#e2e8f0]">
      <div className="border-b border-[#1f2937] bg-[#111318]/95 backdrop-blur-xl sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-8 flex items-center justify-between h-20">
          <Link to="/servers" className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-[#7c6af7] flex items-center justify-center">
              <Shield className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="text-2xl font-semibold tracking-[-1.5px]">AgentPulse</div>
              <div className="text-[10px] text-[#64748b] -mt-1 tracking-[2px]">FLEET DASHBOARD</div>
            </div>
          </Link>
          <nav className="flex items-center gap-2">
            <NavLink to="/servers" className={navLinkClass}>
              Servers
            </NavLink>
            <NavLink to="/incidents" className={navLinkClass}>
              Incidents
            </NavLink>
            <NavLink to="/account" className={navLinkClass}>
              Account
            </NavLink>
            <button type="button" onClick={disconnect} className={navLinkClass({ isActive: false })}>
              Disconnect
            </button>
          </nav>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-8 py-10">
        {logoutError ? <p className="text-sm text-[#f87171] mb-4">{logoutError}</p> : null}
        {children}
      </div>
    </div>
  )
}

function NotFound() {
  return (
    <div className="text-center py-24">
      <div className="text-5xl font-semibold tracking-[-2px] mb-3">404</div>
      <p className="text-[#64748b] mb-6">This page does not exist.</p>
      <Link to="/servers" className="text-[#7c6af7] hover:underline text-sm">
        Go to server inventory
      </Link>
    </div>
  )
}

function Landing() {
  const [target, setTarget] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    getAccount()
      .then(() => {
        if (!cancelled) setTarget('/servers')
      })
      .catch(() => {
        if (!cancelled) setTarget('/connect')
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (target) return <Navigate to={target} replace />
  return <div className="text-sm text-[#64748b]">Checking session…</div>
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/connect" element={<ConnectPage />} />
          <Route path="/claim" element={<ConnectPage />} />
          <Route
            path="/account"
            element={
              <RequireSession allowInactive>
                <AccountPage />
              </RequireSession>
            }
          />
          <Route
            path="/servers"
            element={
              <RequireSession>
                <ServerInventoryPage />
              </RequireSession>
            }
          />
          <Route
            path="/servers/:agentId"
            element={
              <RequireSession>
                <ServerDetailPage />
              </RequireSession>
            }
          />
          <Route
            path="/incidents"
            element={
              <RequireSession>
                <IncidentListPage />
              </RequireSession>
            }
          />
          <Route
            path="/incidents/:incidentId"
            element={
              <RequireSession>
                <IncidentDetailPage />
              </RequireSession>
            }
          />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
