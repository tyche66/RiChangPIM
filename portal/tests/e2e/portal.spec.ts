import { test, expect } from '@playwright/test'

function makeJwt(payload: Record<string, unknown>) {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url')
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url')
  return `${header}.${body}.signature`
}

test('home renders portal shell', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('RiChangPIM Portal')).toBeVisible()
})

test('chat route redirects to home when unauthenticated', async ({ page }) => {
  await page.goto('/chat')
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByText('RiChangPIM Portal')).toBeVisible()
})

test('login and stream knowledge query', async ({ page }) => {
  const accessToken = makeJwt({
    sub: 'user-1',
    role_code: 'viewer',
    perms: ['ai:access', 'ai:knowledge'],
  })
  const refreshToken = makeJwt({ sub: 'user-1', type: 'refresh' })

  await page.route('**/api/v1/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          access_token: accessToken,
          refresh_token: refreshToken,
        },
      }),
    })
  })

  await page.route('**/api/v1/knowledge/query', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'event: meta\ndata: {"trace_id":"trace-1","session_id":"session-1"}\n\n',
        'event: answer_delta\ndata: {"text":"已找到资料。"}\n\n',
        'event: source\ndata: {"source_id":"chunk:11111111-1111-1111-1111-111111111111","source_type":"document","title":"安装手册","quote":"步骤一"}\n\n',
        'event: products\ndata: {"items":[{"id":"p1","product_no":"SN-CZ001","product_name":"会议桌","face_price_display":99999,"stock_status_display":"unknown"}]}\n\n',
        'event: done\ndata: {"status":"completed","confidence":"medium","usage":{}}\n\n',
      ].join(''),
    })
  })

  await page.route('**/api/v1/knowledge/sources/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          source_id: 'chunk:11111111-1111-1111-1111-111111111111',
          source_type: 'document',
          title: '安装手册',
          section: 'section-1',
          quote: '步骤一',
        },
      }),
    })
  })

  await page.goto('/')
  await page.getByLabel('账号').fill('admin')
  await page.getByLabel('密码').fill('admin123')
  await page.getByRole('button', { name: '进入 Portal' }).click()
  await expect(page).toHaveURL(/\/chat$/)

  await page.getByPlaceholder('输入产品搜索、问资料、查质量或做比较').fill('SN-CZ001 安装说明')
  await page.getByRole('button', { name: '发送' }).click()

  await expect(page.locator('.panel--answer').getByText('已找到资料。')).toBeVisible()
  await expect(page.locator('.card-list').first().getByRole('heading', { name: '会议桌' })).toBeVisible()
  await expect(page.locator('.card-list').first().getByText('待核价')).toBeVisible()
  await expect(page.locator('.card-list').first().getByText('库存待确认')).toBeVisible()
  await expect(page.locator('.card-list').nth(1).getByText('安装手册')).toBeVisible()

  const [sourceResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().includes('/api/v1/knowledge/sources/chunk%3A11111111')),
    page.getByRole('button', { name: '打开' }).click(),
  ])
  expect(sourceResponse.ok()).toBeTruthy()
})
