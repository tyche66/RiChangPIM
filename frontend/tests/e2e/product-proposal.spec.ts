import { test, expect, type Page } from '@playwright/test'
import { createMockToken, installApiFallback } from './helpers'

const MOCK_REFRESH_TOKEN = 'mock-refresh-token-proposal'

// Token with product + proposal permissions
const PERMS = [
  'product:view',
  'product:create',
  'product:edit',
  'proposal:view',
  'proposal:create',
]
const TOKEN = createMockToken({
  sub: '1',
  username: 'admin',
  role_code: 'admin',
  perms: PERMS,
  exp: Math.floor(Date.now() / 1000) + 3600,
})

// ============ Helpers ============

function routeAuth(page: Page) {
  page.route('**/api/v1/auth/me', (route) => {
    route.fulfill({
      status: 200,
      json: { data: { id: '1', username: 'admin', role_code: 'admin', perms: PERMS } },
    })
  })
}

const PROD_ACTIVE = {
  id: 'p-active-001',
  product_name: '氨基酸洁面泡沫',
  product_no: 'CLE-001',
  face_price: 88,
  stock_status: 'in_stock',
  status: 'active',
}
const PROD_INACTIVE = {
  id: 'p-inactive-001',
  product_name: '已下架产品',
  product_no: 'OFF-001',
  face_price: 50,
  stock_status: 'out_of_stock',
  status: 'inactive',
}

function visibleSelectionRow(page: Page, productName: string) {
  return page.locator('tr').filter({ hasText: productName }).filter({ visible: true })
}

async function selectActiveProduct(page: Page) {
  // 点「制作方案」之后，el-table 要插入一列复选框并重排整张表；重排期间点下去的
  // 那一下会落在被替换掉的旧节点上，静默丢失（这就是 152/164 交替失败的原因）。
  // 先等选择条出现，确认 proposalMode 已经渲染完，再点。
  await expect(page.getByText('已选 0 项')).toBeVisible()

  const mobileCard = page
    .locator('.proposal-mobile-item')
    .filter({ hasText: PROD_ACTIVE.product_name })
  if (await mobileCard.isVisible()) {
    await mobileCard.click()
    await expect(mobileCard).toHaveClass(/selected/)
    return
  }

  const row = visibleSelectionRow(page, PROD_ACTIVE.product_name)
  const checkbox = row.getByRole('checkbox')
  await expect(checkbox).toBeEnabled()
  // el-checkbox 的真实 input 是 opacity:0 的，只能点外层包装 + force。
  await row.locator('.el-checkbox').click({ force: true })
  // 自证这一下真的选上了：否则失败会指向下游的「已选 1 项」，看不出是点击丢了。
  await expect(checkbox).toBeChecked()
}

function routeProducts(page: Page) {
  page.route(/\/api\/v1\/products(?:\?.*)?$/, (route) => {
    route.fulfill({
      status: 200,
      json: {
        code: 200,
        data: {
          list: [PROD_ACTIVE, PROD_INACTIVE],
          total: 2,
          page: 1,
          size: 20,
        },
      },
    })
  })
}

function routeProposals(page: Page, createdProposalId: { value: string }) {
  // 原来写的 '/api/v1/proposals' 是「无通配的相对 URL」，只能精确匹配不带查询串的请求，
  // 于是只有 POST 命中、GET 列表（?page=1&size=20）永远落进兜底。加 `**` 前缀和 `*` 结尾
  // 才能把两种都接住；详情 /proposals/<id> 因为含 `/` 不会被 `*` 吃掉。
  page.route('**/api/v1/proposals*', async (route) => {
    if (route.request().method() === 'GET') {
      route.fulfill({
        status: 200,
        json: { code: 200, data: { list: [], total: 0, page: 1, size: 20 } },
      })
    } else if (route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData()!)
      createdProposalId.value = 'prop-test-001'
      route.fulfill({
        status: 200,
        json: {
          code: 200,
          data: {
            id: createdProposalId.value,
            proposal_no: 'PRP-TEST-001',
            proposal_name: body.proposal_name,
            customer_name: body.customer_name,
            creator_id: '1',
            status: 'draft',
            ai_polished: false,
            total_face_value: 0,
            create_time: new Date().toISOString(),
            items: body.items,
          },
        },
      })
    }
  })
}

// ============ Tests ============

test.describe('Products → Proposal flow', () => {
  let createdProposalId: { value: string }

  test.beforeEach(async ({ page }) => {
    // 兜底必须最先注册（route 是后注册者优先），否则会盖掉下面 routeAuth/routeProducts/routeProposals。
    await installApiFallback(page)
    await page.addInitScript((arg) => {
      localStorage.setItem('token', arg.token)
      localStorage.setItem('refresh_token', arg.refreshToken)
    }, { token: TOKEN, refreshToken: MOCK_REFRESH_TOKEN })
    routeAuth(page)
    routeProducts(page)
    createdProposalId = { value: '' }
    routeProposals(page, createdProposalId)
  })

  test('enters proposal mode and shows selection column', async ({ page }) => {
    await page.goto('/products')
    await expect(page.getByRole('button', { name: '制作方案' })).toBeVisible()
    await page.getByRole('button', { name: '制作方案' }).click()
    await expect(page.getByText('已选 0 项')).toBeVisible()
    await expect(page.getByRole('button', { name: '取消' })).toBeVisible()
    await expect(page.getByRole('button', { name: '完成' })).toBeVisible()
    await expect(page.locator('.el-table__header-wrapper .el-checkbox')).toBeVisible()
  })

  test('inactive product is not selectable', async ({ page }) => {
    await page.goto('/products')
    await page.getByRole('button', { name: '制作方案' }).click()
    await expect(page.getByText('已选 0 项')).toBeVisible()
    const inactiveRow = visibleSelectionRow(page, PROD_INACTIVE.product_name)
    const checkbox = inactiveRow.getByRole('checkbox')
    await expect(checkbox).toBeDisabled()
  })

  test('selects active product and completes proposal prefill', async ({ page }) => {
    await page.goto('/products')
    await page.getByRole('button', { name: '制作方案' }).click()
    await selectActiveProduct(page)
    await expect(page.getByText('已选 1 项')).toBeVisible()
    await page.getByRole('button', { name: '完成' }).click()
    await expect(page).toHaveURL(/\/proposals\?mode=create&selection_token=/)
    await expect(page.getByRole('heading', { name: '新增方案' })).toBeVisible()
    await expect(page.locator('.item-card')).toHaveCount(1)
    await expect(page.locator('.item-card')).toContainText(PROD_ACTIVE.product_name)
  })

  test('cancel exits proposal mode and clears selection', async ({ page }) => {
    await page.goto('/products')
    await page.getByRole('button', { name: '制作方案' }).click()
    await selectActiveProduct(page)
    await expect(page.getByText('已选 1 项')).toBeVisible()
    await page.getByRole('button', { name: '取消' }).click()
    await expect(page.getByText('已选 0 项')).not.toBeVisible()
    await expect(page.locator('.el-table__header-wrapper .el-checkbox')).not.toBeVisible()
  })
})
