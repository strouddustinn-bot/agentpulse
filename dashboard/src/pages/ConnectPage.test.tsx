import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ConnectPage from './ConnectPage'

const api = vi.hoisted(() => ({
  claimAccount: vi.fn(),
  getAccount: vi.fn(),
}))

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    constructor(readonly status: number, message: string) {
      super(message)
    }
  },
  claimAccount: api.claimAccount,
  getAccount: api.getAccount,
}))

function renderAt(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/claim" element={<ConnectPage />} />
        <Route path="/connect" element={<ConnectPage />} />
        <Route path="/servers" element={<div>servers-ready</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('checkout claim routing', () => {
  beforeEach(() => {
    api.claimAccount.mockReset()
    api.getAccount.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('scrubs the claim nonce before exchanging it and routes a successful claim', async () => {
    const replaceState = vi.spyOn(window.history, 'replaceState')
    api.claimAccount.mockImplementation(async () => {
      expect(replaceState).toHaveBeenCalledWith(null, '', '/claim')
      return { tenant_id: 'tenant-a' }
    })

    renderAt('/claim?claim_nonce=ap_claim_secret_1234567890')

    expect(await screen.findByText('servers-ready')).toBeTruthy()
    expect(api.claimAccount).toHaveBeenCalledWith('ap_claim_secret_1234567890')
    expect(document.body.textContent).not.toContain('ap_claim_secret_1234567890')
  })

  it('recovers an ambiguous claim when the browser session already exists', async () => {
    api.claimAccount.mockRejectedValue(new Error('network response lost'))
    api.getAccount.mockResolvedValue({ tenant_id: 'tenant-a' })

    renderAt('/claim?claim_nonce=ap_claim_ambiguous_1234567890')

    expect(await screen.findByText('servers-ready')).toBeTruthy()
    expect(api.getAccount).toHaveBeenCalledTimes(1)
  })

  it('shows a truthful error when neither claim nor session succeeds and never renders the URL nonce', async () => {
    api.claimAccount.mockRejectedValue(new Error('Claim token is invalid'))
    api.getAccount.mockRejectedValue(new Error('No browser session'))

    renderAt('/claim?claim_nonce=ap_claim_invalid_1234567890')

    expect(await screen.findByText('Claim token is invalid')).toBeTruthy()
    expect(document.body.textContent).not.toContain('ap_claim_invalid_1234567890')
  })

  it('routes an already-authenticated visitor without requiring a claim nonce', async () => {
    api.getAccount.mockResolvedValue({ tenant_id: 'tenant-a' })

    renderAt('/connect')

    await waitFor(() => expect(api.getAccount).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('servers-ready')).toBeTruthy()
    expect(api.claimAccount).not.toHaveBeenCalled()
  })
})
