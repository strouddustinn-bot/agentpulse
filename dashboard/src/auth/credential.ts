const STORAGE_KEY = 'agentpulse.account_credential'

export function getCredential(): string | null {
  const value = window.sessionStorage.getItem(STORAGE_KEY)
  return value && value.trim() ? value.trim() : null
}

export function setCredential(value: string): void {
  const normalized = value.trim()
  if (!normalized) throw new Error('An account credential is required')
  window.sessionStorage.setItem(STORAGE_KEY, normalized)
}

export function clearCredential(): void {
  window.sessionStorage.removeItem(STORAGE_KEY)
}
