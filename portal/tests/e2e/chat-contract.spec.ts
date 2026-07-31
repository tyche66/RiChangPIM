import { test, expect, type Page } from '@playwright/test'

/**
 * 门户 /chat 的对外契约。
 *
 * 这些断言原来长在后台的 `frontend/tests/e2e/ai-features.spec.ts` 里（「AI 智能选品」
 * 自带的一套对话 UI）。T02 把后台那一页换成 iframe 嵌门户 /chat 之后，被测的 DOM 整体
 * 搬到了门户，那 9 条用例连同两条安全不变量一起失效。重新分层后的落点：
 *
 * - cost_price / supplier_id 不得外泄 → backend/tests/unit/test_ai_recommend_sensitive_fields.py
 *   （接口契约，DOM 断言只能证明「这一页没画」，证明不了接口没返回）
 * - iframe 指向门户、令牌只发给门户、握手超时兜底 → frontend/tests/e2e/ai-features.spec.ts
 * - 本文件：空回答兜底、接口失败提示、来源列表、嵌入模式下的外壳收敛
 *
 * `portal.spec.ts` 是 HANDOFF 的红线，不改；「登录 + 流式渲染答案」的正向链路仍由它
 * 覆盖，这里只补它没有覆盖的边界，并且自带 /api 兜底（那个文件是非密闭的）。
 */

const CHAT_PLACEHOLDER = '输入产品搜索、问资料、查质量或做比较'
const SOURCE_UUID = '11111111-1111-1111-1111-111111111111'

function makeJwt(payload: Record<string, unknown>) {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url')
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url')
  return `${header}.${body}.signature`
}

/** 门户账号只有 ai:*，没有 product:view —— 首屏推荐因此不会去打 /products。 */
const ACCESS_TOKEN = makeJwt({
  sub: 'user-1',
  username: 'portal-viewer',
  role_code: 'viewer',
  perms: ['ai:access', 'ai:knowledge'],
  exp: Math.floor(Date.now() / 1000) + 3600,
})
const REFRESH_TOKEN = makeJwt({ sub: 'user-1', type: 'refresh' })

/**
 * 任何没被用例显式 mock 的后端调用都返回 404，避免测试悄悄打到真后端。
 *
 * 必须用锚在 `/api/v1/` 上的正则，不能写 `**​/api/**`：后者会把 Vite dev server 提供的
 * 模块地址 `/src/api/index.ts` 一起吃掉，整个门户直接白屏。
 */
async function installApiFallback(page: Page) {
  await page.route(/^https?:\/\/[^/]+\/api\/v1\//, (route) =>
    route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ code: 404, msg: 'e2e: 该接口未被 mock' }),
    }),
  )
}

function sseFrame(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}

function sseResponse(...frames: string[]) {
  return { status: 200, contentType: 'text/event-stream', body: frames.join('') }
}

async function ask(page: Page, message: string) {
  await page.getByPlaceholder(CHAT_PLACEHOLDER).fill(message)
  await page.getByRole('button', { name: '发送' }).click()
}

test.beforeEach(async ({ page }) => {
  // 兜底必须最先注册：route 是后注册者优先，反了会盖掉各用例自己的 mock。
  await installApiFallback(page)
  await page.addInitScript(
    (arg: { token: string; refreshToken: string }) => {
      localStorage.setItem('token', arg.token)
      localStorage.setItem('refresh_token', arg.refreshToken)
    },
    { token: ACCESS_TOKEN, refreshToken: REFRESH_TOKEN },
  )
})

test.describe('门户 /chat：结果区的兜底与来源', () => {
  test('只回 done、没有正文时落到占位文案，而不是当成失败', async ({ page }) => {
    await page.route('**/api/v1/knowledge/query', (route) =>
      route.fulfill(
        sseResponse(
          sseFrame('meta', { trace_id: 'trace-empty', session_id: 'session-empty' }),
          sseFrame('done', { status: 'completed', confidence: 'low', usage: {} }),
        ),
      ),
    )

    await page.goto('/chat')
    await expect(page).toHaveURL(/\/chat$/)
    await ask(page, '有没有型号 SN-0000 的资料')

    await expect(page.locator('.answer-body__placeholder')).toHaveText(
      '这次查询没有生成答案，可以换个更具体的说法再试一次。',
    )
    // 「没答案」不是「出错」：错误提示不该跟着冒出来。
    await expect(page.locator('.notice--error')).toHaveCount(0)
  })

  test('接口失败时显示后端给的原因，并且先流式、再退回一次性查询', async ({ page }) => {
    let calls = 0
    await page.route('**/api/v1/knowledge/query', (route) => {
      calls += 1
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: { code: 'CAPABILITY_DISABLED', msg: 'Knowledge Gateway 已关闭', retryable: false },
        }),
      })
    })

    await page.goto('/chat')
    await ask(page, '这台设备怎么安装')

    // 文案必须来自后端 detail.msg，不能被前端替换成「请求失败」这种无信息量的兜底。
    await expect(page.locator('.notice--error')).toHaveText('Knowledge Gateway 已关闭')
    // 流式失败且一个事件都没收到时会退回非流式查询，所以是两次请求；
    // 变成 1 次说明降级链路被拆掉了。
    await expect.poll(() => calls, { timeout: 10_000 }).toBe(2)
  })

  test('来源全部渲染，被正文引用的那一条带脚注编号', async ({ page }) => {
    // 后台旧用例里有一条「来源最多显示 3 条」的断言。门户没有这个上限（grep 全仓
    // 没有任何截断逻辑），所以这里改成锁「5 条全渲染」——把现状写死，防止有人日后
    // 悄悄加回一个隐式上限。
    const sources = Array.from({ length: 5 }, (_, i) => ({
      source_id: `chunk:${SOURCE_UUID.slice(0, -1)}${i + 1}`,
      source_type: 'document',
      title: `安装手册 ${i + 1}`,
      quote: `步骤 ${i + 1}`,
    }))

    await page.route('**/api/v1/knowledge/query', (route) =>
      route.fulfill(
        sseResponse(
          sseFrame('meta', { trace_id: 'trace-sources', session_id: 'session-sources' }),
          sseFrame('answer_delta', { text: `见随机附带的安装手册[${sources[0].source_id}]。` }),
          ...sources.map((source) => sseFrame('source', source)),
          sseFrame('done', { status: 'completed', confidence: 'high', usage: {} }),
        ),
      ),
    )

    await page.goto('/chat')
    await ask(page, 'SN-CZ001 安装说明')

    const sourceList = page.locator('.source-list')
    await expect(sourceList.locator('.source-card')).toHaveCount(5)
    await expect(
      page.locator('.section-head').filter({ hasText: '引用来源' }).locator('.section-head__count'),
    ).toHaveText('5 条')

    // 正文里的 [chunk:uuid] 折成角标，且和来源卡上的编号对得上。
    await expect(page.locator('.answer-body .citation')).toHaveText('1')
    await expect(sourceList.locator('.source-card__index').first()).toHaveText('1')
  })
})

/**
 * 宿主页用 route 造，不落盘也不进构建产物：同源（都在 baseURL 上）才能复刻生产环境
 * ——生产 nginx 把门户挂 `/`、后台挂 `/admin/`，iframe 与父页面同源，localStorage
 * 直接共用，`allowedParentOrigins()` 也天然放行。
 */
const EMBED_HOST_HTML = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>embed host</title></head>
<body style="margin:0">
<iframe id="frame" src="/chat?embed=1" style="width:100%;height:680px;border:0"></iframe>
</body></html>`

test.describe('门户 /chat：被后台 iframe 嵌入时的外壳', () => {
  test('嵌入模式收掉门户自己的顶栏，且不会被路由守卫弹回首页', async ({ page }) => {
    await page.route('**/e2e-embed-host.html', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: EMBED_HOST_HTML,
      }),
    )

    await page.goto('/e2e-embed-host.html')

    const frame = page.frameLocator('#frame')
    // 输入框出现 = Conversation.vue 真的挂上了 = 没被路由守卫重定向到首页。
    await expect(frame.getByPlaceholder(CHAT_PLACEHOLDER)).toBeVisible()
    await expect
      .poll(() => page.frames().some((f) => f.url().includes('/chat?embed=1')), {
        timeout: 10_000,
      })
      .toBe(true)

    // 后台已经有一整套顶栏和账户操作，门户再出一个「退出」会误清共享的登录态。
    await expect(frame.locator('.site-header')).toHaveCount(0)
    await expect(frame.locator('.chat-shell')).toHaveClass(/chat-shell--embedded/)
    await expect(frame.locator('html')).toHaveAttribute('data-embed', '1')
    // 站内跳转（例如产品详情跳后台）必须打到父窗口，不在 iframe 里套娃。
    await expect(frame.locator('head base')).toHaveAttribute('target', '_parent')
  })

  test('独立访问 /chat 时门户顶栏仍在（嵌入模式的对照组）', async ({ page }) => {
    await page.goto('/chat')

    await expect(page.locator('.site-header')).toBeVisible()
    await expect(page.locator('.chat-shell')).not.toHaveClass(/chat-shell--embedded/)
    await expect(page.locator('html')).not.toHaveAttribute('data-embed', '1')
  })
})
