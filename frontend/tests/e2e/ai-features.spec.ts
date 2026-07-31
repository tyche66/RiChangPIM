import { test, expect } from '@playwright/test'
import { ADMIN_TOKEN, installApiFallback } from './helpers'

/**
 * AI 选品（/ai-select）现在只是一个壳：标题条 + 指向门户 `/chat?embed=1` 的 iframe。
 * 原来这个文件里的 9 条用例测的是后台自己的 AI 对话 / 推荐表单，那些 UI 已经整体搬进
 * 门户，选择器改不回来，所以覆盖按不变量真正的执行位置重新分层：
 *
 * - 「结果里不得出现 cost_price / supplier_id」是接口契约，锁在
 *   backend/tests/unit/test_ai_recommend_sensitive_fields.py（DOM 断言证明不了接口没泄露）。
 * - 对话渲染、空回答兜底、接口失败提示、来源列表 → portal/tests/e2e/chat-contract.spec.ts。
 * - 这里只留后台真正负责的事：iframe 是否指向门户、令牌交接是否只发给门户、
 *   握手超时的兜底 UI 是否真的能用。
 *
 * 刻意不断言 iframe 内部内容：dev 下后台与门户不同源，父页面读不到子文档，硬写只会
 * 得到一条永远不稳的测试。下面用 route 把门户 `/chat` 换成替身页，替身页复刻门户对外
 * 的契约（发 pim-embed-ready、收 pim-embed-session），这样这套用例不依赖门户 dev
 * server 起没起，也不会去测门户的内部实现。
 */

const MOCK_REFRESH_TOKEN = 'mock-refresh-token'
const USER_PERMS = ['product:view', 'ai:use', 'proposal:view', 'proposal:edit', 'share:view']

/** AISelect.vue 在 DEV 下的 portalOrigin 默认值。用正则精确匹配，避免误拦后台自己的请求。 */
const PORTAL_CHAT_URL = /^http:\/\/localhost:5174\/chat(\?|$)/

/** 另一个 origin 的页面，用来验证令牌不会被广播给它。 */
const OTHER_ORIGIN_URL = /^http:\/\/localhost:5999\//

const PORTAL_STUB_HTML = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>portal chat stub</title></head>
<body>
<p id="handshake">未收到会话</p>
<script>
  window.addEventListener('message', function (event) {
    var data = event.data || {}
    if (data.type !== 'pim-embed-session') return
    document.getElementById('handshake').textContent =
      'token=' + (data.token || '') + ' refresh=' + (data.refreshToken || '') + ' origin=' + event.origin
  })
  parent.postMessage({ type: 'pim-embed-ready' }, '*')
</script>
</body></html>`

/** 冒充「别的站点」：同样喊 ready，但它不该收到任何令牌。 */
const OTHER_ORIGIN_STUB_HTML = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>other origin stub</title></head>
<body>
<p id="handshake">未收到会话</p>
<script>
  window.addEventListener('message', function (event) {
    var data = event.data || {}
    if (data.type !== 'pim-embed-session') return
    document.getElementById('handshake').textContent = 'leaked=' + (data.token || '')
  })
  parent.postMessage({ type: 'pim-embed-ready' }, '*')
</script>
</body></html>`

test.beforeEach(async ({ page }) => {
  // 兜底必须最先注册（route 是后注册者优先），否则会盖掉下面各用例自己的 mock。
  await installApiFallback(page)

  await page.addInitScript(
    (arg: { token: string; refreshToken: string }) => {
      localStorage.setItem('token', arg.token)
      localStorage.setItem('refresh_token', arg.refreshToken)
    },
    { token: ADMIN_TOKEN, refreshToken: MOCK_REFRESH_TOKEN }
  )

  await page.route('**/api/v1/auth/me', (route: any) => {
    route.fulfill({
      status: 200,
      json: {
        data: {
          id: '1',
          username: 'admin',
          role_code: 'admin',
          perms: USER_PERMS,
        },
      },
    })
  })
})

async function stubPortalChat(page: any, html = PORTAL_STUB_HTML) {
  await page.route(PORTAL_CHAT_URL, (route: any) => {
    route.fulfill({ status: 200, contentType: 'text/html; charset=utf-8', body: html })
  })
}

test.describe('AI 选品：门户 /chat 的嵌入壳', () => {
  test('renders an iframe pointing at the portal /chat?embed=1', async ({ page }) => {
    await stubPortalChat(page)
    await page.goto('/ai-select')

    // 「AI 选品」在页面上出现三次（侧边菜单项、布局的 h1、壳自己的 kicker），
    // 按文本找会撞 strict mode，所以直接锚定壳自己的那一处。
    await expect(page.locator('.portal-kicker')).toHaveText('AI 选品')

    const frame = page.locator('iframe.portal-frame')
    await expect(frame).toHaveAttribute('src', 'http://localhost:5174/chat?embed=1')
    await expect(frame).toHaveAttribute('title', 'AI 选品工作台')
  })

  test('shows the loading hint until the portal document finishes loading', async ({ page }) => {
    // 故意让 /chat 慢 1.5 秒返回，才能稳定观察到「正在载入」这一帧。
    await page.route(PORTAL_CHAT_URL, async (route: any) => {
      await new Promise((resolve) => setTimeout(resolve, 1500))
      await route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: PORTAL_STUB_HTML,
      })
    })

    await page.goto('/ai-select')
    await expect(page.getByText('正在载入 AI 选品工作台…')).toBeVisible()
    await expect(page.getByText('正在载入 AI 选品工作台…')).toBeHidden({ timeout: 10_000 })
  })

  test('hands the admin session to the portal frame with an explicit target origin', async ({
    page,
  }) => {
    await stubPortalChat(page)
    await page.goto('/ai-select')

    const adminOrigin = new URL(page.url()).origin
    const handshake = page.frameLocator('iframe.portal-frame').locator('#handshake')
    await expect(handshake).toHaveText(
      `token=${ADMIN_TOKEN} refresh=${MOCK_REFRESH_TOKEN} origin=${adminOrigin}`
    )

    // 握手成功就不该出现超时兜底提示。
    await expect(page.locator('.portal-alert')).toHaveCount(0)
  })

  test('never posts the session to a frame from another origin', async ({ page }) => {
    await stubPortalChat(page)
    await page.route(OTHER_ORIGIN_URL, (route: any) => {
      route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: OTHER_ORIGIN_STUB_HTML,
      })
    })

    await page.goto('/ai-select')
    await expect(page.frameLocator('iframe.portal-frame').locator('#handshake')).toContainText(
      `token=${ADMIN_TOKEN}`
    )

    // 再塞一个别的 origin 的 iframe，它也喊 ready，但 origin / source 都不匹配。
    await page.evaluate(() => {
      const rogue = document.createElement('iframe')
      rogue.id = 'rogue-frame'
      rogue.src = 'http://localhost:5999/embed.html'
      document.body.appendChild(rogue)
    })

    const rogue = page.frameLocator('#rogue-frame').locator('#handshake')
    await expect(rogue).toHaveText('未收到会话')
    // 给父页面留出反应时间，确认不是「还没来得及泄露」。
    await page.waitForTimeout(1000)
    await expect(rogue).toHaveText('未收到会话')
  })

  test('offers reload fallback when the portal never completes the handshake', async ({ page }) => {
    let requests = 0
    await page.route(PORTAL_CHAT_URL, (route: any) => {
      requests += 1
      route.abort()
    })

    await page.goto('/ai-select')
    // iframe 的子资源请求是文档 load 之后才发的，goto 返回时计数可能还是 0，
    // 所以这里必须轮询而不是立即断言。
    await expect.poll(() => requests, { timeout: 10_000 }).toBe(1)

    // 看门狗 8 秒，留足余量。
    const alert = page.locator('.portal-alert')
    await expect(alert).toBeVisible({ timeout: 15_000 })
    await expect(alert).toContainText('AI 选品工作台还没有响应')

    await alert.getByRole('button', { name: '重新加载' }).click()
    await expect(alert).toBeHidden()
    await expect.poll(() => requests, { timeout: 10_000 }).toBe(2)
  })

  test('opens the portal chat standalone in a new tab', async ({ page, context }) => {
    await stubPortalChat(page)
    await context.route(PORTAL_CHAT_URL, (route: any) => {
      route.fulfill({
        status: 200,
        contentType: 'text/html; charset=utf-8',
        body: PORTAL_STUB_HTML,
      })
    })
    await page.goto('/ai-select')

    const [opened] = await Promise.all([
      context.waitForEvent('page'),
      page.locator('.portal-tools').getByRole('button', { name: '新窗口打开' }).click(),
    ])
    expect(opened.url()).toBe('http://localhost:5174/chat')
    await opened.close()
  })
})
