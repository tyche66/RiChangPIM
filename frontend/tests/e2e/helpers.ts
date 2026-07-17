// Helper to create a mock JWT token with embedded claims
// Uses standard base64 with padding for browser atob compatibility
export function createMockToken(payload: Record<string, unknown> = {}): string {
  const header = toBase64(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const body = toBase64(JSON.stringify(payload))
  return `${header}.${body}.mock-signature`
}

function toBase64(str: string): string {
  return Buffer.from(str).toString('base64')
}

// Admin token with full permissions
export const ADMIN_TOKEN = createMockToken({
  sub: '1',
  username: 'admin',
  role_code: 'admin',
  perms: ['product:view', 'product:import', 'ai:use', 'proposal:view', 'proposal:edit', 'share:view', 'stats:view'],
  exp: Math.floor(Date.now() / 1000) + 3600,
})

// User token with limited permissions
export const USER_TOKEN = createMockToken({
  sub: '2',
  username: 'user',
  role_code: 'user',
  perms: ['product:view', 'ai:use'],
  exp: Math.floor(Date.now() / 1000) + 3600,
})
