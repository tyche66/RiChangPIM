import { test, expect } from '@playwright/test'
import { ADMIN_TOKEN } from './helpers'

const MOCK_REFRESH_TOKEN = 'mock-refresh-token-admin'

async function mockLogin(page: any, options: { status?: number; responseBody?: any } = {}) {
  const { status = 200, responseBody = { data: { access_token: ADMIN_TOKEN, refresh_token: MOCK_REFRESH_TOKEN } } } = options
  await page.route('**/api/v1/auth/login', (route: any) => {
    route.fulfill({ status, json: responseBody })
  })
}

async function mockCurrentUser(page: any, options: { status?: number; body?: any } = {}) {
  const { status = 200, body = { id: '1', username: 'admin', role_code: 'admin', perms: ['product:view', 'product:import', 'ai:use', 'proposal:view', 'proposal:edit', 'share:view', 'stats:view'] } } = options
  await page.route('**/api/v1/auth/me', (route: any) => {
    route.fulfill({ status, json: { data: body } })
  })
}

async function loginViaUI(page: any, username = 'admin', password = 'admin123') {
  await page.goto('/login')
  await expect(page.getByRole('heading', { name: 'AI-PIM' })).toBeVisible()
  await page.getByPlaceholder('用户名').fill(username)
  await page.getByPlaceholder('密码').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
}

test.describe('Admin Login UI', () => {
  test.beforeEach(async ({ page }) => {
    await mockLogin(page)
    await mockCurrentUser(page)
  })

  test('shows login form with required fields', async ({ page }) => {
    await page.goto('/login')

    await expect(page.getByRole('heading', { name: 'AI-PIM 产品信息管理平台' })).toBeVisible()
    await expect(page.getByPlaceholder('用户名')).toBeVisible()
    await expect(page.getByPlaceholder('密码')).toBeVisible()
    await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
  })

  test('shows validation errors for empty fields', async ({ page }) => {
    await page.goto('/login')
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page.locator('.el-form-item__error')).toHaveCount(2)
  })

  test('navigates to products after successful login', async ({ page }) => {
    await page.route('**/api/v1/products', (route: any) => {
      route.fulfill({ status: 200, json: { items: [], total: 0 } })
    })

    await loginViaUI(page)

    await expect(page).toHaveURL(/\/products/)
    const token = await page.evaluate(() => localStorage.getItem('token'))
    expect(token).toBe(ADMIN_TOKEN)
  })

  test('shows error message on failed login', async ({ page }) => {
    await mockLogin(page, {
      status: 401,
      responseBody: { detail: { msg: '用户名或密码错误' } },
    })

    await loginViaUI(page)

    await expect(page).toHaveURL(/\/login/)
    const errorMsg = page.locator('.el-message--error')
    await expect(errorMsg).toBeVisible({ timeout: 10000 })
    await expect(errorMsg).toContainText('用户名或密码错误')
  })

  test('redirects to original page after login', async ({ page }) => {
    await page.route('**/api/v1/auth/me', (route: any) => {
      route.fulfill({
        status: 200,
        json: { data: { id: '1', username: 'admin', role_code: 'admin', perms: ['ai:use'] } },
      })
    })

    await page.goto('/login?redirect=/ai-select')
    await page.getByPlaceholder('用户名').fill('admin')
    await page.getByPlaceholder('密码').fill('admin123')
    await page.getByRole('button', { name: '登录' }).click()

    await expect(page).toHaveURL(/\/ai-select/)
  })

  test('logout clears auth state and redirects to login', async ({ page }) => {
    await page.route('**/api/v1/products', (route: any) => {
      route.fulfill({ status: 200, json: { items: [], total: 0 } })
    })
    await page.route('**/api/v1/auth/logout', (route: any) => {
      route.fulfill({ status: 200, json: {} })
    })

    await loginViaUI(page)
    await expect(page).toHaveURL(/\/products/)

    await page.getByRole('button', { name: '退出' }).dispatchEvent('click')

    await expect(page).toHaveURL(/\/login/, { timeout: 10000 })
    await expect.poll(async () => {
      try {
        return await page.evaluate(() => localStorage.getItem('token'))
      } catch {
        return 'navigation-in-progress'
      }
    }).toBeNull()
  })
})
