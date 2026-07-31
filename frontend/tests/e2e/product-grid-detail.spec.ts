import { test, expect, type Page } from '@playwright/test'
import { createMockToken, installApiFallback } from './helpers'

/**
 * 回归：产品列表 → 卡片视图 → 点卡片进产品详情页，实测白屏（验收退回的第 1 条）。
 *
 * 失因不在详情页本身，而在导航方式：这个回调曾经是
 * `window.open('/products/' + id)`。后台是以 base '/admin/' 构建的
 * （scripts/build_frontends.sh 里 VITE_BASE_PATH=/admin/），根绝对路径
 * '/products/x' 在 nginx 里落进 `location /`（门户 SPA），门户没有这条路由，
 * 于是新标签页白屏。现在走 router.push({ name: 'ProductDetail' })。
 *
 * 三条断言要同时钉住，少一条都会被同一个 bug 蒙过去：
 *   1. 没多出一个标签页 —— window.open 会在 context 里多一个 page；
 *   2. URL 是 SPA 内的 /products/<id>，不是整页重载；
 *   3. 详情页真把这条产品渲染出来了（编号 + 名称），不是空壳。
 * 第三条不能省：漏 mock 详情接口时兜底会回 data:null，页面照样「不白」，
 * 只有断言到具体编号才会露出来。
 */

const REFRESH_TOKEN = 'mock-refresh-token-grid-detail'
const PERMS = ['product:view', 'product:edit']
const TOKEN = createMockToken({
  sub: '1',
  username: 'admin',
  role_code: 'admin',
  perms: PERMS,
  exp: Math.floor(Date.now() / 1000) + 3600,
})

// 封面按真实列表的形状给：cover_image_url 是站内相对路径，不是绝对地址。
const COVER_URL = '/api/v1/files/f-cover-001/content?token=mock-file-token'

const PRODUCT = {
  id: 'p-grid-001',
  product_no: 'GRID-001',
  product_name: '卡片视图详情页产品',
  brand_name: '测试品牌',
  category_name: '洁面',
  face_price: 128,
  cost_price: 60,
  stock_status: 'in_stock',
  status: 'active',
  cover_image_id: 'f-cover-001',
  cover_image_url: COVER_URL,
  cover_image_filename: 'cover.jpg',
  create_time: '2026-07-20T08:00:00Z',
  update_time: '2026-07-20T08:00:00Z',
}

const DETAIL_URL_RE = new RegExp(`/products/${PRODUCT.id}$`)

// ============ Helpers ============

async function routeAuth(page: Page) {
  await page.route('**/api/v1/auth/me', (route) => {
    route.fulfill({
      status: 200,
      json: { data: { id: '1', username: 'admin', role_code: 'admin', perms: PERMS } },
    })
  })
}

// 列表：正则以 $ 收尾，故意不吃 /products/<id>（详情单独 mock，见下）。
async function routeProducts(page: Page) {
  await page.route(/\/api\/v1\/products(?:\?.*)?$/, (route) => {
    route.fulfill({
      status: 200,
      json: { code: 200, data: { list: [PRODUCT], total: 1, page: 1, size: 20 } },
    })
  })
}

async function routeProductDetail(page: Page) {
  await page.route(`**/api/v1/products/${PRODUCT.id}`, (route) => {
    route.fulfill({
      status: 200,
      json: { code: 200, data: { ...PRODUCT, images: [], scene_images: [] } },
    })
  })
}

// 视图模式存在 localStorage（usePreference，pim:pref: 前缀，字符串原样存）。
// 切换按钮是纯图标、没有可访问名字，靠点它定位很脆，进页面前把偏好写死。
async function presetViewMode(page: Page, mode: 'table' | 'grid') {
  await page.addInitScript((m) => {
    localStorage.setItem('pim:pref:products.viewMode', m as string)
  }, mode)
}

/**
 * 记录浏览器真正发出的封面图请求。
 *
 * 不断言 DOM 上的 src：封面 URL 被兜底 route 回成 JSON，el-image 解码失败后会把
 * <img> 换成 #error 插槽，那时候再读 src 就是在赌时序。请求已经发出去了，事后换
 * 插槽也改不了这个事实 —— 钉网络层，顺便也就是「浏览器到底拉了多大的图」本身。
 */
function recordCoverRequests(page: Page): string[] {
  const urls: string[] = []
  page.on('request', (req) => {
    if (/\/api\/v1\/files\/[^/]+\/content/.test(req.url())) urls.push(req.url())
  })
  return urls
}

async function expectDetailRendered(page: Page) {
  await expect(page).toHaveURL(DETAIL_URL_RE)
  await expect(page.locator('.product-no').first()).toHaveText(`[${PRODUCT.product_no}]`)
  await expect(page.locator('.product-name').first()).toHaveText(PRODUCT.product_name)
}

// ============ Tests ============

test.describe('产品列表 → 产品详情页', () => {
  test.beforeEach(async ({ page }) => {
    // 兜底必须最先注册（route 是后注册者优先），否则会盖掉下面几条。
    await installApiFallback(page)
    await page.addInitScript(
      (arg) => {
        localStorage.setItem('token', arg.token)
        localStorage.setItem('refresh_token', arg.refreshToken)
      },
      { token: TOKEN, refreshToken: REFRESH_TOKEN },
    )
    await routeAuth(page)
    await routeProducts(page)
    await routeProductDetail(page)
  })

  test('卡片视图点卡片：SPA 内跳转、不开新标签、详情有内容', async ({ page }) => {
    await presetViewMode(page, 'grid')
    const popups: Page[] = []
    page.context().on('page', (p) => popups.push(p))

    await page.goto('/products')
    const tile = page.locator('.product-tile').filter({ hasText: PRODUCT.product_name })
    await expect(tile).toBeVisible()

    await tile.click()

    await expectDetailRendered(page)
    expect(popups, 'window.open 又回来了：新标签页按根路径加载会落到门户 → 白屏').toHaveLength(0)
  })

  test('表格视图点「查看」：同一条路径也不能整页跳转', async ({ page }) => {
    await presetViewMode(page, 'table')
    const popups: Page[] = []
    page.context().on('page', (p) => popups.push(p))

    await page.goto('/products')
    const view = page.getByRole('button', { name: '查看' }).first()
    await expect(view).toBeVisible()
    await view.click()

    await expectDetailRendered(page)
    expect(popups, 'window.open 又回来了：新标签页按根路径加载会落到门户 → 白屏').toHaveLength(0)
  })

  test('列表封面只拉缩略图：表格 w=192、卡片 w=480', async ({ page }) => {
    // 滚轮卡顿的修法（验收退回的第 3 条）：列表不许挂原图。库里封面基本是
    // 4000×3000，一页 20 行光解码就是 GB 级位图，滚动时反复丢弃/重解码。
    await presetViewMode(page, 'table')
    const covers = recordCoverRequests(page)

    await page.goto('/products')
    await expect(page.locator('.product-thumb').first()).toBeVisible()
    await expect.poll(() => covers.length, { timeout: 10_000 }).toBeGreaterThan(0)
    expect(
      covers.filter((u) => !u.includes('w=192')),
      '表格缩略图漏了 w=192，等于在拉 12MP 原图',
    ).toEqual([])

    covers.length = 0
    await page.locator('.view-mode-toggle .el-radio-button:has(input[value="grid"])').click()
    await expect(page.locator('.product-tile')).toBeVisible()
    await expect.poll(() => covers.length, { timeout: 10_000 }).toBeGreaterThan(0)
    expect(covers.filter((u) => !u.includes('w=480')), '卡片瓦片漏了 w=480').toEqual([])
  })
})
