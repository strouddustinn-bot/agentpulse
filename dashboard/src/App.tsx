/**
 * AgentPulse dashboard — read-only screens for the backend v1 API.
 *
 * Routes:
 *   /servers            server inventory
 *   /servers/:agentId   server detail
 *   /incidents          incident list
 *   /incidents/:id      incident detail
 */

import { BrowserRouter, Link, Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { Shield } from 'lucide-react'
import { clearCredential } from './auth/credential'
import ServerInventoryPage from './pages/ServerInventoryPage'
import ServerDetailPage from './pages/ServerDetailPage'
import IncidentListPage from './pages/IncidentListPage'
import IncidentDetailPage from './pages/IncidentDetailPage'
import ConnectPage from './pages/ConnectPage'

function Layout({ children }: { children: React.ReactNode }) {
  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `px-4 py-1.5 rounded-full text-sm transition-colors ${
      isActive
        ? 'bg-[#1a1d27] text-[#e2e8f0] border border-[#2d3048]'
        : 'text-[#64748b] hover:text-[#e2e8f0] border border-transparent'
    }`

  return (
    <div className="min-h-screen bg-[#0a0b0f] text-[#e2e8f0]">
      {/* Header */}
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
            <Link to="/connect" onClick={() => clearCredential()} className={navLinkClass({ isActive: false })}>
              Disconnect
            </Link>
          </nav>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-8 py-10">{children}</div>
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

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/connect" replace />} />
          <Route path="/connect" element={<ConnectPage />} />
          <Route path="/servers" element={<ServerInventoryPage />} />
          <Route path="/servers/:agentId" element={<ServerDetailPage />} />
          <Route path="/incidents" element={<IncidentListPage />} />
          <Route path="/incidents/:incidentId" element={<IncidentDetailPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
