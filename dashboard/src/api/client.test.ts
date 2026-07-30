import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  claimAccount,
  disconnectSession,
  getFleet,
} from './client'
import {
  clearCredential,
  getCsrfToken,
  setCsrfToken,
} from '../auth/credential'

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('browser-session API client', () => {
  beforeEach(() => {
    clearCredential()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearCredential()
  })

  it('uses the HttpOnly cookie for fleet reads and never sends a bearer credential', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ tenant_id: 'tenant-a', agents: [] }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getFleet()).resolves.toEqual([])
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'GET', credentials: 'include' })
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ Accept: 'application/json' })
  })

  it('claims an account with credentials included and retains only the returned CSRF token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({
      csrf_token: 'ap_csrf_claim_1234567890',
      account: {
        tenant_id: 'tenant-a',
        email: 'owner@example.com',
        plan: 'starter',
        entitlement_status: 'active',
        agent_limit: 1,
        current_period_end: null,
        grace_period_ends_at: null,
      },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await claimAccount('ap_claim_secret_1234567890')

    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', credentials: 'include' })
    expect(getCsrfToken()).toBe('ap_csrf_claim_1234567890')
    expect(window.sessionStorage.length).toBe(0)
  })

  it('bootstraps CSRF after a reload, deletes the server session, then clears memory', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ csrf_token: 'ap_csrf_reload_1234567890' }))
      .mockResolvedValueOnce(response(null, 204))
    vi.stubGlobal('fetch', fetchMock)

    await disconnectSession()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0][0]).toContain('/v1/session/csrf')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', credentials: 'include' })
    expect(fetchMock.mock.calls[1][0]).toContain('/v1/session')
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: 'DELETE',
      credentials: 'include',
      headers: { 'X-CSRF-Token': 'ap_csrf_reload_1234567890' },
    })
    expect(getCsrfToken()).toBeNull()
  })

  it('fails closed when CSRF bootstrap fails and never sends DELETE', async () => {
    setCsrfToken('ap_csrf_stale_1234567890')
    clearCredential()
    const fetchMock = vi.fn().mockResolvedValue(response({ error: { message: 'session expired' } }, 401))
    vi.stubGlobal('fetch', fetchMock)

    await expect(disconnectSession()).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toContain('/v1/session/csrf')
    expect(getCsrfToken()).toBeNull()
  })

  it('clears legacy sessionStorage account credentials on load and disconnect', async () => {
    window.sessionStorage.setItem('agentpulse.account_credential', 'ap_acct_legacy_secret')
    clearCredential()
    expect(window.sessionStorage.getItem('agentpulse.account_credential')).toBeNull()

    window.sessionStorage.setItem('agentpulse.account_credential', 'ap_acct_legacy_secret')
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ csrf_token: 'ap_csrf_reload_legacy_1234567890' }))
      .mockResolvedValueOnce(response(null, 204))
    vi.stubGlobal('fetch', fetchMock)
    await disconnectSession()
    expect(window.sessionStorage.getItem('agentpulse.account_credential')).toBeNull()
  })
})
