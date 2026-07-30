import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AccountPage from './AccountPage'

const api = vi.hoisted(() => ({
  getAccount: vi.fn(),
  createBrowserEnrollmentToken: vi.fn(),
  createBillingPortalSession: vi.fn(),
  buildEnrollmentGuidance: vi.fn(() => ({
    configureHint: 'Set control_plane.enabled=true and control_plane.base_url=https://api.example',
    enrollCommand: 'agentpulse enroll /etc/agentpulse/config.json',
    stdinCommand: 'agentpulse enroll /etc/agentpulse/config.json --token-stdin',
  })),
  API_BASE_URL: 'https://api.example',
}))

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    constructor(
      readonly status: number,
      message: string,
    ) {
      super(message)
    }
  },
  getAccount: api.getAccount,
  createBrowserEnrollmentToken: api.createBrowserEnrollmentToken,
  createBillingPortalSession: api.createBillingPortalSession,
  buildEnrollmentGuidance: api.buildEnrollmentGuidance,
  API_BASE_URL: api.API_BASE_URL,
}))

function renderAccount() {
  return render(
    <MemoryRouter initialEntries={['/account']}>
      <Routes>
        <Route path="/account" element={<AccountPage />} />
        <Route path="/connect" element={<div>connect-page</div>} />
        <Route path="/servers" element={<div>servers-page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

const activeAccount = {
  tenant_id: 'tenant-a',
  email: 'owner@example.test',
  plan: 'starter',
  entitlement_status: 'active',
  agent_limit: 1,
  current_period_end: 1_700_000_000,
  grace_period_ends_at: null,
}

describe('AccountPage', () => {
  beforeEach(() => {
    api.getAccount.mockReset()
    api.createBrowserEnrollmentToken.mockReset()
    api.createBillingPortalSession.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('shows subscription details for an active paid session', async () => {
    api.getAccount.mockResolvedValue(activeAccount)
    renderAccount()

    expect(await screen.findByText('owner@example.test')).toBeTruthy()
    expect(screen.getByText('Starter')).toBeTruthy()
    expect(screen.getByText('Active')).toBeTruthy()
    expect(screen.getByText('1')).toBeTruthy()
  })

  it('routes anonymous sessions to connect', async () => {
    const { ApiError } = await import('../api/client')
    api.getAccount.mockRejectedValue(new ApiError(401, 'unauthorized'))
    renderAccount()
    expect(await screen.findByText('connect-page')).toBeTruthy()
  })

  it('blocks enrollment mint when entitlement is inactive and still allows portal', async () => {
    api.getAccount.mockResolvedValue({
      ...activeAccount,
      entitlement_status: 'blocked',
    })
    api.createBillingPortalSession.mockResolvedValue({
      portal_url: 'https://billing.stripe.com/p/session/test',
    })
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })

    renderAccount()
    expect(await screen.findByText(/Host enrollment is blocked/i)).toBeTruthy()
    const mint = screen.getByRole('button', { name: /Create enrollment token/i })
    expect((mint as HTMLButtonElement).disabled).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: /Open billing portal/i }))
    await waitFor(() => expect(api.createBillingPortalSession).toHaveBeenCalledTimes(1))
    expect(assign).toHaveBeenCalledWith('https://billing.stripe.com/p/session/test')
    vi.unstubAllGlobals()
  })

  it('mints an enrollment token into page memory only and shows enroll commands without embedding it', async () => {
    api.getAccount.mockResolvedValue(activeAccount)
    api.createBrowserEnrollmentToken.mockResolvedValue({
      enrollment_token: 'ap_enroll_secret_once_1234567890',
      expires_at: 1_700_000_600,
    })

    renderAccount()
    await screen.findByText('owner@example.test')
    fireEvent.click(screen.getByRole('button', { name: /Create enrollment token/i }))

    const tokenEl = await screen.findByTestId('enrollment-token')
    expect(tokenEl.textContent).toContain('ap_enroll_secret_once_1234567890')
    expect(screen.getByText('agentpulse enroll /etc/agentpulse/config.json')).toBeTruthy()
    expect(screen.getByText(/--token-stdin/)).toBeTruthy()
    expect(window.sessionStorage.length).toBe(0)
    expect(window.localStorage.length).toBe(0)
  })

  it('rejects non-Stripe portal URLs', async () => {
    api.getAccount.mockResolvedValue(activeAccount)
    api.createBillingPortalSession.mockResolvedValue({
      portal_url: 'https://evil.example/phish',
    })

    renderAccount()
    await screen.findByText('owner@example.test')
    fireEvent.click(screen.getByRole('button', { name: /Open billing portal/i }))
    expect(await screen.findByText(/not trusted/i)).toBeTruthy()
  })
})
