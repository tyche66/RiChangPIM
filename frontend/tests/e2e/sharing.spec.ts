import { test, expect } from '@playwright/test'

test.describe('Public Share Page Access', () => {
  const shareToken = 'share-abc123'

  test('accesses share page without JWT token', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
    })

    await page.route(`**/api/v1/share/${shareToken}`, (route: any) => {
      route.fulfill({
        status: 200,
        json: {
          data: {
            share_type: 'proposal',
            target_id: 'prop-001',
            access_count: 5,
            content: {
              proposal_name: '夏季护肤方案分享',
              customer_name: '共享客户',
              status: 'draft',
              items: [
                { product_name: '洁面泡沫', face_price: 88, quantity: 50 },
                { product_name: '爽肤水', face_price: 120, quantity: 30 },
              ],
            },
          },
        },
      })
    })

    await page.goto(`/share/${shareToken}`)

    await expect(page).toHaveURL(`/share/${shareToken}`)
    await expect(page.getByText('有效链接')).toBeVisible()
    await expect(page.getByText('夏季护肤方案分享')).toBeVisible()
    await expect(page.getByText('共享客户')).toBeVisible()
    await expect(page.getByText('洁面泡沫')).toBeVisible()
    await expect(page.getByText('爽肤水')).toBeVisible()
    await expect(page.getByText(/访问次数: 5/)).toBeVisible()
    await expect(page.getByText('AI-PIM 提供技术支持')).toBeVisible()
  })

  test('does NOT display sensitive fields on share page', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
    })

    await page.route(`**/api/v1/share/${shareToken}`, (route: any) => {
      route.fulfill({
        status: 200,
        json: {
          data: {
            share_type: 'quotation',
            target_id: 'quo-001',
            access_count: 1,
            content: {
              quotation_no: 'QUO-2024-001',
              status: 'confirmed',
              total_amount: 5000,
              items: [
                {
                  product_name: 'Product A',
                  face_price: 100,
                  unit_price: 80,
                  quantity: 50,
                  cost_price: 40,
                  supplier_id: 'SUP-SECRET',
                  supplier_name: 'Secret Supplier',
                },
              ],
            },
          },
        },
      })
    })

    await page.goto(`/share/${shareToken}`)

    await expect(page.getByText('QUO-2024-001')).toBeVisible()
    await expect(page.getByText('Product A')).toBeVisible()
    await expect(page.getByText('SUP-SECRET')).not.toBeVisible()
    await expect(page.getByText('Secret Supplier')).not.toBeVisible()
  })

  test('shows password prompt when share requires password', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
    })

    await page.route(`**/api/v1/share/${shareToken}`, (route: any) => {
      route.fulfill({
        status: 403,
        json: {
          detail: {
            code: 40304,
            msg: '该分享需要访问密码',
          },
        },
      })
    })

    await page.goto(`/share/${shareToken}`)

    // Use specific locator for the alert component (not the toast message)
    await expect(page.locator('.el-alert--warning').getByText('该分享需要访问密码')).toBeVisible()
    await expect(page.getByPlaceholder('请输入访问密码')).toBeVisible()
    await expect(page.getByRole('button', { name: '验证' })).toBeVisible()

    // Should show "链接失效" tag
    await expect(page.getByText('链接失效')).toBeVisible()
  })

  test('shows error for expired/invalid share link', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
    })

    await page.route(`**/api/v1/share/${shareToken}`, (route: any) => {
      route.fulfill({
        status: 404,
        json: {
          detail: {
            msg: '分享链接已过期',
          },
        },
      })
    })

    await page.goto(`/share/${shareToken}`)

    // The error alert is shown, not the password prompt
    await expect(page.locator('.el-alert--error')).toBeVisible()
    // Use first match to avoid strict mode violation from toast duplicates
    await expect(page.locator('.el-alert__title').filter({ hasText: '分享链接已过期' })).toBeVisible()
    await expect(page.getByText('链接失效')).toBeVisible()
  })

  test('share page does not show admin navigation', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
    })

    await page.route(`**/api/v1/share/${shareToken}`, (route: any) => {
      route.fulfill({
        status: 200,
        json: {
          data: {
            share_type: 'proposal',
            target_id: 'prop-001',
            access_count: 0,
            content: {
              proposal_name: 'Test',
              status: 'draft',
              items: [],
            },
          },
        },
      })
    })

    await page.goto(`/share/${shareToken}`)

    // Should NOT show the main layout sidebar
    await expect(page.getByText('产品管理')).not.toBeVisible()
    await expect(page.getByText('AI 功能')).not.toBeVisible()
    await expect(page.getByText('退出')).not.toBeVisible()
  })
})
