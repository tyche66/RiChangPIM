import { test, expect } from '@playwright/test'
import { ADMIN_TOKEN } from './helpers'

const MOCK_REFRESH_TOKEN = 'mock-refresh-token'
const USER_PERMS = ['product:view', 'ai:use', 'proposal:view', 'proposal:edit', 'share:view']

test.beforeEach(async ({ page }) => {
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
      json: { data: { id: '1', username: 'admin', role_code: 'admin', perms: USER_PERMS } },
    })
  })
})

test.describe('Proposal Structured Polish UI', () => {
  const proposalId = 'prop-001'

  test('displays AI polish results in structured sections', async ({ page }) => {
    await page.route(`**/api/v1/proposals/${proposalId}`, (route: any) => {
      route.fulfill({
        status: 200,
        json: { code: 200, data: {
          id: proposalId,
          proposal_no: 'PRP-2024-001',
          proposal_name: '夏季护肤方案',
          customer_name: '测试客户',
          status: 'draft',
          ai_polished: true,
          ai_polish_model: 'gpt-4',
          ai_polish_at: '2024-01-15T10:00:00Z',
          ai_polish_content: JSON.stringify({
            summary: '本方案精选了3款适合夏季使用的护肤产品，具有清爽不油腻的特点。',
            item_reasons: [
              '产品1：氨基酸洁面泡沫，温和清洁不紧绷。',
              '产品2：清爽爽肤水，收敛毛孔控油。',
              '产品3：轻薄保湿乳，补水不粘腻。',
            ],
            industry_phrases: ['清爽控油', '温和配方', '夏季必备'],
          }),
          items: [
            { product_id: 'p1', quantity: 100, remark: '首批' },
          ],
        } },
      })
    })

    await page.goto(`/proposals/${proposalId}`)

    await expect(page.getByText('夏季护肤方案')).toBeVisible()
    await expect(page.getByText('测试客户')).toBeVisible()

    await expect(page.getByText('整体亮点')).toBeVisible()
    await expect(page.getByText('本方案精选了3款适合夏季使用的护肤产品')).toBeVisible()

    await expect(page.getByText('单品推荐理由')).toBeVisible()
    await expect(page.getByText('氨基酸洁面泡沫，温和清洁不紧绷。')).toBeVisible()

    await expect(page.getByText('行业话术')).toBeVisible()
    await expect(page.getByText('清爽控油')).toBeVisible()

    await expect(page.getByText('已润色')).toBeVisible()
    await expect(page.getByText('gpt-4')).toBeVisible()
  })

  test('shows polish failure state with raw data', async ({ page }) => {
    await page.route(`**/api/v1/proposals/${proposalId}`, (route: any) => {
      route.fulfill({
        status: 200,
        json: { code: 200, data: {
          id: proposalId,
          proposal_no: 'PRP-2024-002',
          proposal_name: '失败方案',
          status: 'draft',
          ai_polished: true,
          ai_polish_content: 'invalid json {broken',
          items: [],
        } },
      })
    })

    await page.goto(`/proposals/${proposalId}`)
    await expect(page.getByText('失败方案')).toBeVisible()

    await expect(page.getByText('AI 润色未能生成有效内容')).toBeVisible()
    await expect(page.getByText('invalid json {broken')).toBeVisible()
    await expect(page.getByText('润色失败')).toBeVisible()
  })

  test('AI polish button triggers API call and refreshes', async ({ page }) => {
    let polishCalled = false

    await page.route(`**/api/v1/proposals/${proposalId}`, (route: any) => {
      route.fulfill({
        status: 200,
        json: { code: 200, data: {
          id: proposalId,
          proposal_no: 'PRP-2024-003',
          proposal_name: '待润色方案',
          status: 'draft',
          ai_polished: false,
          ai_polish_content: null,
          items: [],
        } },
      })
    })

    await page.route(`**/api/v1/ai/proposal/${proposalId}/polish`, (route: any) => {
      polishCalled = true
      route.fulfill({ status: 200, json: { success: true } })
    })

    await page.goto(`/proposals/${proposalId}`)
    await expect(page.getByText('待润色方案')).toBeVisible()

    await page.getByRole('button', { name: 'AI 润色' }).click()

    expect(polishCalled).toBe(true)

    await expect(page.locator('.el-message--success')).toBeVisible()
    await expect(page.locator('.el-message--success')).toContainText('AI 润色完成')
  })

  test('shows retry button (重新润色) after polish failure', async ({ page }) => {
    await page.route(`**/api/v1/proposals/${proposalId}`, (route: any) => {
      route.fulfill({
        status: 200,
        json: { code: 200, data: {
          id: proposalId,
          proposal_no: 'PRP-2024-004',
          proposal_name: '失败重试方案',
          status: 'draft',
          ai_polished: true,
          ai_polish_content: 'parse error',
          items: [],
        } },
      })
    })

    await page.goto(`/proposals/${proposalId}`)
    await expect(page.getByText('润色失败')).toBeVisible()

    await expect(page.getByRole('button', { name: '重新润色' })).toBeVisible()
  })

  test('toggle raw JSON visibility', async ({ page }) => {
    const polishContent = JSON.stringify({
      summary: 'Test summary',
      item_reasons: ['Reason 1'],
      industry_phrases: ['phrase1'],
    })

    await page.route(`**/api/v1/proposals/${proposalId}`, (route: any) => {
      route.fulfill({
        status: 200,
        json: { code: 200, data: {
          id: proposalId,
          proposal_name: 'JSON Toggle Test',
          status: 'draft',
          ai_polished: true,
          ai_polish_content: polishContent,
          items: [],
        } },
      })
    })

    await page.goto(`/proposals/${proposalId}`)

    await expect(page.getByText('整体亮点')).toBeVisible()
    await expect(page.getByRole('button', { name: '查看原始 JSON' })).toBeVisible()

    await page.getByRole('button', { name: '查看原始 JSON' }).click()
    await expect(page.getByRole('button', { name: '隐藏原始 JSON' })).toBeVisible()
    await expect(page.getByText(polishContent)).toBeVisible()

    await page.getByRole('button', { name: '隐藏原始 JSON' }).click()
    await expect(page.getByText(polishContent)).not.toBeVisible()
  })
})
