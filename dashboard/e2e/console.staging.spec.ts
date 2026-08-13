import { expect, test, type Page } from '@playwright/test'
import { assertNoBrowserBearer } from './fixtures/mockApi'

/**
 * Live staging E2E against real staging-app + staging-api.
 *
 * Preferred path (no nonce paste):
 *   AP_E2E_BASE_URL=https://staging-app.agentpulse.ca
 *   AP_E2E_API_BASE_URL=https://staging-api.agentpulse.ca
 *   npm run test:e2e:staging
 *
 * Creates a Stripe *test-mode* Checkout Session, pays with the Visa test card
 * inside Playwright, then asserts claim → account → enroll mint → logout with
 * no browser bearer storage.
 *
 * Optional override (single-use; do not commit):
 *   AP_E2E_CLAIM_NONCE=ap_claim_…
 *
 * Never log checkout URLs, claim nonces, or enrollment tokens.
 */

const appBase = (process.env.AP_E2E_BASE_URL ?? '').replace(/\/+$/, '')
const apiBase = (process.env.AP_E2E_API_BASE_URL ?? 'https://staging-api.agentpulse.ca').replace(
  /\/+$/,
  '',
)
const providedNonce = process.env.AP_E2E_CLAIM_NONCE?.trim() ?? ''
// Unique email every run — Stripe rejects "already have a subscription" for reused test emails.
const testEmail =
  process.env.AP_E2E_CHECKOUT_EMAIL?.trim() ||
  `agentpulse-e2e+${Date.now()}@example.test`

test.describe.configure({ mode: 'serial', timeout: 180_000 })

test.describe('staging-app live console', () => {
  test.skip(!appBase, 'Set AP_E2E_BASE_URL to the live staging console origin')

  test('checkout → claim → account → enroll mint → logout without browser bearer storage', async ({
    page,
  }) => {
    if (providedNonce) {
      await page.goto(`/claim?claim_nonce=${encodeURIComponent(providedNonce)}`)
    } else {
      await completeStripeTestCheckout(page)
    }

    // Real auth signal: claim lands on fleet (or account). Layout always shows Disconnect,
    // so that button alone is NOT proof of a session.
    await expect(
      page
        .getByRole('heading', { name: 'Servers' })
        .or(page.getByRole('heading', { name: 'Account' })),
    ).toBeVisible({ timeout: 90_000 })
    await expect(page.getByRole('heading', { name: 'Connect AgentPulse' })).toHaveCount(0)
    await assertNoBrowserBearer(page)

    // SPA nav can race right after claim; use in-app link then fall back to direct route.
    if (!(await page.getByRole('heading', { name: 'Account' }).isVisible().catch(() => false))) {
      await page.getByRole('link', { name: 'Account' }).click()
      try {
        await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible({ timeout: 15_000 })
      } catch {
        await page.goto('/account', { waitUntil: 'domcontentloaded' })
      }
    }
    await expect(page).toHaveURL(/\/account$/)
    await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/Starter/i)).toBeVisible()
    await expect(page.getByText(/Active|Grace/i)).toBeVisible()

    const mint = page.getByRole('button', { name: 'Create enrollment token' })
    await expect(mint).toBeEnabled({ timeout: 15_000 })
    await mint.click()
    await expect(page.getByTestId('enrollment-token')).toBeVisible()
    // Token value must stay in the DOM only — never assert its contents into logs.
    await assertNoBrowserBearer(page)

    await page.getByRole('button', { name: 'Disconnect' }).click()
    await expect(page.getByRole('heading', { name: 'Connect AgentPulse' })).toBeVisible({
      timeout: 30_000,
    })
    await expect(page).toHaveURL(/\/connect$/)
    await assertNoBrowserBearer(page)
  })
})

async function completeStripeTestCheckout(page: Page): Promise<void> {
  const checkout = await createStagingCheckoutSession()
  await page.goto(checkout.checkout_url, { waitUntil: 'domcontentloaded' })

  // Sandbox Checkout: wait for the real email field, not hidden Link iframes.
  const email = page.getByRole('textbox', { name: /email/i }).first()
  await expect(email).toBeVisible({ timeout: 60_000 })
  await email.fill(testEmail)

  // Expand card fields (collapsed until Card is selected).
  const cardRadio = page.getByRole('radio', { name: /^card$/i })
  if (await cardRadio.count()) {
    await cardRadio.check({ force: true }).catch(async () => {
      await page.getByText(/^card$/i).first().click()
    })
  } else {
    await page.getByText(/^card$/i).first().click()
  }

  // Card inputs often mount inside Stripe Payment Element iframes after selection.
  await fillCardNumber(page, '4242424242424242')
  await fillCardExpiry(page, '1242')
  await fillCardCvc(page, '123')

  await fillOptionalBilling(page)

  // Avoid Link save prompt noise when present.
  const saveInfo = page.getByRole('checkbox', { name: /save my information/i })
  if (await saveInfo.count()) {
    if (await saveInfo.isChecked().catch(() => false)) {
      await saveInfo.uncheck({ force: true }).catch(() => undefined)
    }
  }

  const subscribe = page.getByRole('button', { name: /^subscribe$/i }).first()
  await expect(subscribe).toBeEnabled({ timeout: 30_000 })
  await subscribe.click()

  // Success returns to staging-app /claim?claim_nonce=… which auto-claims.
  await page.waitForURL(
    (url) => {
      const expected = new URL(appBase)
      return url.origin === expected.origin && !url.hostname.endsWith('stripe.com')
    },
    { timeout: 120_000 },
  )
}

async function createStagingCheckoutSession(): Promise<{
  checkout_url: string
  checkout_session_id: string
  livemode: boolean
}> {
  const response = await fetch(`${apiBase}/v1/billing/checkout`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      Origin: appBase,
    },
    body: JSON.stringify({ plan: 'starter' }),
  })
  if (response.status !== 201) {
    throw new Error(`staging checkout create failed with HTTP ${response.status}`)
  }
  const body = (await response.json()) as {
    checkout_url?: string
    checkout_session_id?: string
    livemode?: boolean
  }
  if (body.livemode === true) {
    throw new Error('refusing live-mode Stripe checkout in E2E')
  }
  if (!body.checkout_session_id?.startsWith('cs_test_')) {
    throw new Error('staging checkout session id is not cs_test_*')
  }
  if (!body.checkout_url?.startsWith('https://checkout.stripe.com/')) {
    throw new Error('staging checkout_url is not a Stripe Checkout URL')
  }
  return {
    checkout_url: body.checkout_url,
    checkout_session_id: body.checkout_session_id,
    livemode: false,
  }
}

async function fillOptionalBilling(page: Page): Promise<void> {
  await fillAcrossFrames(page, [
    'input[name="billingName"]',
    'input[name="name"]',
    'input[autocomplete="name"]',
    'input[autocomplete="cc-name"]',
  ], 'AgentPulse E2E')

  await fillAcrossFrames(page, [
    'input[name="billingAddressLine1"]',
    'input[name="addressLine1"]',
    'input[autocomplete="address-line1"]',
  ], '123 Test Street')

  await fillAcrossFrames(page, [
    'input[name="billingLocality"]',
    'input[name="locality"]',
    'input[autocomplete="address-level2"]',
  ], 'Toronto')

  await fillAcrossFrames(page, [
    'input[name="billingPostalCode"]',
    'input[name="postalCode"]',
    'input[autocomplete="postal-code"]',
  ], 'M5V2T6')

  await selectAcrossFrames(page, [
    'select[name="billingCountry"]',
    'select[name="country"]',
    'select[autocomplete="country"]',
  ], ['CA', 'Canada'])

  await selectAcrossFrames(page, [
    'select[name="billingAdministrativeArea"]',
    'select[name="administrativeArea"]',
    'select[autocomplete="address-level1"]',
  ], ['ON', 'Ontario'])
}

async function fillCardNumber(page: Page, value: string): Promise<void> {
  const selectors = [
    'input[name="cardNumber"]',
    'input[autocomplete="cc-number"]',
    'input[name="number"]',
    'input[placeholder*="1234"]',
    '#cardNumber',
  ]
  await waitAndFill(page, selectors, value, /card number|number/i)
}

async function fillCardExpiry(page: Page, value: string): Promise<void> {
  const selectors = [
    'input[name="cardExpiry"]',
    'input[autocomplete="cc-exp"]',
    'input[name="expiry"]',
    'input[placeholder*="MM"]',
    '#cardExpiry',
  ]
  await waitAndFill(page, selectors, value, /expir/i)
}

async function fillCardCvc(page: Page, value: string): Promise<void> {
  const selectors = [
    'input[name="cardCvc"]',
    'input[autocomplete="cc-csc"]',
    'input[name="cvc"]',
    'input[placeholder*="CVC"]',
    '#cardCvc',
  ]
  await waitAndFill(page, selectors, value, /cvc|cvv|security code/i)
}

async function waitAndFill(
  page: Page,
  selectors: string[],
  value: string,
  roleName: RegExp,
): Promise<void> {
  const deadline = Date.now() + 45_000
  while (Date.now() < deadline) {
    // Prefer accessible name when Stripe exposes it.
    for (const frame of page.frames()) {
      const byRole = frame.getByRole('textbox', { name: roleName }).first()
      if ((await byRole.count().catch(() => 0)) > 0 && (await byRole.isVisible().catch(() => false))) {
        await byRole.fill(value)
        return
      }
    }
    if (await fillAcrossFrames(page, selectors, value)) return
    await page.waitForTimeout(250)
  }
  throw new Error(`could not locate Stripe field matching ${roleName}`)
}

async function fillAcrossFrames(page: Page, selectors: string[], value: string): Promise<boolean> {
  for (const frame of page.frames()) {
    for (const selector of selectors) {
      const locator = frame.locator(selector).first()
      if ((await locator.count().catch(() => 0)) === 0) continue
      if (!(await locator.isVisible().catch(() => false))) continue
      await locator.fill(value)
      return true
    }
  }
  return false
}

async function selectAcrossFrames(page: Page, selectors: string[], values: string[]): Promise<boolean> {
  for (const frame of page.frames()) {
    for (const selector of selectors) {
      const locator = frame.locator(selector).first()
      if ((await locator.count().catch(() => 0)) === 0) continue
      if (!(await locator.isVisible().catch(() => false))) continue
      for (const value of values) {
        try {
          await locator.selectOption({ value })
          return true
        } catch {
          try {
            await locator.selectOption({ label: value })
            return true
          } catch {
            // try next
          }
        }
      }
    }
  }
  return false
}
