import { defineConfig, devices } from '@playwright/test'

/**
 * Phase 4B browser E2E.
 *
 * Default project `mocked` exercises the console against a fully mocked Worker
 * contract so CI and local agents can prove claim/session/enroll/portal/logout
 * and storage hygiene without staging-app DNS.
 *
 * Project `staging-live` is opt-in and requires:
 *   AP_E2E_BASE_URL=https://staging-app.agentpulse.ca
 *   AP_E2E_API_BASE_URL=https://staging-api.agentpulse.ca
 * Optional:
 *   AP_E2E_CLAIM_NONCE=<one-time claim nonce>  # skips Checkout automation
 */
const isCI = !!process.env.CI
const stagingBase = process.env.AP_E2E_BASE_URL?.replace(/\/+$/, '')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  workers: isCI ? 2 : undefined,
  reporter: isCI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  use: {
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [
    {
      name: 'mocked',
      testMatch: /.*\.mocked\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        baseURL: 'http://127.0.0.1:4173',
      },
    },
    ...(stagingBase
      ? [
          {
            name: 'staging-live',
            testMatch: /.*\.staging\.spec\.ts/,
            timeout: 180_000,
            use: {
              ...devices['Desktop Chrome'],
              baseURL: stagingBase,
              // Hosted Stripe Checkout + webhook claim can exceed default timeouts.
              actionTimeout: 30_000,
              navigationTimeout: 120_000,
            },
          },
        ]
      : []),
  ],
  webServer: {
    command:
      'npm run build && npm run preview -- --host 127.0.0.1 --port 4173 --strictPort',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !isCI,
    timeout: 180_000,
    env: {
      ...process.env,
      // Mocked E2E hits the same-origin mock routes installed by fixtures.
      VITE_API_BASE_URL: 'http://127.0.0.1:4173',
    },
  },
})
