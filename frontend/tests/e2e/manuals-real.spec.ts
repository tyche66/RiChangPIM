import { test, expect } from '@playwright/test'

const productId = process.env.E2E_PRODUCT_ID || ''
const pdfPath = process.env.E2E_PDF_PATH || ''

test.describe('Real manual knowledge-base flow', () => {
  test.beforeEach(async ({ page }) => {
    expect(productId, 'E2E_PRODUCT_ID must reference a real product').not.toBe('')
    expect(pdfPath, 'E2E_PDF_PATH must reference a real PDF fixture').not.toBe('')
    await page.goto('/login')
    await page.getByPlaceholder('用户名').fill('admin')
    await page.getByPlaceholder('密码').fill('admin123')
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page).toHaveURL(/\/products/)
  })

  test('uploads, parses, indexes and answers with traceable sources', async ({ page }) => {
    await page.goto('/manuals')
    await expect(page.getByRole('heading', { name: '产品知识库' })).toBeVisible()

    await page.getByPlaceholder('请输入已存在的 product_id').fill(productId)
    await page.locator('input[type="file"]').setInputFiles(pdfPath)
    await page.getByRole('button', { name: '上传并创建' }).click()
    await expect(page.getByText('说明书已创建，请触发解析')).toBeVisible()

    const newestRow = page.locator('.el-table__row').last()
    await newestRow.getByRole('button', { name: '解析' }).click()
    await expect(page.getByText('解析完成')).toBeVisible()
    await expect(newestRow.getByText('parsed')).toBeVisible()

    await newestRow.getByRole('button', { name: '索引' }).click()
    await expect(page.getByText('索引完成')).toBeVisible()
    await expect(newestRow.getByText('indexed')).toBeVisible()

    await page.getByPlaceholder('留空则搜索全部已索引说明书').fill(productId)
    await page.getByPlaceholder('例如：这款产品支持哪些用电标准？').fill('What material is used?')
    await page.getByRole('button', { name: '提问' }).click()
    await expect(page.getByRole('heading', { name: '回答' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Sources' })).toBeVisible()
    await expect(page.getByText(/score 1/).first()).toBeVisible()
  })
})
