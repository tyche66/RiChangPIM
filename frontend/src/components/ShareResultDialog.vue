<template>
  <el-dialog
    v-model="dialogVisible"
    title="分享链接已生成"
    class="glass-dialog share-result-dialog"
    append-to-body
    lock-scroll
    :close-on-click-modal="false"
  >
    <el-alert
      type="success"
      :closable="false"
      class="share-alert"
    >
      请将以下链接发送给客户
    </el-alert>

    <el-input
      :model-value="absoluteShareUrl"
      readonly
      class="capsule-input share-url-input"
    >
      <template #append>
        <el-button
          class="capsule-btn capsule-btn-primary"
          @click="handleCopy"
        >
          复制
        </el-button>
      </template>
    </el-input>

    <div class="qr-section">
      <canvas ref="qrCanvas" class="qr-canvas" />
    </div>

    <div class="share-actions">
      <el-button
        type="primary"
        class="capsule-btn capsule-btn-primary"
        @click="handlePreview"
      >
        在新窗口预览
      </el-button>
      <el-button
        class="capsule-btn"
        @click="handleDownload"
      >
        下载二维码
      </el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import QRCode from 'qrcode'

interface Props {
  modelValue: boolean
  shareUrl: string
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const dialogVisible = computed({
  get: () => props.modelValue,
  set: (val: boolean) => emit('update:modelValue', val),
})

const qrCanvas = ref<HTMLCanvasElement | null>(null)

// Resolve absolute URL: prefer VITE_PUBLIC_FRONTEND_URL, fallback to origin
const resolveShareUrl = () => {
  const publicUrl = import.meta.env.VITE_PUBLIC_FRONTEND_URL
  if (publicUrl) {
    // If shareUrl is already absolute, use it; otherwise prefix
    if (props.shareUrl && props.shareUrl.startsWith('http')) {
      return props.shareUrl
    }
    return `${publicUrl.endsWith('/') ? publicUrl : publicUrl + '/'}${props.shareUrl?.replace(/^\//, '')}`
  }
  // Fallback: origin + relative path
  if (props.shareUrl && props.shareUrl.startsWith('http')) {
    return props.shareUrl
  }
  return `${window.location.origin}${props.shareUrl}`
}
const absoluteShareUrl = computed(resolveShareUrl)

const generateQR = async () => {
  await nextTick()
  const canvas = qrCanvas.value
  if (!canvas) return

  const url = resolveShareUrl()
  if (!url) return

  try {
    await QRCode.toCanvas(canvas, url, {
      width: 180,
      margin: 2,
      color: { dark: '#1e325a', light: '#ffffff' },
    })
  } catch {
    ElMessage.error('二维码生成失败')
  }
}

const handleCopy = async () => {
  const url = resolveShareUrl()
  try {
    await navigator.clipboard.writeText(url)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败')
  }
}

const handleDownload = () => {
  const canvas = qrCanvas.value
  if (!canvas) return
  try {
    const url = canvas.toDataURL('image/png')
    const link = document.createElement('a')
    link.href = url
    link.download = `share-qr-${Date.now()}.png`
    link.click()
    ElMessage.success('二维码已下载')
  } catch {
    ElMessage.error('下载失败')
  }
}

const handlePreview = () => {
  const url = resolveShareUrl()
  window.open(url, '_blank')
}

watch(dialogVisible, async (val) => {
  if (val) {
    await nextTick()
    await generateQR()
  }
})
</script>

<style scoped>
.share-result-dialog :deep(.el-dialog) {
  border-radius: 28px !important;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(30, 50, 90, 0.15);
}

.share-result-dialog :deep(.el-dialog__header) {
  background: linear-gradient(135deg, rgba(30, 50, 90, 0.06), rgba(30, 50, 90, 0.02));
  padding: 20px 24px 16px;
  margin-right: 0;
  border-bottom: 1px solid rgba(30, 50, 90, 0.06);
}

.share-result-dialog :deep(.el-dialog__title) {
  color: #5E6470;
  font-weight: 700;
  font-size: 18px;
}

.share-result-dialog :deep(.el-dialog__body) {
  padding: 24px;
}

.share-alert {
  border-radius: 12px;
  margin-bottom: 16px;
}

.share-url-input :deep(.el-input__wrapper) {
  border-radius: 20px;
}

.share-url-input :deep(.el-input-group__append) {
  border-radius: 0 20px 20px 0;
}

.qr-section {
  display: flex;
  justify-content: center;
  margin: 16px 0;
}

.qr-canvas {
  width: 180px !important;
  height: 180px !important;
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(30, 50, 90, 0.1);
}

.share-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
  flex-wrap: wrap;
}

.capsule-btn {
  border-radius: 20px !important;
  padding: 8px 20px;
  font-weight: 500;
  transition: 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.capsule-btn:hover {
  transform: scale(1.03);
}

.capsule-btn:active {
  transform: scale(0.97);
}

.capsule-btn-primary {
  background: rgba(30, 50, 90, 0.85);
  border-color: rgba(30, 50, 90, 0.85);
}

.capsule-btn-primary:hover {
  background: rgba(30, 50, 90, 0.92);
  border-color: rgba(30, 50, 90, 0.92);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .share-result-dialog :deep(.el-dialog) {
    width: 95vw !important;
    max-width: 95vw;
    margin: 8px auto;
  }

  .share-result-dialog :deep(.el-dialog__body) {
    padding: 16px;
  }

  .share-actions {
    flex-direction: column;
  }

  .share-actions .capsule-btn {
    width: 100%;
  }
}
</style>
