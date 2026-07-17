import { test, expect } from '@playwright/test'
import { ADMIN_TOKEN } from './helpers'

const MOCK_REFRESH_TOKEN = 'mock-refresh-token'
const USER_PERMS = ['product:view', 'ai:use', 'proposal:view', 'proposal:edit', 'share:view']

test.beforeEach(async ({ page }) => {
  // Pass token as argument to make it available in browser context
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

test.describe('AI Chat Source Display', () => {
  test('displays AI chat response with source citations', async ({ page }) => {
    await page.route('**/api/v1/ai/chat', (route: any) => {
      route.fulfill({
        status: 200,
        json: {
          data: {
            answer: '根据您的需求，我推荐以下几款产品。',
            sources: [
              { product_name: '保湿洁面乳', doc_title: '产品文档A' },
              { product_name: '清爽爽肤水', doc_title: '产品文档B' },
            ],
            session_id: 'test-session',
            tool_calls: [],
          },
        },
      })
    })

    await page.goto('/ai-select')

    await expect(page.getByText('AI 智能对话')).toBeVisible()

    await page.getByPlaceholder('输入您的问题').fill('推荐适合夏季的护肤品', { force: true })
    await page.getByRole('button', { name: '发送' }).click({ force: true })

    await expect(page.getByText('推荐适合夏季的护肤品')).toBeVisible()
    await expect(page.getByText('根据您的需求，我推荐以下几款产品。')).toBeVisible()
    await expect(page.locator('.message-sources .el-tag').first()).toBeVisible()
  })

  test('shows fallback message when AI chat returns empty answer', async ({ page }) => {
    await page.route('**/api/v1/ai/chat', (route: any) => {
      route.fulfill({
        status: 200,
        json: { data: { answer: '', sources: [], session_id: 's1', tool_calls: [] } },
      })
    })

    await page.goto('/ai-select')
    await page.getByPlaceholder('输入您的问题').fill('hello', { force: true })
    await page.getByRole('button', { name: '发送' }).click({ force: true })

    await expect(page.getByText('暂无回复')).toBeVisible()
  })

  test('shows error message when AI chat API fails', async ({ page }) => {
    await page.route('**/api/v1/ai/chat', (route: any) => {
      route.fulfill({ status: 500, json: { detail: { msg: 'Internal Server Error' } } })
    })

    await page.goto('/ai-select')
    await page.getByPlaceholder('输入您的问题').fill('hello', { force: true })
    await page.getByRole('button', { name: '发送' }).click({ force: true })

    await expect(page.getByText('AI 服务暂时不可用，请稍后重试')).toBeVisible()
  })

  test('limits sources display to first 3', async ({ page }) => {
    const manySources = Array.from({ length: 5 }, (_, i) => ({
      product_name: `Product ${i + 1}`,
      doc_title: `Doc ${i + 1}`,
    }))

    await page.route('**/api/v1/ai/chat', (route: any) => {
      route.fulfill({
        status: 200,
        json: {
          data: {
            answer: 'Here are results.',
            sources: manySources,
            session_id: 's1',
            tool_calls: [],
          },
        },
      })
    })

    await page.goto('/ai-select')
    await page.getByPlaceholder('输入您的问题').fill('test', { force: true })
    await page.getByRole('button', { name: '发送' }).click({ force: true })

    await expect(page.getByText('Here are results.')).toBeVisible()
    await expect(page.getByText('Product 1')).toBeVisible()
    await expect(page.getByText('Product 3')).toBeVisible()
  })
})

test.describe('AI Recommendation - Verified Products', () => {
  test('displays verified badge for AI-recommended products', async ({ page }) => {
    await page.route('**/api/v1/ai/recommend', (route: any) => {
      route.fulfill({
        status: 200,
        json: {
          data: {
            status: 'success',
            filters_applied: { category_id: 'cat-skincare', max_face_price: 200 },
            products: [
              {
                id: 'p1',
                product_no: 'P001',
                product_name: '氨基酸洁面泡沫',
                brand_id: 'b1',
                category_id: 'cat-skincare',
                face_price: 128,
                stock_status: 'in_stock',
                description: '温和清洁，适合敏感肌',
                _verified: true,
                _verified_by: 'ai-model-v3',
              },
            ],
            rationale: '基于您的预算和肤质需求筛选',
            total: 1,
            sources: [],
          },
        },
      })
    })

    await page.goto('/ai-select')

    await page.getByLabel('需求描述').fill('需要一款温和的洁面产品，预算200以内', { force: true })
    await page.getByRole('button', { name: 'AI 推荐' }).click({ force: true })

    await expect(page.getByText('氨基酸洁面泡沫')).toBeVisible()
    await expect(page.getByText('已验证')).toBeVisible()
    await expect(page.getByText('by ai-model-v3')).toBeVisible()
    await expect(page.getByText('基于您的预算和肤质需求筛选')).toBeVisible()
    await expect(page.getByText('筛选条件')).toBeVisible()
  })

  test('does NOT display cost_price in recommendation results', async ({ page }) => {
    await page.route('**/api/v1/ai/recommend', (route: any) => {
      route.fulfill({
        status: 200,
        json: {
          data: {
            status: 'success',
            filters_applied: {},
            products: [
              {
                id: 'p1',
                product_no: 'P001',
                product_name: 'Test Product',
                face_price: 100,
                cost_price: 50,
                supplier_id: 'sup-123',
                stock_status: 'in_stock',
                _verified: true,
              },
            ],
            rationale: 'test rationale',
            total: 1,
            sources: [],
          },
        },
      })
    })

    await page.goto('/ai-select')
    await page.getByLabel('需求描述').fill('test')
    await page.getByRole('button', { name: 'AI 推荐' }).click()

    await expect(page.locator('text=/cost_price|进价|成本/')).toHaveCount(0)
  })

  test('does NOT display supplier_id in recommendation results', async ({ page }) => {
    await page.route('**/api/v1/ai/recommend', (route: any) => {
      route.fulfill({
        status: 200,
        json: {
          data: {
            status: 'success',
            filters_applied: {},
            products: [
              {
                id: 'p1',
                product_name: 'Test Product',
                face_price: 100,
                supplier_id: 'SUP-SECRET-123',
                stock_status: 'in_stock',
              },
            ],
            rationale: 'test',
            total: 1,
            sources: [],
          },
        },
      })
    })

    await page.goto('/ai-select')
    await page.getByLabel('需求描述').fill('test')
    await page.getByRole('button', { name: 'AI 推荐' }).click()

    await expect(page.locator('text=/supplier_id|供应商ID/')).toHaveCount(0)
  })

  test('shows degraded banner when AI parse fails', async ({ page }) => {
    await page.route('**/api/v1/ai/recommend', (route: any) => {
      route.fulfill({
        status: 200,
        json: {
          data: {
            status: 'parse_failed',
            filters_applied: {},
            products: [{ product_name: 'Fallback' }],
            rationale: 'AI 解析失败',
            total: 1,
            sources: [],
          },
        },
      })
    })

    await page.goto('/ai-select')
    await page.getByLabel('需求描述').fill('vague request')
    await page.getByRole('button', { name: 'AI 推荐' }).click()

    await expect(page.locator('.el-alert--warning')).toBeVisible()
    await expect(page.getByText('AI 解析失败，请修正需求后重试')).toBeVisible()
  })

  test('shows error toast when recommend API fails', async ({ page }) => {
    await page.route('**/api/v1/ai/recommend', (route: any) => {
      route.fulfill({ status: 500, json: { detail: { msg: 'Service Unavailable' } } })
    })

    await page.goto('/ai-select')
    await page.getByLabel('需求描述').fill('test')
    await page.getByRole('button', { name: 'AI 推荐' }).click()

    // Wait for the error message to appear (it may auto-dismiss after 3s)
    await page.waitForSelector('.el-message--error', { state: 'visible', timeout: 10000 })
  })
})
