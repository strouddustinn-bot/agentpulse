import type { Page, Request, Route } from '@playwright/test'
import { expect } from '@playwright/test'

export type MockAccount = {
  tenant_id: string
  email: string
  plan: string
  entitlement_status: 'active' | 'grace' | 'blocked'
  agent_limit: number
  current_period_end: number | null
  grace_period_ends_at: number | null
}

export type MockApiOptions = {
  account?: MockAccount
  claimNonce?: string
  /** When true, anonymous GETs stay 401 until a successful claim. */
  startAnonymous?: boolean
  /** Second tenant used only for isolation assertions. */
  otherTenantId?: string
}

const DEFAULT_ACCOUNT: MockAccount = {
  tenant_id: 'tenant-a',
  email: 'owner@example.test',
  plan: 'starter',
  entitlement_status: 'active',
  agent_limit: 1,
  current_period_end: 1_900_000_000,
  grace_period_ends_at: null,
}

function json(route: Route, status: number, body: unknown, extraHeaders: Record<string, string> = {}) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    headers: {
      'Access-Control-Allow-Origin': 'http://127.0.0.1:4173',
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Headers': 'Accept, Content-Type, X-CSRF-Token',
      'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
      Vary: 'Origin',
      ...extraHeaders,
    },
    body: JSON.stringify(body),
  })
}

function unauthorized(route: Route) {
  return json(route, 401, {
    error: { code: 'unauthorized', message: 'Authentication required' },
  })
}

function forbidden(route: Route, message: string) {
  return json(route, 403, {
    error: { code: 'forbidden', message },
  })
}

function fleetPayload(tenantId: string) {
  const now = Math.floor(Date.now() / 1000)
  return {
    tenant_id: tenantId,
    agents: [
      {
        agent_key: 'agent-host-1',
        hostname: 'edge-01.example',
        enrolled_at: now - 86_400,
        last_seen_at: now - 30,
        local_policy_ceiling: 'supervised',
        incidents: [
          {
            id: 'inc-1',
            kind: 'disk_pressure',
            detail: 'root filesystem above warning threshold',
            severity: 'warning',
            status: 'open',
            fingerprint: 'disk-root',
            opened_at: now - 600,
            updated_at: now - 30,
          },
        ],
      },
    ],
  }
}

/**
 * Install a deterministic Worker mock for the console against VITE_API_BASE_URL.
 * Tracks CSRF requirements and session state for claim / enroll / portal / logout.
 */
export async function installMockApi(page: Page, options: MockApiOptions = {}) {
  const account: MockAccount = { ...DEFAULT_ACCOUNT, ...(options.account ?? {}) }
  const claimNonce = options.claimNonce ?? 'ap_claim_e2e_valid_nonce'
  const otherTenantId = options.otherTenantId ?? 'tenant-b'
  let sessionActive = options.startAnonymous === false
  let csrfToken: string | null = sessionActive ? 'csrf-seed-token' : null
  const seen: string[] = []

  const record = (request: Request) => {
    seen.push(`${request.method()} ${new URL(request.url()).pathname}`)
  }

  await page.route('**/v1/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method().toUpperCase()
    record(request)

    if (method === 'OPTIONS') {
      return json(route, 204, {})
    }

    if (method === 'POST' && path.endsWith('/v1/onboarding/claim')) {
      const body = request.postDataJSON() as { claim_nonce?: string } | null
      if (!body?.claim_nonce || body.claim_nonce !== claimNonce) {
        return json(route, 400, {
          error: { code: 'invalid_claim', message: 'Claim token is invalid' },
        })
      }
      sessionActive = true
      csrfToken = `csrf-${Math.random().toString(36).slice(2, 10)}`
      return json(route, 200, { csrf_token: csrfToken, account })
    }

    if (method === 'GET' && path.endsWith('/v1/account')) {
      if (!sessionActive) return unauthorized(route)
      return json(route, 200, account)
    }

    if (method === 'POST' && path.endsWith('/v1/session/csrf')) {
      if (!sessionActive) return unauthorized(route)
      csrfToken = `csrf-${Math.random().toString(36).slice(2, 10)}`
      return json(route, 200, { csrf_token: csrfToken })
    }

    if (method === 'DELETE' && path.endsWith('/v1/session')) {
      if (!sessionActive) return unauthorized(route)
      const header = request.headers()['x-csrf-token']
      if (!header || header !== csrfToken) {
        return forbidden(route, 'CSRF token missing or invalid')
      }
      sessionActive = false
      csrfToken = null
      return route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': 'http://127.0.0.1:4173',
          'Access-Control-Allow-Credentials': 'true',
        },
      })
    }

    if (method === 'POST' && path.endsWith('/v1/browser/enrollment-tokens')) {
      if (!sessionActive) return unauthorized(route)
      const header = request.headers()['x-csrf-token']
      if (!header || header !== csrfToken) {
        return forbidden(route, 'CSRF token missing or invalid')
      }
      if (!['active', 'grace'].includes(account.entitlement_status)) {
        return forbidden(route, 'Host enrollment is blocked')
      }
      return json(
        route,
        201,
        {
          enrollment_token: 'ap_enroll_e2e_secret_once_do_not_store',
          expires_at: Math.floor(Date.now() / 1000) + 600,
        },
        { 'Cache-Control': 'no-store' },
      )
    }

    if (method === 'POST' && path.endsWith('/v1/billing/portal')) {
      if (!sessionActive) return unauthorized(route)
      const header = request.headers()['x-csrf-token']
      if (!header || header !== csrfToken) {
        return forbidden(route, 'CSRF token missing or invalid')
      }
      return json(route, 200, {
        portal_url: 'https://billing.stripe.com/p/session/e2e-test',
      })
    }

    if (method === 'GET' && path.endsWith('/v1/fleet')) {
      if (!sessionActive) return unauthorized(route)
      if (!['active', 'grace'].includes(account.entitlement_status)) {
        return forbidden(route, 'Subscription is inactive')
      }
      // Isolation probe: foreign tenant query must not change payload tenant.
      return json(route, 200, fleetPayload(account.tenant_id))
    }

    return json(route, 404, {
      error: { code: 'not_found', message: `No mock for ${method} ${path}` },
    })
  })

  return {
    account,
    claimNonce,
    otherTenantId,
    seen,
    setEntitlement(status: MockAccount['entitlement_status']) {
      account.entitlement_status = status
    },
    isSessionActive() {
      return sessionActive
    },
  }
}

export async function assertNoBrowserBearer(page: Page) {
  const storage = await page.evaluate(() => ({
    local: { ...window.localStorage },
    session: { ...window.sessionStorage },
  }))
  const blob = JSON.stringify(storage).toLowerCase()
  expect(blob).not.toMatch(/ap_(session|enroll|claim)_/)
  expect(blob).not.toMatch(/bearer/)
  expect(blob).not.toMatch(/account_credential/)
  expect(Object.keys(storage.local)).toHaveLength(0)
  expect(Object.keys(storage.session)).toHaveLength(0)
}

/**
 * Capture external navigations via the product seam in src/lib/navigation.ts.
 * Production still uses location.assign when the hook is absent.
 */
export async function stubExternalNavigation(page: Page) {
  await page.addInitScript(() => {
    const store: string[] = []
    ;(window as unknown as { __apAssignedUrls: string[] }).__apAssignedUrls = store
    ;(window as unknown as { __apNavigateExternal: (url: string) => void }).__apNavigateExternal = (
      url: string,
    ) => {
      store.push(String(url))
    }
  })
}

export async function readAssignedUrls(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const w = window as unknown as { __apAssignedUrls?: string[] }
    return [...(w.__apAssignedUrls ?? [])]
  })
}
