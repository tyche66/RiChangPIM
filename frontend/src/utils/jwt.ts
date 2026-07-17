export function decodeJwt(token: string): { header: Record<string, unknown>; payload: Record<string, unknown>; signature: string } | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const header = JSON.parse(atob(parts[0]))
    const payload = JSON.parse(atob(parts[1]))
    return { header, payload, signature: parts[2] }
  } catch {
    return null
  }
}

export function isTokenExpired(token: string): boolean {
  const decoded = decodeJwt(token)
  if (!decoded?.payload?.exp) return false
  const now = Math.floor(Date.now() / 1000)
  return (decoded.payload.exp as number) < now
}
