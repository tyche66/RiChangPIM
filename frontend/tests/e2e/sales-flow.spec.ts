import { test, expect, type Page } from '@playwright/test'
import { createMockToken } from './helpers'

const MOCK_REFRESH_TOKEN = 'mock-refresh-token-sales'

// Token with full sales permissions (ADMIN_TOKEN lacks proposal:create, quotation:*, share:create)
const SALES_PERMS = ['product:view', 'ai:use', 'proposal:view', 'proposal:create', 'proposal:edit', 'quotation:view', 'quotation:create', 'quotation:edit', 'quotation:confirm', 'share:view', 'share:create']
const SALES_TOKEN = createMockToken({
  sub: '1',
  username: 'admin',
  role_code: 'admin',
  perms: SALES_PERMS,
  exp: Math.floor(Date.now() / 1000) + 3600,
})

const USER_PERMS = SALES_PERMS

// ============ Helpers ============

function routeAuth(page: Page) {
  page.route('**/api/v1/auth/me', (route) => {
    route.fulfill({
      status: 200,
      json: { data: { id: '1', username: 'admin', role_code: 'admin', perms: USER_PERMS } },
    })
  })
  page.route('**/api/v1/auth/refresh', (route) => {
    route.fulfill({ status: 200, json: { data: { access_token: SALES_TOKEN, refresh_token: MOCK_REFRESH_TOKEN } } })
  })
}

const PROD_A = { id: 'prod-a', product_name: '氨基酸洁面泡沫', product_no: 'CLE-001', face_price: 88, stock_status: '充足', status: 'active' }
const PROD_B = { id: 'prod-b', product_name: '清爽爽肤水', product_no: 'TON-002', face_price: 120, stock_status: '充足', status: 'active' }
const PROD_C = { id: 'prod-c', product_name: '轻薄保湿乳', product_no: 'LOT-003', face_price: 150, stock_status: '充足', status: 'active' }
const ALL_PRODUCTS = [PROD_A, PROD_B, PROD_C]

function routeProducts(page: Page) {
  page.route(/\/api\/v1\/products(?:\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    const kw = url.searchParams.get('keyword') || ''
    const status = url.searchParams.get('status') || ''
    let list = ALL_PRODUCTS
    if (kw) list = list.filter(p => p.product_name.includes(kw) || p.product_no.includes(kw))
    if (status) list = list.filter(p => p.status === status)
    route.fulfill({
      status: 200,
      json: { code: 200, data: { list, total: list.length, page: 1, size: 50 } },
    })
  })
}

async function addProduct(page: Page, keyword: string, productName: string) {
  const editor = page.locator('.proposal-item-editor')
  await editor.getByRole('combobox').fill(keyword)
  await page.waitForTimeout(500)
  await page.getByRole('option', { name: new RegExp(productName) }).click()
  await editor.getByRole('button', { name: '添加商品' }).click()
}

async function fillProposalItem(page: Page, index: number, quantity: string, remark: string) {
  const card = page.locator('.item-card').nth(index)
  const quantityInput = card.locator('.el-input-number input')
  await quantityInput.fill(quantity)
  await quantityInput.press('Tab')
  const remarkInput = card.getByPlaceholder('备注（可选）')
  await remarkInput.fill(remark)
  await remarkInput.press('Tab')
}

// ============ Test: Sales full-flow ============

test.describe('Sales Flow: Proposal → Quotation → Share', () => {
  let proposalId = ''
  let quotationId = ''
  let shareToken = ''
  let quotationConfirmed = false

  // Mutable state for proposal GET responses
  let proposalState: 'original' | 'edited' = 'original'

  test.beforeEach(async ({ page }) => {
    await page.addInitScript((arg) => {
      localStorage.setItem('token', arg.token)
      localStorage.setItem('refresh_token', arg.refreshToken)
    }, { token: SALES_TOKEN, refreshToken: MOCK_REFRESH_TOKEN })
    routeAuth(page)
    routeProducts(page)
    // Quotations list + create mock (state-driven)
    await page.route(/\/api\/v1\/quotations(?:\?.*)?$/, async (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          json: {
            code: 200,
            data: {
              list: [{
                id: quotationId,
                quotation_no: 'QUO-2024-999',
                proposal_no: 'PRP-2024-999',
                proposal_name: '测试方案-全自动',
                total_amount: 1140,
                tax_rate: 0.13,
                discount: 1,
                status: quotationConfirmed ? 'confirmed' : 'draft',
                create_time: new Date().toISOString(),
                items: [
                  { product_id: 'prod-a', quantity: 8, unit_price: 75, tax_rate: 0.13, subtotal: 600, product_name: PROD_A.product_name, product_no: PROD_A.product_no, face_price: PROD_A.face_price },
                  { product_id: 'prod-c', quantity: 3, unit_price: 150, tax_rate: 0.13, subtotal: 450, product_name: PROD_C.product_name, product_no: PROD_C.product_no, face_price: PROD_C.face_price },
                ],
              }],
              total: 1,
              page: 1,
              size: 20,
            },
          },
        })
      } else if (route.request().method() === 'POST') {
        const rawBody = route.request().postData()
        const body = JSON.parse(rawBody)
        expect(body.proposal_id).toBe(proposalId)
        expect(body.items.length).toBe(2)
        expect(body.items.some((i: any) => i.product_id === 'prod-a')).toBe(true)
        expect(body.items.some((i: any) => i.product_id === 'prod-c')).toBe(true)
        quotationId = 'quo-flow-001'
        route.fulfill({
          status: 200,
          json: {
            code: 200,
            data: {
              id: quotationId,
              quotation_no: 'QUO-2024-999',
              proposal_id: proposalId,
              proposal_no: 'PRP-2024-999',
              proposal_name: '测试方案-全自动',
              creator_id: '1',
              valid_until: null,
              total_amount: 0,
              subtotal: 0,
              tax_rate: body.tax_rate,
              discount: body.discount,
              status: 'draft',
              create_time: new Date().toISOString(),
              update_time: new Date().toISOString(),
              items: body.items,
            },
          },
        })
      }
    })
    // Proposal detail GET mock (state-driven)
    await page.route('**/api/v1/proposals/**', async (route) => {
      const url = new URL(route.request().url())
      const segments = url.pathname.split('/')
      const id = segments[segments.length - 1]
      if (route.request().method() === 'GET') {
        const isEdited = proposalState === 'edited'
        route.fulfill({
          status: 200,
          json: {
            code: 200,
            data: {
              id: id || 'prop-flow-001',
              proposal_no: 'PRP-2024-999',
              proposal_name: '测试方案-全自动',
              customer_name: '测试客户',
              creator_id: '1',
              status: 'draft',
              ai_polished: false,
              total_face_value: 1180,
              create_time: new Date().toISOString(),
              items: isEdited
                ? [
                    { product_id: 'prod-a', quantity: 8, remark: '首批洁面', product_name: PROD_A.product_name, product_no: PROD_A.product_no, face_price: PROD_A.face_price },
                    { product_id: 'prod-c', quantity: 3, remark: '', product_name: PROD_C.product_name, product_no: PROD_C.product_no, face_price: PROD_C.face_price },
                  ]
                : [
                    { product_id: 'prod-a', quantity: 10, remark: '首批洁面', product_name: PROD_A.product_name, product_no: PROD_A.product_no, face_price: PROD_A.face_price },
                    { product_id: 'prod-b', quantity: 5, remark: '配套爽肤水', product_name: PROD_B.product_name, product_no: PROD_B.product_no, face_price: PROD_B.face_price },
                  ],
            },
          },
        })
      } else if (route.request().method() === 'PUT') {
        const rawBody = route.request().postData()
        const body = JSON.parse(rawBody)
        expect(body.items.length).toBe(2)
        expect(body.items[0].product_id).toBe('prod-a')
        expect(body.items[0].quantity).toBe(8)
        expect(body.items[1].product_id).toBe('prod-c')
        expect(body.items[1].quantity).toBe(3)
        proposalState = 'edited'
        route.fulfill({
          status: 200,
          json: {
            code: 200,
            data: {
              id: id || 'prop-flow-001',
              proposal_no: 'PRP-2024-999',
              proposal_name: '测试方案-全自动',
              customer_name: '测试客户',
              creator_id: '1',
              status: 'draft',
              ai_polished: false,
              total_face_value: 0,
              create_time: new Date().toISOString(),
              items: [
                { product_id: 'prod-a', quantity: 8, remark: '首批洁面', product_name: PROD_A.product_name, product_no: PROD_A.product_no, face_price: PROD_A.face_price },
                { product_id: 'prod-c', quantity: 3, remark: '', product_name: PROD_C.product_name, product_no: PROD_C.product_no, face_price: PROD_C.face_price },
              ],
            },
          },
        })
      }
    })
  })

  test('full sales flow: create proposal with 2 items, edit, create quotation, share, verify public view', async ({ page }) => {
    // ===== PHASE 1: Create proposal with 2 products =====

    await page.route('**/api/v1/proposals', async (route) => {
      if (route.request().method() === 'GET') {
        route.fulfill({ status: 200, json: { code: 200, data: { list: [], total: 0, page: 1, size: 20 } } })
      } else if (route.request().method() === 'POST') {
        const rawBody = route.request().postData()
        const body = JSON.parse(rawBody)
        expect(body.proposal_name).toBe('测试方案-全自动')
        expect(body.customer_name).toBe('测试客户')
        expect(body.items.length).toBe(2)
        expect(body.items[0].product_id).toBe('prod-a')
        expect(body.items[0].quantity).toBe(10)
        expect(body.items[0].remark).toBe('首批洁面')
        expect(body.items[1].product_id).toBe('prod-b')
        expect(body.items[1].quantity).toBe(5)
        expect(body.items[1].remark).toBe('配套爽肤水')
        proposalId = 'prop-flow-001'
        route.fulfill({
          status: 200,
          json: { code: 200, data: { id: proposalId, proposal_no: 'PRP-2024-999', proposal_name: body.proposal_name, customer_name: body.customer_name, creator_id: '1', status: 'draft', ai_polished: false, total_face_value: 0, create_time: new Date().toISOString(), items: body.items } },
        })
      }
    })

    await page.goto('/proposals')
    await expect(page.getByRole('heading', { name: '方案管理' })).toBeVisible()

    // Click "新增方案"
    await page.getByRole('button', { name: '新增方案' }).click()
    await expect(page.getByRole('heading', { name: '新增方案' })).toBeVisible()

    await page.getByLabel('方案名称').fill('测试方案-全自动')
    await page.getByLabel('客户名称').fill('测试客户')

    await addProduct(page, '洁面', PROD_A.product_name)
    await expect(page.locator('.item-card')).toHaveCount(1)
    await fillProposalItem(page, 0, '10', '首批洁面')

    // --- Add product B ---
    await addProduct(page, '爽肤', PROD_B.product_name)
    await expect(page.locator('.item-card')).toHaveCount(2)
    await fillProposalItem(page, 1, '5', '配套爽肤水')

    // Submit
    await page.getByRole('button', { name: '确定' }).click()
    await expect(page.getByText('创建成功', { exact: true })).toBeVisible({ timeout: 5000 })

    // ===== PHASE 2: View proposal detail — product name not UUID =====
    // Proposal GET mock already set up in beforeEach (returns prod-a + prod-b)

    await page.goto(`/proposals/${proposalId}`)
    await expect(page.getByText('测试方案-全自动')).toBeVisible()
    await expect(page.getByText('测试客户')).toBeVisible()

    // Verify product names displayed (not UUIDs)
    await expect(page.getByText('氨基酸洁面泡沫')).toBeVisible()
    await expect(page.getByText('清爽爽肤水')).toBeVisible()
    const bodyText = await page.locator('.items-table').innerText()
    expect(bodyText).not.toContain('prod-a')
    expect(bodyText).not.toContain('prod-b')

    // ===== PHASE 3: Edit proposal — modify qty, delete one, add third =====

    await page.getByRole('button', { name: '编辑' }).click()
    await expect(page.getByText('编辑方案')).toBeVisible()

    // Change quantity of first item from 10 to 8
    const editQuantity = page.locator('.item-card').first().locator('.el-input-number input')
    await editQuantity.fill('8')
    await editQuantity.press('Tab')

    // Delete the second item (prod-b)
    const removeBtnB = page.locator('.item-card').nth(1).getByRole('button', { name: '删除' })
    if (await removeBtnB.count() > 0) {
      await removeBtnB.click()
    } else {
      const closeIcon = page.locator('.item-card').nth(1).locator('.item-remove')
      await closeIcon.click()
    }

    // Search and add third product
    await addProduct(page, '保湿', PROD_C.product_name)
    await expect(page.locator('.item-card')).toHaveCount(2) // prod-a + prod-c (prod-b deleted)

    const newQuantity = page.locator('.item-card').nth(1).locator('.el-input-number input')
    await newQuantity.fill('3')
    await newQuantity.press('Tab')

    await page.getByRole('button', { name: '确定' }).click()
    await expect(page.locator('.el-message--success')).toContainText('更新成功')

    // ===== PHASE 4: Generate quotation — proposal GET prefill =====
    // Route already set up in beforeEach

    await page.getByRole('button', { name: '生成报价单' }).click()

    // Wait for quotation dialog to open (prefilled from proposal)
    await expect(page.getByText('创建报价单')).toBeVisible({ timeout: 5000 })

    // Verify prefill: proposal_id is set
    await expect(page.getByLabel('关联方案ID')).toHaveValue(proposalId)

    const unitPrice = page.locator('.quote-item-row').first().locator('.el-input-number input').nth(1)
    await unitPrice.fill('75')
    await unitPrice.press('Tab')

    // Submit quotation
    await page.getByRole('button', { name: '确定' }).click()
    await expect(page.getByText('创建成功', { exact: true })).toBeVisible({ timeout: 5000 })

    // ===== PHASE 5: Confirm quotation =====

    await page.goto('/quotations')
    await expect(page.getByRole('heading', { name: '报价管理' })).toBeVisible()
    await expect(page.getByText('QUO-2024-999')).toBeVisible()

    await page.route(`**/api/v1/quotations/${quotationId}/confirm`, (route) => {
      quotationConfirmed = true
      route.fulfill({ status: 200, json: { code: 200, data: { id: quotationId, quotation_no: 'QUO-2024-999', proposal_id: proposalId, status: 'confirmed' } } })
    })

    await page.getByRole('button', { name: '确认' }).click()
    await expect(page.locator('.el-message--success')).toContainText('报价已确认')

    // ===== PHASE 6: Create share — QR code canvas + link =====

    await page.route('**/api/v1/shares', async (route) => {
      shareToken = 'share-token-flow-001'
      route.fulfill({
        status: 200,
        json: {
          code: 200,
          data: {
            share_id: 'share-flow-001',
            share_url: `/share/${shareToken}`,
            token: shareToken,
            expire_time: new Date(Date.now() + 24 * 3600 * 1000).toISOString(),
            max_access_count: 100,
          },
        },
      })
    })

    await page.getByRole('button', { name: '分享' }).click()
    await expect(page.getByText('创建分享链接')).toBeVisible()
    await page.getByRole('button', { name: '生成链接' }).click()
    await expect(page.locator('.el-message--success')).toBeVisible({ timeout: 5000 })

    // ShareResultDialog should be visible
    await expect(page.getByText('分享链接已生成')).toBeVisible()

    // Verify share link shown in input
    const shareLinkText = await page.locator('.share-url-input .el-input__inner').inputValue()
    expect(shareLinkText).toContain(shareToken)
    expect(shareLinkText).toBe(`http://localhost:5173/share/${shareToken}`)

    // Verify QR code canvas is present and has content
    const canvas = page.locator('.qr-canvas')
    await expect(canvas).toBeVisible()
    const canvasBounds = await canvas.boundingBox()
    expect(canvasBounds?.width).toBeGreaterThan(50)
    expect(canvasBounds?.height).toBeGreaterThan(50)

    // Try to get canvas data URL
    const canvasDataURL = await page.evaluate(() => {
      const c = document.querySelector('.qr-canvas') as HTMLCanvasElement
      if (c && c.width > 10 && c.height > 10) {
        return c.toDataURL('image/png')
      }
      return null
    })
    expect(canvasDataURL).not.toBeNull()
    expect(canvasDataURL?.startsWith('data:image/png')).toBe(true)

    // ===== PHASE 7: Public share page — no login, see products, no cost =====

    // Clear auth for new navigation
    await page.addInitScript(() => {
      localStorage.removeItem('token')
      localStorage.removeItem('refresh_token')
    })

    await page.route(`**/api/v1/share/${shareToken}`, (route) => {
      route.fulfill({
        status: 200,
        json: {
          code: 200,
          data: {
            share_type: 'quotation',
            target_id: quotationId,
            access_count: 1,
            content: {
              quotation_no: 'QUO-2024-999',
              status: 'confirmed',
              total_amount: 1140,
              items: [
                {
                  product_id: 'prod-a',
                  product_name: PROD_A.product_name,
                  product_no: PROD_A.product_no,
                  face_price: PROD_A.face_price,
                  unit_price: 75,
                  quantity: 8,
                  tax_rate: 0.13,
                  subtotal: 600,
                },
                {
                  product_id: 'prod-c',
                  product_name: PROD_C.product_name,
                  product_no: PROD_C.product_no,
                  face_price: PROD_C.face_price,
                  unit_price: 150,
                  quantity: 3,
                  tax_rate: 0.13,
                  subtotal: 450,
                },
              ],
            },
          },
        },
      })
    })

    await page.goto(`/share/${shareToken}`)
    await expect(page).toHaveURL(`/share/${shareToken}`)

    await expect(page.getByText('有效链接')).toBeVisible()
    await expect(page.getByText('QUO-2024-999')).toBeVisible()
    await expect(page.getByText('已确认')).toBeVisible()
    await expect(page.getByText('氨基酸洁面泡沫')).toBeVisible()
    await expect(page.getByText('轻薄保湿乳')).toBeVisible()
    await expect(page.getByText('¥75.00')).toBeVisible()
    await expect(page.getByText('¥150.00').first()).toBeVisible()
    await expect(page.getByText('¥1140.00')).toBeVisible()
    await expect(page.getByText('AI-PIM 提供技术支持')).toBeVisible()

    // Verify NO cost info
    const sharePageText = await page.locator('.share-content').innerText()
    expect(sharePageText).not.toContain('cost_price')
    expect(sharePageText).not.toContain('成本')
    expect(sharePageText).not.toContain('supplier')
  })
})
