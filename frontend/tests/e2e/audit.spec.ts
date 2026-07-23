import { test, expect } from '@playwright/test'
import { ADMIN_TOKEN, createMockToken } from './helpers'

// V1.2 §5.5 / RELEASE_GATE §3 — audit E2E:
//   - admin can reach /logs and see the audit table
//   - non-admin (no stats:view / audit:view perm) is redirected away
//   - /api/v1/audit/operation-logs responses must NOT contain request_body

const MOCK_REFRESH = 'mock-refresh-token'

function mockLoginByRole(page: any, role: 'admin' | 'sales' | 'viewer') {
  const profiles = {
    admin: {
      token: ADMIN_TOKEN,
      perms: ['product:view', 'product:import', 'ai:use', 'proposal:view', 'proposal:edit', 'share:view', 'stats:view', 'audit:view'],
      role_code: 'admin',
      username: 'admin',
    },
    sales: {
      // Sales has product:view but no audit:view / stats:view — should be blocked.
      token: createMockToken({
        sub: '5',
        username: 'sales1',
        role_code: 'sales',
        perms: ['product:view', 'proposal:view'],
        exp: Math.floor(Date.now() / 1000) + 3600,
      }),
      perms: ['product:view', 'proposal:view'],
      role_code: 'sales',
      username: 'sales1',
    },
    viewer: {
      token: createMockToken({
        sub: '6',
        username: 'viewer1',
        role_code: 'viewer',
        perms: ['product:view'],
        exp: Math.floor(Date.now() / 1000) + 3600,
      }),
      perms: ['product:view'],
      role_code: 'viewer',
      username: 'viewer1',
    },
  } as const

  const p = profiles[role]

  return page.route('**/api/v1/auth/login', (route: any) => {
    route.fulfill({
      status: 200,
      json: { data: { access_token: p.token, refresh_token: MOCK_REFRESH } },
    })
  }).then(() =>
    page.route('**/api/v1/auth/me', (route: any) => {
      route.fulfill({ status: 200, json: {
        data: { id: '1', username: p.username, role_code: p.role_code, perms: p.perms },
      } })
    })
  )
}

test.describe('Audit page RBAC and content', () => {
  test('admin can open the audit page and the response body must omit request_body', async ({ page }) => {
    await mockLoginByRole(page, 'admin')

    let apiPayload: any = null
    await page.route('**/api/v1/audit/operation-logs', (route: any) => {
      apiPayload = {
        list: [{
          operate_time: '2026-07-20T08:00:00',
          action: 'login',
          module: 'auth',
          user_id: 'admin-uuid',
          target_id: null,
          response_code: 200,
          ip: '127.0.0.1',
          // Even if backend leaked request_body, the table MUST NOT render it.
          request_body: 'SHOULD_NOT_APPEAR',
        }],
        total: 1,
        page: 1,
        size: 20,
      }
      route.fulfill({ status: 200, json: { code: 200, data: apiPayload } })
    })
    await page.route('**/api/v1/stats/shares', (route: any) => route.fulfill({
      status: 200, json: { data: { total_shares: 0, total_access: 0, active_shares: 0, top_accessed: [] } },
    }))
    await page.route('**/api/v1/stats/hot-products', (route: any) => route.fulfill({
      status: 200, json: { data: { items: [] } },
    }))

    await page.goto('/login')
    await page.getByPlaceholder('用户名').fill('admin')
    await page.getByPlaceholder('密码').fill('admin123')
    await page.getByRole('button', { name: '登录' }).click()

    // Navigate directly to the logs route.
    await page.goto('/logs')
    await expect(page).toHaveURL(/\/logs/)

    // Audit content visible.
    await expect(page.getByText('login').first()).toBeVisible({ timeout: 10_000 })

    // request_body redaction invariant — never in DOM.
    await expect(page.locator('body')).not.toContainText('SHOULD_NOT_APPEAR')
    await expect(page.locator('body')).not.toContainText('request_body')
  })

  test('sales role (no audit:view) cannot reach the audit page', async ({ page }) => {
    await mockLoginByRole(page, 'sales')

    await page.route('**/api/v1/products', (route: any) => {
      route.fulfill({ status: 200, json: { data: { list: [], total: 0, page: 1, size: 20 } } })
    })

    await page.goto('/login')
    await page.getByPlaceholder('用户名').fill('sales1')
    await page.getByPlaceholder('密码').fill('anything')
    await page.getByRole('button', { name: '登录' }).click()

    // Try direct navigation to /logs — the router guard should redirect to /products.
    await page.goto('/logs')
    await expect(page).toHaveURL(/\/products/, { timeout: 10_000 })
  })

  test('viewer role (no audit:view) cannot reach the audit page', async ({ page }) => {
    await mockLoginByRole(page, 'viewer')

    await page.route('**/api/v1/products', (route: any) => {
      route.fulfill({ status: 200, json: { data: { list: [], total: 0, page: 1, size: 20 } } })
    })

    await page.goto('/login')
    await page.getByPlaceholder('用户名').fill('viewer1')
    await page.getByPlaceholder('密码').fill('anything')
    await page.getByRole('button', { name: '登录' }).click()

    await page.goto('/logs')
    await expect(page).toHaveURL(/\/products/, { timeout: 10_000 })
  })
})
