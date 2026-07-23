<template>
  <div class="media-uploader">
    <el-upload
      ref="uploadRef"
      drag
      multiple
      :auto-upload="false"
      :accept="acceptStr"
      :on-change="handleChange"
      :before-upload="beforeUpload"
      :file-list="fileList"
      list-type="text"
      class="upload-zone"
    >
      <el-icon
        class="upload-icon"
        :size="40"
      >
        <UploadFilled />
      </el-icon>
      <div class="upload-text">
        <p class="text-lg font-semibold">
          点击上传 或 拖拽文件到此处
        </p>
        <p class="text-sm text-gray-500 mt-1">
          支持 JPG, PNG, WebP, PDF (最大 50MB)
        </p>
      </div>
    </el-upload>

    <div
      v-if="uploads.length > 0"
      class="upload-queue mt-4"
    >
      <h4 class="text-sm font-semibold text-gray-700 mb-2">
        上传队列 ({{ uploads.length }})
      </h4>
      <div
        v-for="item in uploads"
        :key="item.id"
        class="upload-item"
      >
        <div class="upload-item-info">
          <el-icon
            v-if="item.status === 'success'"
            class="status-icon success"
            :size="18"
          >
            <CircleCheckFilled />
          </el-icon>
          <el-icon
            v-else-if="item.status === 'error'"
            class="status-icon error"
            :size="18"
          >
            <CircleCloseFilled />
          </el-icon>
          <el-icon
            v-else
            class="status-icon loading"
            :size="18"
          >
            <Loading />
          </el-icon>
          <div class="upload-item-text">
            <span class="file-name">{{ item.name }}</span>
            <span class="file-meta">
              {{ formatSize(item.size) }}
              <span
                v-if="item.status === 'uploading'"
                class="ml-1"
              >— {{ item.progress }}%</span>
              <span
                v-else-if="item.status === 'error'"
                class="ml-1 text-red-500"
              >{{ item.error }}</span>
            </span>
          </div>
        </div>
        <el-progress
          v-if="item.status === 'uploading'"
          :percentage="item.progress"
          :stroke-width="4"
          :show-text="false"
          class="upload-progress"
        />
        <el-button
          v-if="item.status === 'error'"
          size="small"
          text
          type="danger"
          @click="removeUpload(item.id)"
        >
          移除
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadInstance, UploadFile } from 'element-plus'
import { UploadFilled, CircleCheckFilled, CircleCloseFilled, Loading } from '@element-plus/icons-vue'
import { mediaApi, formatSize } from '@/api/media'
import type { MediaItem } from '@/api/media'

const emit = defineEmits<{
  uploaded: [item: MediaItem]
}>()

const acceptStr = 'image/*,.pdf'
const uploadRef = ref<UploadInstance>()
const fileList = ref<UploadFile[]>([])
const uploads = ref<{
  id: string
  name: string
  size: number
  status: 'uploading' | 'success' | 'error'
  progress: number
  error?: string
}[]>([])

function beforeUpload(rawFile: File): boolean {
  if (rawFile.size > 50 * 1024 * 1024) {
    addUploadTask(rawFile, 'error', 0, '文件超过 50MB 限制')
    return false
  }
  if (!isAllowedFile(rawFile)) {
    addUploadTask(rawFile, 'error', 0, '仅支持 JPG、PNG、WebP、PDF')
    ElMessage.error('仅支持 JPG、PNG、WebP、PDF')
    return false
  }
  return true
}

function handleChange(uploadFile: UploadFile) {
  const raw = uploadFile.raw
  if (!raw) return
  if (raw.size > 50 * 1024 * 1024) {
    addUploadTask(raw, 'error', 0, '文件超过 50MB 限制')
    ElMessage.error('文件超过 50MB 限制')
    return
  }
  if (!isAllowedFile(raw)) {
    addUploadTask(raw, 'error', 0, '仅支持 JPG、PNG、WebP、PDF')
    ElMessage.error('仅支持 JPG、PNG、WebP、PDF')
    return
  }

  addUploadTask(raw, 'uploading', 0)
  simulateUpload(raw)
}

function addUploadTask(file: File, status: 'uploading' | 'success' | 'error', progress: number, error?: string) {
  uploads.value.push({
    id: Math.random().toString(36).substr(2, 9),
    name: file.name,
    size: file.size,
    status,
    progress,
    error,
  })
}

async function simulateUpload(file: File) {
  const task = uploads.value.find((t) => t.name === file.name && t.status === 'uploading')
  if (!task) return

  const interval = setInterval(() => {
    if (task.progress < 90) task.progress += 10
  }, 200)

  try {
    const result = await mediaApi.upload(file)
    clearInterval(interval)
    task.progress = 100
    task.status = 'success'
    ElMessage.success(`${file.name} 上传成功`)
    emit('uploaded', result)
  } catch (err: unknown) {
    clearInterval(interval)
    task.status = 'error'
    if (err instanceof Error) {
      task.error = err.message
    } else {
      task.error = '上传失败'
    }
    console.error('[MediaUploader] Upload error:', err)
    ElMessage.error(task.error)
  }
}

function isAllowedFile(file: File): boolean {
  return ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'].includes(file.type)
}

function removeUpload(id: string) {
  uploads.value = uploads.value.filter((u) => u.id !== id)
}
</script>

<style scoped>
.upload-zone {
  width: 100%;
}
.upload-icon {
  margin-bottom: 8px;
  color: var(--el-color-primary);
}
.upload-text p {
  margin: 0;
}
.upload-queue {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.upload-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 12px;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}
.upload-item-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-icon {
  flex-shrink: 0;
}
.status-icon.success { color: var(--el-color-success); }
.status-icon.error { color: var(--el-color-danger); }
.status-icon.loading { color: var(--el-color-primary); animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.upload-item-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.file-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.upload-progress {
  margin-top: 4px;
}
</style>
