<template>
  <section class="system-settings-page">
    <header class="settings-hero">
      <div>
        <span class="eyebrow">SYSTEM SETTINGS</span>
        <h2>全局设置</h2>
        <p>
          统一维护品牌文案、分享缺省值与业务默认参数。保存后立即在后台生效，
          门户最迟 60 秒内跟随刷新。
        </p>
      </div>
      <el-button
        :loading="loading"
        @click="loadSettings(true)"
      >
        刷新
      </el-button>
    </header>

    <el-alert
      v-if="error"
      class="settings-alert"
      type="error"
      :closable="false"
      :title="error"
    />

    <div
      v-loading="loading"
      class="settings-grid"
    >
      <el-card
        class="settings-card"
        shadow="never"
      >
        <template #header>
          <div class="settings-card__header">
            <div>
              <strong>品牌</strong>
              <small>门户标题、页脚与 Logo（生效于后台与门户）</small>
            </div>
          </div>
        </template>

        <el-form
          label-position="top"
          class="settings-form"
        >
          <el-form-item label="系统名称">
            <el-input
              v-model="form.site_name"
              maxlength="64"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="门户主标题">
            <el-input
              v-model="form.portal_title"
              maxlength="128"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="门户副标题">
            <el-input
              v-model="form.portal_subtitle"
              type="textarea"
              :rows="2"
              maxlength="500"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="页脚文案">
            <el-input
              v-model="form.footer_text"
              maxlength="128"
              show-word-limit
            />
          </el-form-item>
          <el-form-item label="Logo">
            <div class="logo-row">
              <div class="logo-preview">
                <img
                  v-if="logoPreviewUrl"
                  :src="logoPreviewUrl"
                  alt="Logo 预览"
                />
                <span
                  v-else
                  class="logo-preview__empty"
                >
                  未配置
                </span>
              </div>
              <div class="logo-actions">
                <el-button
                  :disabled="!canEdit"
                  @click="logoPickerVisible = true"
                >
                  从媒体库选择
                </el-button>
                <el-button
                  :disabled="!canEdit || !form.logo_attachment_id"
                  @click="form.logo_attachment_id = null"
                >
                  清除
                </el-button>
              </div>
            </div>
            <div class="settings-hint">
              仅支持 JPG/PNG/WebP，单张不超过 2MB；更新后 URL 自动换版本，浏览器立即拉新图。
            </div>
          </el-form-item>
        </el-form>
      </el-card>

      <el-card
        class="settings-card"
        shadow="never"
      >
        <template #header>
          <div class="settings-card__header">
            <div>
              <strong>分享缺省值</strong>
              <small>方案/报价分享弹窗的预填值与后端缺省值</small>
            </div>
          </div>
        </template>

        <el-form
          label-position="top"
          class="settings-form"
        >
          <el-form-item label="默认有效期（小时，1–720）">
            <el-input-number
              v-model="form.share_default_expire_hours"
              :min="1"
              :max="720"
              :step="1"
              class="full-width"
            />
          </el-form-item>
          <el-form-item label="默认最大访问次数（1–10000）">
            <el-input-number
              v-model="form.share_default_max_access_count"
              :min="1"
              :max="10000"
              :step="1"
              class="full-width"
            />
            <div class="settings-hint">
              业务输入框上限为 1000，此处为后端校验的设置页范围。
            </div>
          </el-form-item>
          <el-form-item label="分享弹窗默认要求访问密码">
            <el-switch v-model="form.share_default_require_password" />
          </el-form-item>
        </el-form>
      </el-card>

      <el-card
        class="settings-card"
        shadow="never"
      >
        <template #header>
          <div class="settings-card__header">
            <div>
              <strong>业务</strong>
              <small>报价默认税率与金额展示格式</small>
            </div>
          </div>
        </template>

        <el-form
          label-position="top"
          class="settings-form"
        >
          <el-form-item label="报价单默认税率">
            <el-input-number
              v-model="taxRatePercent"
              :min="0"
              :max="100"
              :step="1"
              :precision="0"
              class="full-width"
            />
            <div class="settings-hint">
              以百分比填写（{{ taxRatePercent }}% = {{ form.quotation_default_tax_rate.toFixed(2) }}）。
            </div>
          </el-form-item>
          <el-form-item label="金额小数位（0–4）">
            <el-input-number
              v-model="form.amount_decimal_places"
              :min="0"
              :max="4"
              :step="1"
              class="full-width"
            />
          </el-form-item>
          <el-form-item label="货币符号">
            <el-input
              v-model="form.currency_symbol"
              maxlength="8"
              show-word-limit
            />
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <div class="settings-footer">
      <el-button
        type="primary"
        :loading="saving"
        :disabled="!canEdit"
        @click="handleSave"
      >
        保存设置
      </el-button>
    </div>

    <MediaPicker
      v-model="logoPickerVisible"
      type-filter="image"
      @select="onLogoSelected"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import MediaPicker from '@/components/MediaPicker.vue'
import type { MediaItem } from '@/api/media'
import { settingsApi, type SystemSettingsData } from '@/api/settings'
import { useAuthStore } from '@/stores/auth'
import { useSettingsStore } from '@/stores/settings'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()
const settingsStore = useSettingsStore()

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const logoPickerVisible = ref(false)
/** 媒体库刚选中、尚未保存时的本地预览地址 */
const pendingLogoUrl = ref('')

const form = reactive({
  site_name: '',
  portal_title: '',
  portal_subtitle: '',
  footer_text: '',
  logo_attachment_id: null as string | null,
  share_default_expire_hours: 24,
  share_default_max_access_count: 100,
  share_default_require_password: false,
  quotation_default_tax_rate: 0.13,
  amount_decimal_places: 2,
  currency_symbol: '¥',
})

const canEdit = computed(
  () =>
    authStore.userRoleCode === 'admin' &&
    hasPermission(authStore.permissions, 'setting:edit'),
)

const taxRatePercent = computed({
  get: () => Math.round(form.quotation_default_tax_rate * 100),
  set: (value: number | undefined) => {
    form.quotation_default_tax_rate = Number(((value ?? 0) / 100).toFixed(4))
  },
})

const logoPreviewUrl = computed(() => {
  if (pendingLogoUrl.value && form.logo_attachment_id) return pendingLogoUrl.value
  return settingsStore.settings.logo_url
})

function fillForm(data: SystemSettingsData) {
  form.site_name = data.brand.site_name
  form.portal_title = data.brand.portal_title
  form.portal_subtitle = data.brand.portal_subtitle
  form.footer_text = data.brand.footer_text
  form.logo_attachment_id = data.brand.logo_attachment_id
  form.share_default_expire_hours = data.share.share_default_expire_hours
  form.share_default_max_access_count = data.share.share_default_max_access_count
  form.share_default_require_password = data.share.share_default_require_password
  form.quotation_default_tax_rate = data.business.quotation_default_tax_rate
  form.amount_decimal_places = data.business.amount_decimal_places
  form.currency_symbol = data.business.currency_symbol
}

async function fetchSettings() {
  const res = await settingsApi.get()
  if (!res.data) throw new Error('empty settings payload')
  return res.data
}

async function loadSettings(force = false) {
  loading.value = true
  error.value = ''
  try {
    const data = await fetchSettings()
    fillForm(data)
    settingsStore.applyFromResponse(data)
  } catch {
    error.value = '读取全局设置失败，请确认当前账号为管理员后重试'
    if (force) await settingsStore.load(true)
  } finally {
    loading.value = false
  }
}

function onLogoSelected(item: MediaItem | MediaItem[]) {
  const media = Array.isArray(item) ? item[0] : item
  if (!media) return
  form.logo_attachment_id = media.id
  pendingLogoUrl.value = media.url
}

async function handleSave() {
  if (!form.site_name.trim() || !form.portal_title.trim()) {
    ElMessage.warning('系统名称与门户主标题不能为空')
    return
  }
  saving.value = true
  try {
    const res = await settingsApi.update({
      brand: {
        site_name: form.site_name.trim(),
        portal_title: form.portal_title.trim(),
        portal_subtitle: form.portal_subtitle,
        footer_text: form.footer_text,
        logo_attachment_id: form.logo_attachment_id,
      },
      share: {
        share_default_expire_hours: form.share_default_expire_hours,
        share_default_max_access_count: form.share_default_max_access_count,
        share_default_require_password: form.share_default_require_password,
      },
      business: {
        quotation_default_tax_rate: form.quotation_default_tax_rate,
        amount_decimal_places: form.amount_decimal_places,
        currency_symbol: form.currency_symbol.trim() || '¥',
      },
    })
    if (res.data) {
      fillForm(res.data)
      settingsStore.applyFromResponse(res.data)
    }
    pendingLogoUrl.value = ''
    ElMessage.success('已保存，后台立即生效，门户最迟 60 秒内跟随')
  } catch {
    ElMessage.error('保存失败，请检查填写内容后重试')
  } finally {
    saving.value = false
  }
}

onMounted(() => loadSettings())
</script>

<style scoped>
.system-settings-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.settings-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.settings-hero h2 {
  margin: 4px 0 6px;
  font-size: 20px;
}

.settings-hero p {
  margin: 0;
  max-width: 620px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.settings-alert {
  margin: 0;
}

.settings-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
  gap: 16px;
  align-items: start;
}

.settings-card__header small {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 2px;
}

.settings-form .full-width {
  width: 100%;
}

.settings-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.logo-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.logo-preview {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 48px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: var(--el-fill-color-light);
  overflow: hidden;
}

.logo-preview img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}

.logo-preview__empty {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.logo-actions {
  display: flex;
  gap: 8px;
}

.settings-footer {
  display: flex;
  justify-content: flex-end;
}
</style>
