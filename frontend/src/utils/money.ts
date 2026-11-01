/**
 * 金额展示工具（FR-3）。
 *
 * 小数位与货币符号统一取自全局设置（stores/settings.ts），
 * 禁止再写死 `¥` / `toFixed(2)`；设置未加载时回落默认值（¥ / 2 位），
 * 与后端 Schema 默认一致。
 */
import { useSettingsStore } from '@/stores/settings'

export function formatMoney(
  value: number | string | null | undefined,
  fallback = '-',
): string {
  if (value === null || value === undefined || value === '') return fallback
  const num = typeof value === 'string' ? Number.parseFloat(value) : value
  if (!Number.isFinite(num)) return fallback
  const { amount_decimal_places: decimals, currency_symbol: symbol } =
    useSettingsStore().business
  return `${symbol}${num.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`
}
