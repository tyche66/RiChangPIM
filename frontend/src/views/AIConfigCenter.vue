<template>
  <section class="ai-config-page">
    <header class="ai-config-hero">
      <div>
        <span class="eyebrow">AI PROVIDER SETTINGS</span>
        <h2>AI 配置中心</h2>
        <p>
          统一管理产品选品检索与内容工坊使用的第三方 AI 服务。留空的字段会继续沿用服务端环境变量，
          保存后约 15 秒内在全部 worker 生效，无需重启。
        </p>
      </div>
      <el-button
        type="primary"
        :loading="loading"
        @click="loadConfigs"
      >
        刷新
      </el-button>
    </header>

    <el-alert
      v-if="error"
      class="ai-config-alert"
      type="error"
      :closable="false"
      :title="error"
    />

    <div
      v-loading="loading"
      class="ai-config-grid"
    >
      <el-card
        v-for="item in items"
        :key="item.scope"
        class="ai-config-card"
        shadow="never"
      >
        <template #header>
          <div class="ai-config-card__header">
            <div>
              <strong>{{ item.label }}</strong>
              <small>{{ scopeCode(item.scope) }}</small>
            </div>
            <el-tag
              :type="item.source === 'db' ? 'success' : 'info'"
              effect="light"
            >
              {{ item.source === 'db' ? '数据库配置生效' : '环境变量生效' }}
            </el-tag>
          </div>
        </template>

        <el-form
          label-position="top"
          class="ai-config-form"
        >
          <el-form-item label="API 地址">
            <el-input
              v-model="forms[item.scope].api_url"
              placeholder="例如 https://api.example.com/v1"
            />
          </el-form-item>

          <el-form-item :label="`API Key（当前：${item.api_key_masked || '未配置'}）`">
            <el-input
              v-model="forms[item.scope].api_key"
              type="password"
              show-password
              placeholder="留空表示不修改"
            />
          </el-form-item>

          <el-form-item label="对话模型 ID">
            <el-input
              v-model="forms[item.scope].chat_model"
              placeholder="例如 step-5-preview"
            />
          </el-form-item>

          <template v-if="item.scope === 'content'">
            <el-form-item label="可选模型列表（内容工坊生成表单的模型下拉）">
              <el-input
                v-model="forms[item.scope].chat_models_text"
                placeholder="多个模型用英文逗号分隔"
              />
              <div class="ai-config-hint">
                请求的模型必须落在该列表内，否则后端直接拒绝。
              </div>
            </el-form-item>
          </template>

          <template v-if="item.scope === 'knowledge'">
            <el-form-item label="嵌入模型 ID">
              <el-input
                v-model="forms[item.scope].embedding_model"
                placeholder="例如 nvidia/nemotron-3-embed-1b:free"
              />
            </el-form-item>
            <el-form-item label="嵌入服务地址（留空则与 API 地址相同）">
              <el-input
                v-model="forms[item.scope].embedding_api_url"
              />
            </el-form-item>
            <el-form-item :label="`嵌入服务 Key（当前：${item.embedding_api_key_masked || '未配置'}）`">
              <el-input
                v-model="forms[item.scope].embedding_api_key"
                type="password"
                show-password
                placeholder="留空表示不修改"
              />
            </el-form-item>
          </template>

          <el-form-item label="超时（秒）">
            <el-input
              v-model.number="forms[item.scope].timeout_seconds"
              type="number"
              :min="1"
              :max="3600"
              placeholder="留空表示使用默认值"
            />
          </el-form-item>

          <el-form-item label="启用数据库配置">
            <el-switch v-model="forms[item.scope].enabled" />
            <div class="ai-config-hint">
              关闭后该域立即回落到环境变量，数据库中的值保留不丢失。
            </div>
          </el-form-item>
        </el-form>

        <div class="ai-config-actions">
          <el-button
            :loading="testing === item.scope"
            @click="handleTest(item.scope)"
          >
            测试连接
          </el-button>
          <el-button
            type="primary"
            :loading="saving === item.scope"
            @click="handleSave(item.scope)"
          >
            保存
          </el-button>
        </div>

        <p
          v-if="activeTestResult(item.scope)"
          :class="[
            'ai-config-test',
            activeTestResult(item.scope)?.ok ? 'is-ok' : 'is-fail',
          ]"
        >
          {{ activeTestResult(item.scope)?.detail }}
          <span v-if="activeTestResult(item.scope)?.latency_ms != null">
            （{{ activeTestResult(item.scope)?.latency_ms }} ms）
          </span>
        </p>
      </el-card>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchAiConfig,
  testAiConfig,
  updateAiConfig,
  type AiConfigItem,
  type AiConfigScope,
  type AiConfigTestResult,
} from '@/api/aiConfig'

const items = ref<AiConfigItem[]>([])
const loading = ref(false)
const saving = ref<AiConfigScope | ''>('')
const testing = ref<AiConfigScope | ''>('')
const error = ref('')
const testResults = reactive<Partial<Record<AiConfigScope, AiConfigTestResult>>>({})

interface FormState {
  api_url: string
  api_key: string
  chat_model: string
  chat_models_text: string
  embedding_model: string
  embedding_api_url: string
  embedding_api_key: string
  timeout_seconds: number | null
  enabled: boolean
}

const emptyForm = (): FormState => ({
  api_url: '',
  api_key: '',
  chat_model: '',
  chat_models_text: '',
  embedding_model: '',
  embedding_api_url: '',
  embedding_api_key: '',
  timeout_seconds: null,
  enabled: true,
})

const forms = reactive<Record<AiConfigScope, FormState>>({
  knowledge: emptyForm(),
  content: emptyForm(),
})

// 卡片级派生值：模板里不再重复索引 reactive，避免 TS 收窄与重复求值。
function activeTestResult(scope: AiConfigScope): AiConfigTestResult | undefined {
  return testResults[scope]
}

function scopeCode(scope: AiConfigScope): string {
  return scope === 'content' ? 'scope: content' : 'scope: knowledge'
}

function fillForm(item: AiConfigItem) {
  const form = forms[item.scope]
  form.api_url = item.api_url ?? ''
  form.api_key = ''
  form.chat_model = item.chat_model ?? ''
  form.chat_models_text = (item.chat_models ?? []).join(',')
  form.embedding_model = item.embedding_model ?? ''
  form.embedding_api_url = item.embedding_api_url ?? ''
  form.embedding_api_key = ''
  form.timeout_seconds = item.timeout_seconds
  form.enabled = item.enabled
}

async function loadConfigs() {
  loading.value = true
  error.value = ''
  try {
    items.value = await fetchAiConfig()
    items.value.forEach(fillForm)
  } catch {
    error.value = '读取 AI 配置失败，请确认当前账号为管理员后重试'
  } finally {
    loading.value = false
  }
}

async function handleSave(scope: AiConfigScope) {
  const form = forms[scope]
  saving.value = scope
  try {
    const saved = await updateAiConfig(scope, {
      api_url: form.api_url.trim() || null,
      api_key: form.api_key.trim() || null,
      chat_model: form.chat_model.trim() || null,
      chat_models:
        scope === 'content'
          ? form.chat_models_text
              .split(',')
              .map((m) => m.trim())
              .filter(Boolean)
          : null,
      embedding_model: scope === 'knowledge' ? form.embedding_model.trim() || null : null,
      embedding_api_url:
        scope === 'knowledge' ? form.embedding_api_url.trim() || null : null,
      embedding_api_key:
        scope === 'knowledge' ? form.embedding_api_key.trim() || null : null,
      timeout_seconds: form.timeout_seconds && form.timeout_seconds > 0 ? form.timeout_seconds : null,
      enabled: form.enabled,
    })
    const index = items.value.findIndex((i) => i.scope === scope)
    if (index >= 0) items.value[index] = saved
    fillForm(saved)
    ElMessage.success('已保存，新配置约 15 秒内生效')
  } catch {
    ElMessage.error('保存失败，请检查填写内容后重试')
  } finally {
    saving.value = ''
  }
}

async function handleTest(scope: AiConfigScope) {
  testing.value = scope
  try {
    const result = await testAiConfig(scope)
    testResults[scope] = result
    if (result.ok) {
      ElMessage.success('连接成功')
    } else {
      ElMessage.warning(result.detail || '连接失败')
    }
  } catch {
    ElMessage.error('测试请求失败')
  } finally {
    testing.value = ''
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.ai-config-page {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.ai-config-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.ai-config-hero h2 {
  margin: 4px 0 6px;
  font-size: 20px;
}

.ai-config-hero p {
  margin: 0;
  max-width: 620px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.ai-config-alert {
  margin: 0;
}

.ai-config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 16px;
  align-items: start;
}

.ai-config-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.ai-config-card__header small {
  display: block;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin-top: 2px;
}

.ai-config-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.ai-config-actions {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

.ai-config-test {
  margin: 10px 0 0;
  font-size: 12px;
}

.ai-config-test.is-ok {
  color: var(--el-color-success);
}

.ai-config-test.is-fail {
  color: var(--el-color-danger);
}
</style>
