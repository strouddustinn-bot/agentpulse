import { expect, test } from '@playwright/test'
import { assertNoBrowserBearer } from './fixtures/mockApi'

/**
 * Live staging E2E — skipped unless AP_E2E_CLAIM_NONCE is provided.
 * Requires Owner Gate 4 DNS so staging-app resolves and cookies work cross-site
 * against staging-api.agentpulse.ca.
 */
const claimNonce = process.env.AP_E2E_CLAIM_NONCE?.trim() ?? ''

test.describe('staging-app live console', () => {
  test.skip(!claimNonce, 'Set AP_E2E_CLAIM_NONCE after minting a fresh staging claim')

  test('claim → account → enroll mint → logout without browser bearer storage', async ({
    page,
  }) => {
    await page.goto(`/claim?claim_nonce=${encodeURIComponent(claimNonce)}`)
    // Successful claim lands on fleet or account depending on entitlement.
    await expect(
      page.getByRole('link', { name: 'Account' }).or(page.getByRole('heading', { name: 'Account' })),
    ).toBeVisible({ timeout: 30_000 })
    await assertNoBrowserBearer(page)

    await page.getByRole('link', { name: 'Account' }).click()
    await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible()

    const mint = page.getByRole('button', { name: 'Create enrollment token' })
    if (await mint.isEnabled()) {
      await mint.click()
      await expect(page.getByTestId('enrollment-token')).toBeVisible()
      await assertNoBrowserBearer(page)
    }

    await page.getByRole('button', { name: 'Disconnect' }).click()
    await expect(page.getByRole('heading', { name: 'Connect AgentPulse' })).toBeVisible()
    await assertNoBrowserBearer(page)
  })
})
