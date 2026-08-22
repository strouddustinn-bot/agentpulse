import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it } from 'vitest'
import SignupPage, {
  isCheckoutPlan,
  isTrustedStripeCheckoutUrl,
} from './SignupPage'

afterEach(() => {
  cleanup()
})

describe('bounded Starter checkout', () => {
  it('accepts only the exact Stripe Checkout host over HTTPS', () => {
    expect(isTrustedStripeCheckoutUrl('https://checkout.stripe.com/c/pay/cs_test_example')).toBe(true)
    expect(isTrustedStripeCheckoutUrl('http://checkout.stripe.com/c/pay/cs_test_example')).toBe(false)
    expect(isTrustedStripeCheckoutUrl('https://checkout.stripe.com.evil.example/c/pay/cs_test_example')).toBe(false)
    expect(isTrustedStripeCheckoutUrl('https://evilcheckout.stripe.com/c/pay/cs_test_example')).toBe(false)
    expect(isTrustedStripeCheckoutUrl('https://user:pass@checkout.stripe.com/c/pay/cs_test_example')).toBe(false)
    expect(isTrustedStripeCheckoutUrl('not-a-url')).toBe(false)
  })

  it('recognizes only Starter as a checkout plan', () => {
    expect(isCheckoutPlan('starter')).toBe(true)
    expect(isCheckoutPlan('pro')).toBe(false)
    expect(isCheckoutPlan('business')).toBe(false)
    expect(isCheckoutPlan(null)).toBe(false)
  })

  it('does not expose Pro or Business checkout when the URL requests Pro', () => {
    render(
      <MemoryRouter initialEntries={['/signup?plan=pro']}>
        <SignupPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('Selected plan').parentElement?.textContent).toContain('Starter')

    expect(
      screen.getByRole('button', { name: /Continue to secure checkout/i }),
    ).toBeTruthy()

    expect(
      screen.queryByRole('button', { name: /^Pro\b/i }),
    ).toBeNull()

    expect(
      screen.queryByRole('button', { name: /^Business\b/i }),
    ).toBeNull()

    expect(screen.getByText('agentpulse.ca/signup')).toBeTruthy()
    expect(screen.queryByRole('link', { name: /agentpulse\.ca\/signup/i })).toBeNull()
  })
})
