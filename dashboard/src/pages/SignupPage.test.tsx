import { describe, expect, it } from 'vitest'
import { isTrustedStripeCheckoutUrl } from './SignupPage'

describe('public checkout transition', () => {
  it('accepts only the exact Stripe Checkout host over HTTPS', () => {
    expect(isTrustedStripeCheckoutUrl('https://checkout.stripe.com/c/pay/cs_test_example')).toBe(true)
    expect(isTrustedStripeCheckoutUrl('http://checkout.stripe.com/c/pay/cs_test_example')).toBe(false)
    expect(isTrustedStripeCheckoutUrl('https://checkout.stripe.com.evil.example/c/pay/cs_test_example')).toBe(false)
    expect(isTrustedStripeCheckoutUrl('https://evilcheckout.stripe.com/c/pay/cs_test_example')).toBe(false)
    expect(isTrustedStripeCheckoutUrl('https://user:pass@checkout.stripe.com/c/pay/cs_test_example')).toBe(false)
    expect(isTrustedStripeCheckoutUrl('not-a-url')).toBe(false)
  })
})
