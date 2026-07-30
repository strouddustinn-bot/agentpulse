/**
 * External navigation helper.
 *
 * Production path uses location.assign. Browser E2E can install
 * window.__apNavigateExternal to capture destinations without leaving the SPA.
 */
export function navigateExternal(url: string): void {
  const hook = (window as unknown as { __apNavigateExternal?: (next: string) => void })
    .__apNavigateExternal
  if (typeof hook === 'function') {
    hook(url)
    return
  }
  window.location.assign(url)
}
