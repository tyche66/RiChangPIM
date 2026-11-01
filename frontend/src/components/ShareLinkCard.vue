<template>
  <section class="share-link-card">
    <header class="share-link-card__header">
      <div>
        <h3>分享链接</h3>
        <p class="share-link-card__hint">
          已生成的链接可在这里再次复制、预览或下载二维码，不必重新创建。
        </p>
      </div>
      <el-tag
        v-if="share?.share_url"
        :type="statusTone"
        class="capsule-tag"
      >
        {{ statusLabel }}
      </el-tag>
    </header>

    <div v-if="loading" class="share-link-card__loading">
      <el-skeleton :rows="3" animated />
    </div>

    <template v-else-if="share?.share_url">
      <el-input
        :model-value="absoluteUrl"
        readonly
        class="share-link-card__url"
      >
        <template #append>
          <el-button @click="handleCopy">复制链接</el-button>
        </template>
      </el-input>

      <div class="share-link-card__body">
        <div class="share-link-card__qr">
          <canvas ref="qrCanvas" aria-label="分享链接二维码" />
          <span>扫码打开分享页</span>
        </div>
        <dl class="share-link-card__facts">
          <div>
            <dt>有效期至</dt>
            <dd>{{ share.expire_time ? formatDate(share.expire_time) : '长期有效' }}</dd>
          </div>
          <div>
            <dt>访问次数</dt>
            <dd>
              {{ share.current_access_count }}
              <template v-if="share.max_access_count"> / {{ share.max_access_count }}</template>
            </dd>
          </div>
          <div>
            <dt>访问密码</dt>
            <dd>{{ share.password_protected ? '已设置' : '未设置' }}</dd>
          </div>
        </dl>
      </div>

      <div class="share-link-card__actions">
        <el-button type="primary" @click="handlePreview">在新窗口预览</el-button>
        <el-button @click="handleDownload">下载二维码</el-button>
      </div>
    </template>

    <div v-else class="share-link-card__empty">
      该方案还没有可复用的分享链接。可在方案列表点击「分享」创建。
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import QRCode from 'qrcode'
import type { ShareLinkInfo } from '@/types/sales'

const props = withDefaults(
  defineProps<{
    share: ShareLinkInfo | null
    loading?: boolean
  }>(),
  { loading: false },
)

const qrCanvas = ref<HTMLCanvasElement | null>(null)

const absoluteUrl = computed(() => {
  const path = props.share?.share_url
  if (!path) return ''
  if (path.startsWith('http')) return path
  const publicUrl = import.meta.env.VITE_PUBLIC_FRONTEND_URL
  if (publicUrl) {
    return `${publicUrl.endsWith('/') ? publicUrl : `${publicUrl}/`}${path.replace(/^\//, '')}`
  }
  return `${window.location.origin}${path}`
})

const expired = computed(() => {
  const value = props.share?.expire_time
  return Boolean(value && new Date(value).getTime() <= Date.now())
})

const statusLabel = computed(() => {
  if (props.share?.status === 'disabled') return '已失效'
  if (expired.value) return '已过期'
  return '有效'
})

const statusTone = computed<'success' | 'warning' | 'info'>(() => {
  if (props.share?.status === 'disabled') return 'info'
  if (expired.value) return 'warning'
  return 'success'
})

function formatDate(value: string): string {
  return new Date(value).toLocaleString('zh-CN')
}

async function drawQr() {
  await nextTick()
  const canvas = qrCanvas.value
  if (!canvas || !absoluteUrl.value) return
  try {
    await QRCode.toCanvas(canvas, absoluteUrl.value, {
      width: 160,
      margin: 2,
      color: { dark: '#1e325a', light: '#ffffff' },
    })
  } catch {
    ElMessage.error('二维码生成失败')
  }
}

async function handleCopy() {
  try {
    await navigator.clipboard.writeText(absoluteUrl.value)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择链接复制')
  }
}

function handlePreview() {
  if (absoluteUrl.value) window.open(absoluteUrl.value, '_blank', 'noopener,noreferrer')
}

function handleDownload() {
  const canvas = qrCanvas.value
  if (!canvas) return
  try {
    const link = document.createElement('a')
    link.href = canvas.toDataURL('image/png')
    link.download = `share-qr-${props.share?.share_id || Date.now()}.png`
    link.click()
    ElMessage.success('二维码已下载')
  } catch {
    ElMessage.error('下载失败')
  }
}

watch(
  () => props.share,
  async () => {
    await drawQr()
  },
  { immediate: true },
)
</script>

<style scoped>
.share-link-card {
  margin-top: 18px;
  padding: 20px 22px;
  border: 1px solid var(--pim-card-border);
  border-radius: var(--pim-radius-sm);
  background: var(--pim-surface);
}

.share-link-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.share-link-card__header h3 {
  margin: 0;
  color: var(--pim-text-strong);
  font-size: 15px;
  font-weight: 700;
}

.share-link-card__hint {
  margin: 5px 0 0;
  color: var(--pim-text-secondary);
  font-size: 12.5px;
  line-height: 1.6;
}

.share-link-card__loading {
  margin-top: 16px;
}

.share-link-card__url {
  margin-top: 16px;
}

.share-link-card__url :deep(.el-input__wrapper) {
  border-radius: 12px;
}

.share-link-card__body {
  display: flex;
  align-items: center;
  gap: 28px;
  margin-top: 16px;
}

.share-link-card__qr {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  flex: none;
  color: var(--pim-text-faint);
  font-size: 11.5px;
}

.share-link-card__qr canvas {
  width: 160px;
  height: 160px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(var(--pim-brand), 0.1);
}

.share-link-card__facts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px 22px;
  margin: 0;
  flex: 1;
}

.share-link-card__facts dt {
  margin: 0;
  color: var(--pim-text-secondary);
  font-size: 12px;
}

.share-link-card__facts dd {
  margin: 4px 0 0;
  color: var(--pim-text-primary);
  font-size: 13px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.share-link-card__actions {
  display: flex;
  gap: 8px;
  margin-top: 18px;
  flex-wrap: wrap;
}

.share-link-card__empty {
  margin-top: 16px;
  padding: 18px;
  border-radius: 10px;
  background: var(--pim-page);
  color: var(--pim-text-secondary);
  font-size: 13px;
  text-align: center;
}

@media (max-width: 768px) {
  .share-link-card {
    padding: 16px;
  }

  .share-link-card__body {
    flex-direction: column;
    align-items: stretch;
    gap: 18px;
  }

  .share-link-card__facts {
    grid-template-columns: 1fr;
  }
}
</style>
