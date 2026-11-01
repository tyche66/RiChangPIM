/**
 * 门户全局设置 store（FR-3）。
 *
 * 启动时匿名拉取 GET /api/v1/settings/public；失败回落现有硬编码文案，
 * 绝不白屏。业务展示参数（货币符号/小数位）公共接口不下发
 * （验收标准：public 不含业务配置），先以默认值兜底、字段预留，
 * 后续若开放再由 merge 自动接管。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getPublicSettings, type PublicSettings } from '@/api'

const FALLBACK: PublicSettings = {
  site_name: 'RiChangPIM',
  portal_title: 'RiChangPIM Portal',
  portal_subtitle:
    '内部只读 AI 工作台。产品、资料和质量记录统一走 Knowledge Gateway，答案都带引用来源。',
  footer_text: '由 RiChangPIM 提供',
  logo_url: null,
}

export const useSettingsStore = defineStore('portal-settings', () => {
  const siteName = ref(FALLBACK.site_name)
  const portalTitle = ref(FALLBACK.portal_title)
  const portalSubtitle = ref(FALLBACK.portal_subtitle)
  const footerText = ref(FALLBACK.footer_text)
  const logoUrl = ref<string | null>(FALLBACK.logo_url)
  // 业务展示参数：public 端点不含，默认值与后端 Schema 一致
  const currencySymbol = ref('¥')
  const amountDecimalPlaces = ref(2)
  /** true 表示至少成功拉取过一次公共设置 */
  const loaded = ref(false)
  const loading = ref(false)

  const brand = computed(() => ({
    site_name: siteName.value,
    portal_title: portalTitle.value,
    portal_subtitle: portalSubtitle.value,
    footer_text: footerText.value,
    logo_url: logoUrl.value,
  }))

  /** 只加载一次；失败静默回落默认文案，重复调用安全 */
  async function load() {
    if (loading.value || loaded.value) return
    loading.value = true
    try {
      const data = await getPublicSettings()
      siteName.value = data.site_name || FALLBACK.site_name
      portalTitle.value = data.portal_title || FALLBACK.portal_title
      portalSubtitle.value = data.portal_subtitle || FALLBACK.portal_subtitle
      footerText.value = data.footer_text || FALLBACK.footer_text
      logoUrl.value = data.logo_url || null
      // 防御性合并：后端若未来在 public 里补充业务展示字段则自动生效
      const extra = data as Partial<{ currency_symbol: string; amount_decimal_places: number }>
      if (typeof extra.currency_symbol === 'string' && extra.currency_symbol) {
        currencySymbol.value = extra.currency_symbol
      }
      if (typeof extra.amount_decimal_places === 'number' && extra.amount_decimal_places >= 0) {
        amountDecimalPlaces.value = extra.amount_decimal_places
      }
      loaded.value = true
      // 浏览器标题跟随 site_name（需求 §3.2）；失败时保留 index.html 静态标题
      document.title = siteName.value
    } catch {
      // 接口失败：保留回落文案与打包 Logo，不阻塞挂载（FR-3 验收）
    } finally {
      loading.value = false
    }
  }

  return {
    siteName,
    portalTitle,
    portalSubtitle,
    footerText,
    logoUrl,
    currencySymbol,
    amountDecimalPlaces,
    loaded,
    loading,
    brand,
    load,
  }
})
