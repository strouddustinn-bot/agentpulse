const LEGACY_ACCOUNT_CREDENTIAL_KEY = 'agentpulse.account_credential'

let csrfToken: string | null = null

function clearLegacyBrowserCredential(): void {
  try {
    window.sessionStorage?.removeItem(LEGACY_ACCOUNT_CREDENTIAL_KEY)
    window.localStorage?.removeItem(LEGACY_ACCOUNT_CREDENTIAL_KEY)
  } catch {
    // Storage may be unavailable in privacy modes; ignore.
  }
}

// Best-effort cleanup for pre-cookie browser credentials.
clearLegacyBrowserCredential()

export function getCsrfToken(): string | null {
  return csrfToken
}

export function setCsrfToken(value: string): void {
  const normalized = value.trim()
  if (!normalized) throw new Error('A CSRF token is required')
  csrfToken = normalized
  clearLegacyBrowserCredential()
}

export function clearCredential(): void {
  csrfToken = null
  clearLegacyBrowserCredential()
}
