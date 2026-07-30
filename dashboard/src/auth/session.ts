/**
 * In-memory session helpers for the browser console.
 *
 * Auth is the Worker HttpOnly cookie. CSRF lives in memory only.
 * Nothing here writes credentials to sessionStorage/localStorage.
 */

import { ApiError, getAccount, type AccountResponse } from '../api/client'
import { getCsrfToken } from './credential'

export type SessionState =
  | { status: 'loading' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; account: AccountResponse }
  | { status: 'inactive'; account: AccountResponse; reason: string }

export function isEntitlementUsable(status: string): boolean {
  return status === 'active' || status === 'grace'
}

export async function loadSession(): Promise<SessionState> {
  try {
    const account = await getAccount()
    if (!isEntitlementUsable(account.entitlement_status)) {
      return {
        status: 'inactive',
        account,
        reason: account.entitlement_status === 'blocked'
          ? 'Subscription is inactive. Billing must be restored before host enrollment.'
          : 'Subscription entitlement is not active.',
      }
    }
    return { status: 'authenticated', account }
  } catch (error) {
    if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
      return { status: 'anonymous' }
    }
    throw error
  }
}

/** True only when a CSRF token is already held in memory (post-claim or bootstrap). */
export function hasCsrfInMemory(): boolean {
  return getCsrfToken() !== null
}
