/**
 * 比较结果的导出：Markdown 在浏览器里拼，PDF 由后端用同一份产品数据渲染。
 *
 * 为什么 Markdown 放前端：数据本来就在页面上，不产生新请求，也不用担心
 * 「导出的内容」和「屏幕上的内容」不一致；PDF 走后端是因为门户不引入
 * 排版库，Gotenberg 已经承担了报价单那一套 HTML→PDF。
 */
import { COMPARE_FIELDS, MISSING_TEXT, cellText, formatPrice, formatStock } from './format'

type ProductRow = Record<string, unknown>

function oneLine(value: unknown): string {
  return cellText(value).replace(/\r?\n/g, ' ').replace(/\|/g, '\\|')
}

const EXTRA_FIELDS: Array<{ key: string; label: string; format?: (value: unknown) => string }> = [
  { key: 'face_price', label: '价格', format: formatPrice },
  { key: 'stock_status', label: '库存状态', format: formatStock },
]

/** 把比较结果拼成 Markdown：一张对照表 + 每个产品的明细段落。 */
export function buildCompareMarkdown(products: ProductRow[]): string {
  const stamp = new Date().toLocaleString('zh-CN', { hour12: false })
  const lines: string[] = ['# 产品比较表', '']
  lines.push(`> 由 RiChangPIM 导出于 ${stamp} · 共 ${products.length} 个产品`, '')

  const rows: Array<{ label: string; values: string[] }> = [
    { label: '产品编号', values: products.map((p) => oneLine(p.product_no)) },
    ...COMPARE_FIELDS.map((field) => ({
      label: field.label,
      values: products.map((p) => oneLine(p[field.key])),
    })),
    ...EXTRA_FIELDS.map((field) => ({
      label: field.label,
      values: products.map((p) => oneLine(field.format ? field.format(p[field.key]) : p[field.key])),
    })),
  ].filter((row) => row.values.some((value) => value !== MISSING_TEXT))

  const header = ['属性', ...products.map((p, index) => oneLine(p.product_name) || `产品 ${index + 1}`)]
  lines.push(`| ${header.join(' | ')} |`)
  lines.push(`| ${header.map(() => '---').join(' | ')} |`)
  for (const row of rows) {
    lines.push(`| ${[row.label, ...row.values].join(' | ')} |`)
  }
  lines.push('')

  products.forEach((product, index) => {
    lines.push(`## ${cellText(product.product_name) || `产品 ${index + 1}`}`, '')
    const pairs: Array<[string, string]> = [['产品编号', oneLine(product.product_no)]]
    for (const field of COMPARE_FIELDS) {
      pairs.push([field.label, oneLine(product[field.key])])
    }
    for (const field of EXTRA_FIELDS) {
      pairs.push([
        field.label,
        oneLine(field.format ? field.format(product[field.key]) : product[field.key]),
      ])
    }
    for (const [label, value] of pairs) {
      lines.push(`- **${label}**：${value}`)
    }
    lines.push('')
  })

  return lines.join('\n')
}

export function downloadTextFile(filename: string, text: string, mime = 'text/markdown;charset=utf-8') {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
