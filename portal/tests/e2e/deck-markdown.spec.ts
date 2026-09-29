import { test, expect, type Page, type Route } from '@playwright/test'

/**
 * 查询结果区交互与展示的验收用例。
 * 全部走本地 mock，不碰任何真实后端；图片用 1×1 GIF 代替真实文件。
 */

const PNG_1X1 = Buffer.from(
  'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7',
  'base64',
)

function makeJwt(payload: Record<string, unknown>) {
  const header = Buffer.from(JSON.stringify({ alg: 'HS256', typ: 'JWT' })).toString('base64url')
  const body = Buffer.from(JSON.stringify(payload)).toString('base64url')
  return `${header}.${body}.signature`
}

const ACCESS_TOKEN = makeJwt({ sub: 'user-1', role_code: 'admin', perms: ['product:view', 'ai:access'] })
const REFRESH_TOKEN = makeJwt({ sub: 'user-1', type: 'refresh' })

type Fixture = {
  /** 推荐产品（未查询状态） */
  recommended?: Array<Record<string, unknown>>
  /** 查询返回的候选产品 */
  products?: Array<Record<string, unknown>>
  /** 答案里的 Markdown 原文 */
  answer?: string
  /** 这些 URL 一律返回 404，用来验证 fallback */
  brokenImages?: string[]
  /** 引用来源 */
  sources?: Array<Record<string, unknown>>
}

function product(index: number, extra: Record<string, unknown> = {}) {
  return {
    id: `p${index}`,
    product_no: `SN-CZ00${index}`,
    product_name: `会议桌 ${index}`,
    brand_name: '圣奥',
    category_name: '会议桌',
    face_price: 6510 + index,
    stock_status: 'in_stock',
    cover_image_url: `/api/v1/files/cover-${index}/content?token=t`,
    ...extra,
  }
}

async function installFixtures(page: Page, fixture: Fixture) {
  await page.route('**/api/v1/auth/login', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN } }),
    })
  })
  await page.route('**/api/v1/auth/refresh', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { access_token: ACCESS_TOKEN, refresh_token: REFRESH_TOKEN } }),
    })
  })
  await page.route('**/api/v1/products**', async (route: Route) => {
    const items = fixture.recommended ?? []
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 200, data: { list: items, total: items.length, page: 1, size: items.length } }),
    })
  })
  await page.route('**/api/v1/knowledge/query', async (route: Route) => {
    const products = fixture.products ?? []
    const body = [
      'event: meta\ndata: {"trace_id":"trace-1","session_id":"session-1"}\n\n',
      `event: answer_delta\ndata: ${JSON.stringify({ text: fixture.answer ?? '' })}\n\n`,
      ...(fixture.sources || []).map(
        (source) => `event: source\ndata: ${JSON.stringify(source)}\n\n`,
      ),
      `event: products\ndata: ${JSON.stringify({ items: products })}\n\n`,
      'event: done\ndata: {"status":"completed","confidence":"medium","usage":{}}\n\n',
    ].join('')
    await route.fulfill({ status: 200, contentType: 'text/event-stream', body })
  })
  await page.route('**/api/v1/files/**', async (route: Route) => {
    const url = route.request().url()
    if ((fixture.brokenImages || []).some((broken) => url.includes(broken))) {
      await route.fulfill({ status: 404, contentType: 'text/plain', body: 'gone' })
      return
    }
    await route.fulfill({ status: 200, contentType: 'image/gif', body: PNG_1X1 })
  })
}

async function login(page: Page) {
  await page.goto('/')
  await page.getByLabel('账号').fill('admin')
  await page.getByLabel('密码').fill('admin123')
  await page.getByRole('button', { name: '进入 Portal' }).click()
  await expect(page).toHaveURL(/\/chat$/)
}

async function submitQuery(page: Page, text: string) {
  await page.getByPlaceholder('输入产品搜索、问资料、查质量或做比较').fill(text)
  await page.getByRole('button', { name: '发送' }).click()
  await expect(page.locator('.panel--answer')).toBeVisible()
}

function deckSlots(page: Page) {
  return page.locator('.hero-deck__slot')
}

/** 卡片布局高度。卡位是旋转的，getBoundingClientRect 会算出含旋转的包围盒，所以用 offsetHeight。 */
async function slotHeights(page: Page) {
  return page.locator('.hero-deck__slot').evaluateAll((nodes) =>
    nodes.map((node) => (node as HTMLElement).offsetHeight),
  )
}

/** 窄屏（≤1024px）会把扇形拍平成可横向滑动的卡片带，方向和交互都不同。 */
async function isFlattenedDeck(page: Page) {
  return page.locator('.hero-deck__track').evaluate((node) => getComputedStyle(node).display === 'flex')
}

/** 等平滑滚动停稳，再读 window.scrollY，否则量到的是滚动中间值。 */
async function settleScroll(page: Page) {
  let previous = Number.NaN
  for (let i = 0; i < 12; i += 1) {
    const current = await page.evaluate(() => window.scrollY)
    if (current === previous) return current
    previous = current
    await page.waitForTimeout(120)
  }
  return previous
}

/**
 * 把鼠标放到卡堆上再滚。先瞬时回到页顶（html 是 scroll-behavior: smooth，
 * 不指定 instant 会和后面的轮换抢滚动），这样 hover 不需要再做
 * scrollIntoViewIfNeeded，鼠标落点不会在等待期间被页面滚动带走。
 */
async function hoverDeck(page: Page) {
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
  await page.waitForTimeout(250)
  await page.locator('.hero-deck').hover()
  await settleScroll(page)
  // html 是 scroll-behavior: smooth，hover 内部触发的滚动是异步的，
  // 落点会停在滚动过程中的旧坐标上。按当前几何重新定位一次鼠标。
  const box = await page.locator('.hero-deck').boundingBox()
  if (box) await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.waitForTimeout(150)
}

/** 窄屏没有鼠标滚轮可用，用卡堆自带的上一组/下一组按钮，交互路径等价。 */
async function wheelStep(page: Page, direction: 1 | -1, times = 1) {
  if (await isFlattenedDeck(page)) {
    const name = direction === 1 ? '下一组产品' : '上一组产品'
    for (let i = 0; i < times; i += 1) await page.getByRole('button', { name }).click()
    return
  }
  await hoverDeck(page)
  for (let i = 0; i < times; i += 1) {
    await page.mouse.wheel(0, direction * 240)
    await page.waitForTimeout(260)
  }
}

test.describe('查询结果区：叠卡 / 图片 / Markdown', () => {
  test('未查询状态展示推荐卡片，图片正常渲染且不出现空白图片区', async ({ page }) => {
    const broken: string[] = []
    await installFixtures(page, {
      recommended: [product(1), product(2), product(3), product(4), product(5)],
      brokenImages: broken,
    })
    await login(page)

    await expect(deckSlots(page)).toHaveCount(5)
    // 每张卡的媒体区要么有 <img>，要么有带文字的占位块，不允许空白
    const media = page.locator('.hero-deck .product-card__media')
    await expect(media).toHaveCount(5)
    for (let i = 0; i < 5; i += 1) {
      await expect(media.nth(i).locator('img.product-card__image')).toBeVisible()
      await expect(media.nth(i)).toHaveAttribute('data-image-state', 'ok')
    }
    // 没有 broken image：所有 img 都成功加载
    const loaded = await page.locator('.hero-deck img.product-card__image').evaluateAll((nodes) =>
      nodes.map((node) => (node as HTMLImageElement).naturalWidth),
    )
    expect(loaded.every((width) => width > 0)).toBeTruthy()
    // 未查询状态不能被误显示成查询结果
    await expect(page.locator('.workspace')).toHaveCount(0)
  })

  test('未查询状态图片缺失时展示统一占位，卡片高度不塌', async ({ page }) => {
    // 推荐产品没有 cover_image_url，也没有 images —— 走字段兼容后的占位
    await installFixtures(page, {
      recommended: [
        product(1, { cover_image_url: null }),
        product(2, { cover_image_url: undefined }),
        product(3, { cover_image_url: '' }),
      ],
    })
    await login(page)

    await expect(deckSlots(page)).toHaveCount(3)
    const heights = await slotHeights(page)
    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(2)
    const placeholders = page.locator('.hero-deck .product-card__placeholder')
    await expect(placeholders).toHaveCount(3)
    // 占位不是空白：有图标 + 文字
    await expect(placeholders.first().locator('svg')).toBeVisible()
    await expect(placeholders.first().locator('.product-card__placeholder-text')).not.toBeEmpty()
  })

  test('主图字段为空时回退到 images 数组里的第一张产品图', async ({ page }) => {
    // 列表接口（backend/app/api/v1/products.py 的 _product_list_response）在主图
    // 没设 is_cover 时 cover_image_url 是 null，但 images[].file_url 里有图。
    // 前端做字段兼容：主图拿不到就退回第一张产品图，而不是显示占位。
    await installFixtures(page, {
      recommended: [
        product(1, {
          cover_image_url: null,
          images: [{ file_url: '/api/v1/files/gallery-1/content?token=t' }],
        }),
        product(2, {
          cover_image_url: '   ',
          images: [
            { file_url: '/api/v1/files/gallery-2/content?token=t' },
            { file_url: '/api/v1/files/gallery-3/content?token=t' },
          ],
        }),
        // 非白名单协议的地址一律判死，不允许进 <img src>
        product(3, { cover_image_url: 'javascript:alert(1)' }),
      ],
    })
    await login(page)

    const images = page.locator('.hero-deck img.product-card__image')
    await expect(images).toHaveCount(2)
    await expect(images.nth(0)).toHaveAttribute('src', '/api/v1/files/gallery-1/content?token=t')
    await expect(images.nth(1)).toHaveAttribute('src', '/api/v1/files/gallery-2/content?token=t')
    // 第三张是危险协议 → 走占位；且 src 里不出现 undefined/null/空串
    const srcs = await page.locator('.hero-deck img.product-card__image').evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('src') || ''),
    )
    expect(srcs.some((src) => /undefined|null|^$/.test(src))).toBeFalsy()
    expect(srcs.some((src) => src.includes('javascript:'))).toBeFalsy()
    await expect(page.locator('.hero-deck .product-card__placeholder')).toHaveCount(1)
  })

  test('图片加载失败时统一 fallback，且不会重复触发 error', async ({ page }) => {
    const errors: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text())
    })
    await installFixtures(page, {
      recommended: [product(1), product(2, { cover_image_url: '/api/v1/files/cover-2/content?token=broken' })],
      brokenImages: ['/api/v1/files/cover-2/content'],
    })
    await login(page)

    await expect(deckSlots(page)).toHaveCount(2)
    // 失败那张显示占位，src 不会停留在坏地址上
    const media = page.locator('.hero-deck .product-card__media')
    await expect(media.nth(1)).toHaveAttribute('data-image-state', 'error')
    await expect(media.nth(1).locator('.product-card__placeholder')).toBeVisible()
    await expect(media.nth(0)).toHaveAttribute('data-image-state', 'ok')

    // 高度与成功加载的那张一致（布局不抖）
    const heights = await slotHeights(page)
    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(2)
    // 唯一允许的控制台错误就是那条故意构造的 404 图片，且只出现一次：
    // onError 里按 URL 判重，不会重复触发。
    const imageErrors = errors.filter((text) => text.includes('Failed to load resource'))
    expect(imageErrors).toHaveLength(1)
    expect(errors.length).toBe(1)
  })

  test('结果数 1 / 3 / 5 都用叠卡，不会退回栅格', async ({ page }) => {
    for (const count of [1, 3, 5]) {
      await installFixtures(page, {
        recommended: [product(1), product(2), product(3), product(4), product(5)],
        products: Array.from({ length: count }, (_, i) => product(i + 1)),
      })
      await login(page)
      await submitQuery(page, `会议桌 ${count}`)

      await expect(deckSlots(page)).toHaveCount(count)
      const flattened = await isFlattenedDeck(page)
      if (flattened) {
        // 窄屏：拍平成横向 scroll-snap 卡片带（避免卡片溢出屏幕），同样不是栅格
        await expect(page.locator('.hero-deck__track')).toHaveCSS('display', 'flex')
        // 卡片带自己横向滚动，但页面不能出现横向滚动条
        const pageOverflow = await page.evaluate(
          () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
        )
        expect(pageOverflow).toBeLessThanOrEqual(1)
      } else {
        // 桌面：卡位是绝对定位 + 旋转，绝不是栅格
        const transforms = await page.locator('.hero-deck__slot').evaluateAll((nodes) =>
          nodes.map((node) => getComputedStyle(node).transform),
        )
        expect(transforms.some((value) => value !== 'none' && value !== 'matrix(1, 0, 0, 1, 0, 0)')).toBeTruthy()
        // 卡片是层叠的：至少两张卡的盒子有重叠
        if (count >= 3) {
          const boxes = await page.locator('.hero-deck__slot').evaluateAll((nodes) =>
            nodes.map((node) => node.getBoundingClientRect()).map((box) => ({ left: box.left, right: box.right })),
          )
          const sorted = [...boxes].sort((a, b) => a.left - b.left)
          expect(sorted[1].left).toBeLessThan(sorted[0].right)
        }
      }
      await page.getByRole('button', { name: '清空结果' }).click()
      await expect(page.locator('.workspace')).toHaveCount(0)
    }
  })

  test('超过 5 条结果时同屏 5 张，滚轮在卡堆内循环轮换且页面不跟滚', async ({ page }) => {
    await installFixtures(page, {
      recommended: [product(1), product(2), product(3), product(4), product(5)],
      products: Array.from({ length: 12 }, (_, i) => product(i + 1)),
    })
    await login(page)
    await submitQuery(page, '会议桌')

    await expect(deckSlots(page)).toHaveCount(5)
    await expect(page.locator('.hero-deck__nav-count')).toHaveText('1-5 / 12')

    const firstWindow = await page.locator('.hero-deck__slot').evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('data-index')),
    )
    expect(firstWindow).toEqual(['0', '1', '2', '3', '4'])

    // 滚轮向下：翻到下一组
    await hoverDeck(page)
    const beforeScroll = await page.evaluate(() => window.scrollY)
    await wheelStep(page, 1)
    await expect(page.locator('.hero-deck__slot').first()).toHaveAttribute('data-index', '1')
    await expect(page.locator('.hero-deck__nav-count')).toHaveText('2-6 / 12')
    // 页面主体没有跟着滚
    expect(await page.evaluate(() => window.scrollY)).toBe(beforeScroll)
    // 连续循环：一路翻到底再翻一张，回到第一张
    await wheelStep(page, 1, 11)
    await expect(page.locator('.hero-deck__slot').first()).toHaveAttribute('data-index', '0')
    await expect(page.locator('.hero-deck__nav-count')).toHaveText('1-5 / 12')

    // 向上翻是反向的
    await wheelStep(page, -1)
    await expect(page.locator('.hero-deck__slot').first()).toHaveAttribute('data-index', '11')
    await expect(page.locator('.hero-deck__nav-count')).toHaveText('12-12 / 12')
  })

  test('鼠标移出卡堆后页面恢复滚动', async ({ page }) => {
    await installFixtures(page, {
      recommended: [product(1), product(2), product(3), product(4), product(5)],
      products: Array.from({ length: 12 }, (_, i) => product(i + 1)),
    })
    await login(page)
    await submitQuery(page, '会议桌')

    // 卡堆内滚：只轮换卡片，页面不动
    await hoverDeck(page)
    const atDeck = await settleScroll(page)
    await wheelStep(page, 1)
    await settleScroll(page)
    expect(await page.evaluate(() => window.scrollY)).toBe(atDeck)
    await expect(page.locator('.hero-deck__slot').first()).toHaveAttribute('data-index', '1')

    // 鼠标离开卡堆再滚：页面正常往下走
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }))
    await page.mouse.move(10, 10)
    const before = await settleScroll(page)
    await page.mouse.wheel(0, 240)
    await page.waitForTimeout(400)
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(before)
  })

  test('轮换时图片、标题、价格不错位', async ({ page }) => {
    await installFixtures(page, {
      recommended: [product(1)],
      products: Array.from({ length: 12 }, (_, i) => product(i + 1)),
    })
    await login(page)
    await submitQuery(page, '会议桌')

    const readCards = async () => {
      // 等翻页过渡结束再读，否则 deck-leave-active 的旧卡还在 DOM 里
      await expect(page.locator('.hero-deck__slot')).toHaveCount(5)
      await page.waitForTimeout(250)
      return page.locator('.hero-deck__slot .product-card').evaluateAll((nodes) =>
        nodes.map((node) => ({
          index: node.closest('.hero-deck__slot')?.getAttribute('data-index') ?? '',
          name: node.querySelector('h3')?.textContent ?? '',
          price: node.querySelector('.product-card__footer strong')?.textContent ?? '',
          src: node.querySelector('img')?.getAttribute('src') ?? '',
        })),
      )
    }

    const before = await readCards()
    await hoverDeck(page)
    await wheelStep(page, 1)
    const after = await readCards()

    expect(after).toHaveLength(5)
    for (const card of after) {
      const index = Number(card.index)
      // 标题、价格、图片地址都必须落在同一索引的产品上
      expect(card.name).toBe(`会议桌 ${index + 1}`)
      expect(card.price).toBe(`¥${(6511 + index).toLocaleString('zh-CN')}`)
      expect(card.src).toContain(`cover-${index + 1}`)
    }
    expect(after[0].index).not.toBe(before[0].index)
  })

  test('切换查询结果后整体重新开始，不残留上一批卡片', async ({ page }) => {
    await installFixtures(page, {
      recommended: [product(1), product(2), product(3), product(4), product(5)],
      products: Array.from({ length: 12 }, (_, i) => product(i + 1)),
    })
    await login(page)
    await submitQuery(page, '会议桌')
    await wheelStep(page, 1)
    await expect(page.locator('.hero-deck__slot').first()).toHaveAttribute('data-index', '1')

    await submitQuery(page, '办公椅')
    await expect(page.locator('.hero-deck__slot').first()).toHaveAttribute('data-index', '0')
    await expect(page.locator('.hero-deck__nav-count')).toHaveText('1-5 / 12')
  })

  test('查询结果 Markdown 被渲染成标题 / 表格 / 列表 / 引用 / 代码块', async ({ page }) => {
    const answer = [
      '## 会议桌产品一览',
      '',
      '当前系统中共有 **20 款会议桌**，均来自供应商 *圣奥*，覆盖 6 个产品系列。',
      '',
      '---',
      '',
      '### 1. 铭达系列（新中式）— 3 款 | 状态：预售（preorder）',
      '',
      '| 型号 | 规格(mm) | 价外 |',
      '| --- | --- | --- |',
      '| EMD76.240110 | 2400×1100×750 | ¥6,510 |',
      '| EMD77.360150 | 3600×1500×750 | ¥12,930 |',
      '',
      '- 双翻线盒、双接口布局',
      '- EMD78 台面采用天然木皮',
      '',
      '1. 先确认台面尺寸',
      '2. 再确认材质与颜色',
      '',
      '> EMD78 台面采用天然木皮。材质、颜色等字段待业务补充。',
      '',
      '```',
      'SELECT product_no, face_price FROM products;',
      '```',
      '',
      '详情见 [安装手册](https://example.com/manual)，型号码 `EMD76.240110`。',
    ].join('\n')

    await installFixtures(page, {
      recommended: [product(1), product(2), product(3), product(4), product(5)],
      products: [product(1)],
      answer,
    })
    await login(page)
    await submitQuery(page, '会议桌')

    const body = page.locator('.answer-body__markdown')
    await expect(body.locator('h2')).toHaveText('会议桌产品一览')
    await expect(body.locator('h3')).toContainText('铭达系列')
    await expect(body.locator('strong').first()).toHaveText('20 款会议桌')
    await expect(body.locator('em').first()).toHaveText('圣奥')
    await expect(body.locator('table.md-table')).toBeVisible()
    await expect(body.locator('table.md-table tbody tr')).toHaveCount(2)
    await expect(body.locator('ul.md-list li')).toHaveCount(2)
    await expect(body.locator('ol.md-list li')).toHaveCount(2)
    await expect(body.locator('blockquote.md-quote')).toContainText('EMD78 台面采用天然木皮')
    await expect(body.locator('hr.md-hr')).toHaveCount(1)
    await expect(body.locator('pre.md-pre code.md-code')).toContainText('SELECT product_no')
    await expect(body.locator('code.md-code-inline')).toHaveText('EMD76.240110')
    await expect(body.locator('a.md-link')).toHaveAttribute('href', 'https://example.com/manual')

    // 不允许把 Markdown 原文直接吐出来
    const text = (await body.innerText()).replace(/\s+/g, '')
    expect(text).not.toContain('##')
    expect(text).not.toContain('**')
    expect(text).not.toContain('|---')
    expect(text).not.toContain('```')
  })

  test('答案里的 HTML / 脚本不会注入，引用角标仍可点击', async ({ page }) => {
    const sourceId = 'chunk:11111111-1111-1111-1111-111111111111'
    const answer = [
      '回答如下。',
      '',
      '<img src=x onerror="window.__xss = true">',
      '<script>window.__xss = true</script>',
      '',
      `引用来源见 [${sourceId}]。`,
      '',
      '| 型号 | 价外 |',
      '| --- | --- |',
      '| EMD76 | ¥6,510 |',
    ].join('\n')

    await installFixtures(page, {
      recommended: [product(1)],
      products: [product(1)],
      answer,
      sources: [{ source_id: sourceId, source_type: 'document', title: '安装手册', quote: '步骤一' }],
    })
    await page.route('**/api/v1/knowledge/sources/**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 200,
          data: { source_id: sourceId, source_type: 'document', title: '安装手册', quote: '步骤一' },
        }),
      })
    })
    await login(page)
    await submitQuery(page, '会议桌')

    const body = page.locator('.answer-body__markdown')
    await expect(body.locator('table.md-table')).toBeVisible()
    await expect(body.locator('img')).toHaveCount(0)
    await expect(body.locator('script')).toHaveCount(0)
    expect(await page.evaluate(() => (window as unknown as { __xss?: boolean }).__xss)).toBeFalsy()

    const citation = body.locator('button.citation')
    await expect(citation).toHaveCount(1)
    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/api/v1/knowledge/sources/')),
      citation.click(),
    ])
    expect(response.ok()).toBeTruthy()
  })

  test('无结果状态展示明确空状态，不误显示为查询结果也不显示推荐位', async ({ page }) => {
    await installFixtures(page, {
      recommended: [product(1), product(2), product(3), product(4), product(5)],
      products: [],
      answer: '',
    })
    await login(page)
    await submitQuery(page, '不存在的型号 xyz')

    await expect(page.locator('.answer-body__placeholder')).toHaveText(
      '这次查询没有生成答案，可以换个更具体的说法再试一次。',
    )
    // 卡堆给出的是明确空状态，而不是把首屏推荐位又摆回来
    await expect(deckSlots(page)).toHaveCount(1)
    await expect(page.locator('.product-card--empty--noresult')).toHaveText(/本次查询没有返回产品/)
    await expect(page.locator('.hero-status')).toHaveText('本次查询没有返回产品')
    await expect(page.locator('.hero-deck .product-card')).toHaveCount(1)
  })

  test('查询失败时答案区给出错误提示', async ({ page }) => {
    await installFixtures(page, {
      recommended: [product(1), product(2), product(3), product(4), product(5)],
      products: [product(1)],
      answer: '',
    })
    await page.route('**/api/v1/knowledge/query', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'event: error\ndata: {"message":"模型服务暂时不可用"}\n\n',
      })
    })
    await login(page)
    await submitQuery(page, '会议桌')

    await expect(page.locator('.notice--error')).toHaveText('模型服务暂时不可用')
    await expect(page.locator('.product-card--empty--noresult')).toBeVisible()
  })

  test('桌面端与移动端都没有横向溢出，且没有控制台报错 / key 警告', async ({ page }) => {
    const consoleNoise: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error' || message.type() === 'warning') consoleNoise.push(message.text())
    })
    page.on('pageerror', (error) => consoleNoise.push(error.message))

    await installFixtures(page, {
      recommended: [product(1), product(2), product(3), product(4), product(5)],
      products: Array.from({ length: 12 }, (_, i) => product(i + 1)),
      answer: '## 标题\n\n| A | B |\n| --- | --- |\n| 1 | 2 |',
    })
    await login(page)
    await submitQuery(page, '会议桌')
    // 翻页会触发卡片 enter/leave，最容易暴露 key 冲突
    await wheelStep(page, 1)
    await wheelStep(page, -1)

    const overflow = async () =>
      page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
    expect(await overflow()).toBeLessThanOrEqual(1)

    await page.setViewportSize({ width: 390, height: 844 })
    await page.waitForTimeout(200)
    expect(await overflow()).toBeLessThanOrEqual(1)
    await expect(deckSlots(page)).toHaveCount(5)

    expect(consoleNoise.join('\n')).toBe('')
  })

  test('卡堆固定高度内不裁切卡片，窄桌面也不横向溢出', async ({ page }) => {
    await installFixtures(page, {
      recommended: [product(1), product(2), product(3), product(4), product(5)],
      products: Array.from({ length: 12 }, (_, i) => product(i + 1)),
    })
    await login(page)
    await submitQuery(page, '会议桌')

    // 1025px 是扇形还生效的最窄桌面宽度，这里必须同时满足：
    // 1) 卡片不出卡堆；2) 页面不出横向滚动条。
    await page.setViewportSize({ width: 1025, height: 800 })
    await page.waitForTimeout(300)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(1)

    const margins = await page.evaluate(() => {
      const deck = document.querySelector('.hero-deck') as HTMLElement
      const box = deck.getBoundingClientRect()
      return Array.from(deck.querySelectorAll('.hero-deck__slot')).map((slot) => {
        const rect = (slot as HTMLElement).getBoundingClientRect()
        return {
          top: rect.top - box.top,
          bottom: box.bottom - rect.bottom,
          left: rect.left - box.left,
          right: box.right - rect.right,
        }
      })
    })
    expect(margins).toHaveLength(5)
    for (const margin of margins) {
      expect(margin.top).toBeGreaterThanOrEqual(0)
      expect(margin.bottom).toBeGreaterThanOrEqual(0)
      expect(margin.left).toBeGreaterThanOrEqual(0)
      expect(margin.right).toBeGreaterThanOrEqual(0)
    }
  })
})
