import { test, expect } from '@playwright/test'

import { ADMIN_TOKEN } from './helpers'

test.describe('Previously missing UI coverage', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((token) => {
      localStorage.setItem('token', token)
      localStorage.setItem('refresh_token', 'test-refresh')
    }, ADMIN_TOKEN)
    await page.route('**/api/v1/auth/me', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        code: 200,
        data: {
          id: 'admin',
          username: 'admin',
          role_code: 'admin',
          permissions: ['product:view', 'product:edit', 'product:import', 'file:upload', 'ai:use'],
        },
      }),
    }))
  })

  test('Product Import UI is available', async ({ page }) => {
    await page.goto('/import')
    await expect(page.locator('input[type="file"]')).toBeAttached()
  })

  test('Manual upload UI is available', async ({ page }) => {
    await page.route('**/api/v1/manuals**', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { list: [], total: 0 } }),
    }))
    await page.goto('/manuals')
    await expect(page.locator('input[type="file"]')).toBeAttached()
    await expect(page.getByRole('button', { name: '上传并创建' })).toBeVisible()
  })

  test('Knowledge index and RAG management UI is available', async ({ page }) => {
    await page.route('**/api/v1/manuals**', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { list: [], total: 0 } }),
    }))
    await page.goto('/manuals')
    await expect(page.getByText('说明书状态')).toBeVisible()
    await expect(page.getByText('RAG 问答')).toBeVisible()
    await expect(page.getByRole('button', { name: '提问' })).toBeVisible()
  })
})
