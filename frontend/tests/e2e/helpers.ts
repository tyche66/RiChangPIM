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

/**
 * 兜住所有没被单独 mock 的 /api 请求，让 e2e 变成密闭的。
 *
 * 为什么必须有：vite dev 会把 /api 代理到真后端（vite.config.ts 里的
 * VITE_API_PROXY_TARGET || http://localhost:8000）。这里用的是 createMockToken
 * 造的假 JWT，真后端一定判 401；而 src/api/index.ts:77-91 的 401 拦截器会去
 * /auth/refresh，refresh 同样 401，于是走到 :70-75 的 `_retry` 分支执行
 * `window.location.href = '/login'`——**整页硬跳转**。
 *
 * 后果是：本机没起后端时（代理连不上，拿不到 response.status）测试全绿，
 * 一旦本机 8000 上恰好有后端在跑，任何漏 mock 的接口都会在测试中途把页面踹去
 * /login，报错现场是「element was detached from the DOM」或「元素找不到」，
 * 跟真正的失因（漏了一个 mock）毫无字面关系，极难排查。让结果取决于本机有没有
 * 起后端，本身就是缺陷。
 *
 * 注册顺序：Playwright 的 route 是后注册者优先，所以这个兜底必须**最先**注册，
 * 各用例自己的 page.route 才能盖住它。
 *
 * 匹配范围只能是 `**\/api/v1/**`（axios baseURL，见 src/api/index.ts:18），
 * 不能图省事写 `**\/api/**`：vite dev 按真实路径发源码模块，`/src/api/index.ts`
 * 会被后者一并拦掉，整个应用直接白屏。
 *
 * 兜底响应刻意给「合法但空」的载荷而不是 abort：abort 会让各 view 弹一片
 * el-message 错误提示，反而干扰断言。设 E2E_TRACE_API=1 可以把漏 mock 的
 * 接口打出来。
 */
export async function installApiFallback(page: {
  route: (pattern: string, handler: (route: unknown) => void) => Promise<void>
}): Promise<void> {
  await page.route('**/api/v1/**', (route: any) => {
    if (process.env.E2E_TRACE_API) {
      console.log(`[e2e] unmocked API request: ${route.request().method()} ${route.request().url()}`)
    }
    route.fulfill({ status: 200, json: { code: 200, data: null, items: [], total: 0 } })
  })
}
