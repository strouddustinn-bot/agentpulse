import { expect, test } from '@playwright/test'
import {
  assertNoBrowserBearer,
  installMockApi,
  readAssignedUrls,
  stubExternalNavigation,
} from './fixtures/mockApi'

test.describe('console session lifecycle (mocked Worker)', () => {
  test.beforeEach(async ({ page }) => {
    await stubExternalNavigation(page)
  })

  test('anonymous fleet route redirects to connect', async ({ page }) => {
    await installMockApi(page, { startAnonymous: true })
    await page.goto('/servers')
    await expect(page).toHaveURL(/\/connect$/)
    await expect(page.getByRole('heading', { name: 'Connect AgentPulse' })).toBeVisible()
    await assertNoBrowserBearer(page)
  })

  test('claim → servers → account enroll → portal → logout', async ({ page }) => {
    const api = await installMockApi(page, { startAnonymous: true })

    await page.goto(`/claim?claim_nonce=${encodeURIComponent(api.claimNonce)}`)
    await expect(page).toHaveURL(/\/servers$/)
    await expect(page.getByRole('heading', { name: 'Servers' })).toBeVisible()
    await expect(page.getByText('edge-01.example')).toBeVisible()
    await assertNoBrowserBearer(page)

    await page.getByRole('link', { name: 'Account' }).click()
    await expect(page).toHaveURL(/\/account$/)
    await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible()
    await expect(page.getByText(api.account.email)).toBeVisible()
    await expect(page.getByText('Starter')).toBeVisible()
    await expect(page.getByText('Active')).toBeVisible()

    await page.getByRole('button', { name: 'Create enrollment token' }).click()
    const token = page.getByTestId('enrollment-token')
    await expect(token).toContainText('ap_enroll_e2e_secret_once_do_not_store')
    await expect(
      page.getByText('agentpulse enroll /etc/agentpulse/config.json', { exact: true }),
    ).toBeVisible()
    await expect(
      page.getByText('agentpulse enroll /etc/agentpulse/config.json --token-stdin', {
        exact: true,
      }),
    ).toBeVisible()
    await assertNoBrowserBearer(page)

    const portalRequest = page.waitForRequest(
      (req) => req.method() === 'POST' && req.url().includes('/v1/billing/portal'),
    )
    await page.getByRole('button', { name: 'Open billing portal' }).click()
    const portal = await portalRequest
    expect(portal.headers()['x-csrf-token']).toBeTruthy()
    await expect
      .poll(async () => readAssignedUrls(page), { timeout: 5_000 })
      .toContain('https://billing.stripe.com/p/session/e2e-test')
    await expect(page).toHaveURL(/\/account$/)
    await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible()

    const csrfCalls = api.seen.filter(
      (entry) =>
        entry.includes('POST /v1/browser/enrollment-tokens') ||
        entry.includes('POST /v1/billing/portal') ||
        entry.includes('DELETE /v1/session'),
    )
    expect(csrfCalls.length).toBeGreaterThanOrEqual(2)

    await page.getByRole('button', { name: 'Disconnect' }).click()
    await expect(page).toHaveURL(/\/connect$/)
    expect(api.isSessionActive()).toBe(false)
    await assertNoBrowserBearer(page)

    await page.goto('/servers')
    await expect(page).toHaveURL(/\/connect$/)
  })

  test('inactive entitlement keeps account, blocks fleet and enroll mint', async ({ page }) => {
    await installMockApi(page, {
      startAnonymous: false,
      account: {
        tenant_id: 'tenant-a',
        email: 'blocked@example.test',
        plan: 'starter',
        entitlement_status: 'blocked',
        agent_limit: 1,
        current_period_end: null,
        grace_period_ends_at: null,
      },
    })

    await page.goto('/servers')
    await expect(page).toHaveURL(/\/account$/)
    await expect(page.getByText(/Host enrollment is blocked/i)).toBeVisible()
    const mint = page.getByRole('button', { name: 'Create enrollment token' })
    await expect(mint).toBeDisabled()
    await expect(page.getByRole('button', { name: 'Open billing portal' })).toBeEnabled()
    await assertNoBrowserBearer(page)
  })

  test('manual claim form rejects bad nonce and accepts good nonce', async ({ page }) => {
    const api = await installMockApi(page, { startAnonymous: true })
    await page.goto('/connect')
    await page.getByLabel('Checkout claim nonce').fill('ap_claim_bad')
    await page.getByRole('button', { name: 'Connect', exact: true }).click()
    await expect(page.getByText(/invalid/i)).toBeVisible()
    await expect(page).toHaveURL(/\/connect$/)

    await page.getByLabel('Checkout claim nonce').fill(api.claimNonce)
    await page.getByRole('button', { name: 'Connect', exact: true }).click()
    await expect(page).toHaveURL(/\/servers$/)
    await expect(page.getByText('edge-01.example')).toBeVisible()
    await assertNoBrowserBearer(page)
  })

  test('cross-tenant query cannot change fleet tenant payload identity', async ({ page }) => {
    const api = await installMockApi(page, { startAnonymous: false })
    await page.goto('/servers')
    await expect(page.getByText('edge-01.example')).toBeVisible()

    const forced = await page.evaluate(async (foreignTenant) => {
      const response = await fetch(
        `http://127.0.0.1:8787/v1/fleet?tenant_id=${encodeURIComponent(foreignTenant)}`,
        { credentials: 'include', headers: { Accept: 'application/json' } },
      )
      return response.json()
    }, api.otherTenantId)

    expect(forced.tenant_id).toBe(api.account.tenant_id)
    expect(forced.tenant_id).not.toBe(api.otherTenantId)
  })
})
