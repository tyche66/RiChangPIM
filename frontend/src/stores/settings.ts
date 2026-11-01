/**
 * 全局设置 store（FR-3）。
 *
 * 后端 GET /settings 仅 admin 可读；非管理员/接口失败时整体回落默认值
 * （与后端 Schema 默认一致），保证分享弹窗预填、税率默认、金额格式化
 * 在任何情况下都有值可用，绝不抛错阻塞业务页。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { settingsApi, type SystemSettingsData } from '@/api/settings'

export const DEFAULT_SETTINGS: SystemSettingsData = {
  brand: {
    site_name: 'RiChangPIM',
    portal_title: 'RiChangPIM Portal',
    portal_subtitle:
      '内部只读 AI 工作台。产品、资料和质量记录统一走 Knowledge Gateway，答案都带引用来源。',
    footer_text: '由 RiChangPIM 提供',
    logo_attachment_id: null,
  },
  share: {
    share_default_expire_hours: 24,
    share_default_max_access_count: 100,
    share_default_require_password: false,
  },
  business: {
    quotation_default_tax_rate: 0.13,
    amount_decimal_places: 2,
    currency_symbol: '¥',
  },
  logo_url: null,
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<SystemSettingsData>(structuredClone(DEFAULT_SETTINGS))
  /** true 表示至少成功拉取过一次真实设置 */
  const loaded = ref(false)
  const loading = ref(false)

  const brand = computed(() => settings.value.brand)
  const share = computed(() => settings.value.share)
  const business = computed(() => settings.value.business)

  function applyFallback() {
    settings.value = structuredClone(DEFAULT_SETTINGS)
    loaded.value = false
  }

  /** 拉取失败回落默认值；重复调用安全（进行中或已成功时直接返回） */
  async function load(force = false) {
    if (loading.value || (loaded.value && !force)) return
    loading.value = true
    try {
      const res = await settingsApi.get()
      if (res.data) {
        settings.value = {
          brand: { ...DEFAULT_SETTINGS.brand, ...res.data.brand },
          share: { ...DEFAULT_SETTINGS.share, ...res.data.share },
          business: { ...DEFAULT_SETTINGS.business, ...res.data.business },
          logo_url: res.data.logo_url ?? null,
        }
        loaded.value = true
      }
    } catch {
      // 非管理员 403 / 网络失败：静默回落默认值
      applyFallback()
    } finally {
      loading.value = false
    }
  }

  /** 保存成功后用响应里的最新设置就地刷新 */
  function applyFromResponse(data: SystemSettingsData) {
    settings.value = {
      brand: { ...DEFAULT_SETTINGS.brand, ...data.brand },
      share: { ...DEFAULT_SETTINGS.share, ...data.share },
      business: { ...DEFAULT_SETTINGS.business, ...data.business },
      logo_url: data.logo_url ?? null,
    }
    loaded.value = true
  }

  return {
    settings,
    brand,
    share,
    business,
    loaded,
    loading,
    load,
    applyFallback,
    applyFromResponse,
  }
})
