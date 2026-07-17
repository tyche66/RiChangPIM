<template>
  <div class="import-page">
    <el-card>
      <div class="toolbar">
        <h2>批量导入产品</h2>
      </div>

      <el-alert
        title="导入说明"
        type="info"
        :closable="false"
        style="margin-bottom: 20px"
      >
        <template #default>
          <ul style="margin: 8px 0 0 0; padding-left: 20px;">
            <li>请下载模板文件，按照模板格式填写产品数据</li>
            <li>必填列：product_no（产品编号）、product_name（产品名称）、face_price（面价）</li>
            <li>可选列：brand_name、supplier_name、category_name、cost_price、material、stock_status、status、tag_names</li>
            <li>tag_names 支持多个标签用英文逗号分隔</li>
            <li>brand_name、supplier_name、category_name 必须为系统中已存在的名称</li>
          </ul>
        </template>
      </el-alert>

      <el-form
        :inline="true"
        class="import-form"
      >
        <el-form-item label="重复处理">
          <el-checkbox v-model="skipIfExists">
            跳过已存在的产品编号
          </el-checkbox>
        </el-form-item>
      </el-form>

      <div class="upload-area">
        <el-upload
          ref="uploadRef"
          drag
          :auto-upload="false"
          :on-change="handleFileChange"
          :on-remove="handleFileRemove"
          :limit="1"
          accept=".xlsx,.xls"
          class="upload-dropzone"
        >
          <el-icon class="el-icon--upload">
            <UploadFilled />
          </el-icon>
          <div class="el-upload__text">
            将文件拖到此处，或 <em>点击上传</em>
          </div>
          <template #tip>
            <div class="el-upload__tip">
              仅支持 .xlsx / .xls 格式文件
            </div>
          </template>
        </el-upload>
      </div>

      <div
        v-if="selectedFile"
        class="import-actions"
      >
        <el-button
          type="primary"
          :loading="importing"
          :disabled="!selectedFile"
          @click="handleImport"
        >
          开始导入
        </el-button>
        <el-button @click="handleReset">
          重置
        </el-button>
      </div>

      <!-- Results -->
      <div
        v-if="importResult"
        class="import-result"
      >
        <el-divider content-position="left">
          导入结果
        </el-divider>
        <el-descriptions
          :column="3"
          border
          style="margin-bottom: 16px"
        >
          <el-descriptions-item label="总行数">
            {{ importResult.total }}
          </el-descriptions-item>
          <el-descriptions-item label="成功数">
            <el-tag type="success">
              {{ importResult.successCount }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="失败数">
            <el-tag type="danger">
              {{ importResult.failCount }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <div
          v-if="importResult.failures && importResult.failures.length > 0"
          class="failures-table"
        >
          <h4>失败明细</h4>
          <el-table
            :data="importResult.failures"
            border
            size="small"
            max-height="300"
          >
            <el-table-column
              prop="row"
              label="行号"
              width="80"
              align="center"
            />
            <el-table-column
              prop="productNo"
              label="产品编号"
              width="150"
            />
            <el-table-column
              prop="reason"
              label="失败原因"
              show-overflow-tooltip
            />
          </el-table>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import type { UploadUserFile, UploadInstance } from 'element-plus'
import { productApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()
const userPermissions = computed(() => authStore.userPermissions)
const canImport = computed(() => hasPermission(userPermissions.value, 'product:import'))

const uploadRef = ref<UploadInstance>()
const selectedFile = ref<UploadUserFile | null>(null)
const skipIfExists = ref(false)
const importing = ref(false)
const importResult = ref<{
  total: number
  successCount: number
  failCount: number
  failures: { row: number; productNo: string; reason: string }[]
} | null>(null)

const handleFileChange = (file: UploadUserFile) => {
  selectedFile.value = file
}

const handleFileRemove = () => {
  selectedFile.value = null
  importResult.value = null
}

const handleReset = () => {
  selectedFile.value = null
  importResult.value = null
  skipIfExists.value = false
  uploadRef.value?.clearFiles()
}

const handleImport = async () => {
  if (!selectedFile.value?.raw) {
    ElMessage.warning('请先选择文件')
    return
  }

  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value.raw)

    const res = await productApi.import(formData, { skipIfExists: skipIfExists.value })
    importResult.value = {
      total: res.data?.total || 0,
      successCount: res.data?.success_count || 0,
      failCount: res.data?.fail_count || 0,
      failures: res.data?.failures || [],
    }

    if (importResult.value.failCount === 0) {
      ElMessage.success(`导入完成，共成功 ${importResult.value.successCount} 条`)
    } else {
      ElMessage.warning(`导入完成，成功 ${importResult.value.successCount} 条，失败 ${importResult.value.failCount} 条`)
    }
  } catch (e: any) {
    const msg = e?.response?.data?.detail?.msg || e?.message || '导入失败'
    ElMessage.error(msg)
  } finally {
    importing.value = false
  }
}

onMounted(() => {
  if (!canImport.value) {
    ElMessage.error('无权限访问导入功能')
  }
})
</script>

<style scoped>
.import-page {
  min-height: 100vh;
  background: #f0f0f0;
  padding: 24px;
  box-sizing: border-box;
}

.import-page :deep(.el-card) {
  background: rgba(255, 255, 255, 0.68);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  box-shadow: 0 4px 32px rgba(30, 50, 90, 0.06);
}

.import-page :deep(.el-card__body) {
  padding: 24px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: rgb(30, 50, 90);
  letter-spacing: 0.3px;
}

.import-form {
  margin-bottom: 16px;
}

.import-form :deep(.el-button) {
  border-radius: 20px;
}

.upload-area {
  display: flex;
  justify-content: center;
  margin: 24px 0;
}

.upload-dropzone {
  width: 100%;
  max-width: 600px;
}

.upload-dropzone :deep(.el-upload-dragger) {
  border-radius: 20px;
  border: 2px dashed rgba(30, 50, 90, 0.2);
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.upload-dropzone :deep(.el-upload-dragger:hover) {
  border-color: rgb(30, 50, 90);
  background: rgba(30, 50, 90, 0.03);
}

.import-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin: 24px 0;
}

.import-actions :deep(.el-button) {
  border-radius: 20px;
}

.import-result {
  margin-top: 24px;
}

.failures-table {
  margin-top: 16px;
}

.failures-table h4 {
  margin: 0 0 12px 0;
  color: #5E6470;
  font-weight: 600;
}

@media (max-width: 768px) {
  .import-page {
    padding: 12px;
  }
  .import-page :deep(.el-card__body) {
    padding: 16px;
  }
  .toolbar h2 {
    font-size: 18px;
  }
}
</style>
