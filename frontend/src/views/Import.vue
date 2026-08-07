<template>
  <div class="import-page">
    <el-card>
      <div class="toolbar">
        <h2>批量导入产品</h2>
        <el-button
          :loading="downloading"
          @click="handleDownloadTemplate"
        >
          <el-icon class="btn-icon">
            <Download />
          </el-icon>
          下载导入模板
        </el-button>
      </div>

      <el-alert
        title="导入说明"
        type="info"
        :closable="false"
        style="margin-bottom: 20px"
      >
        <template #default>
          <ul class="tips-list">
            <li>先点右上角「下载导入模板」，模板的「填写说明」工作表里有完整规则</li>
            <li>必填列：产品编号、产品名称、面价。列名认中文也认英文，表头不必是第一行</li>
            <li>
              品牌、供应商、分类必须填系统里<strong>已存在</strong>的名称（导入不会自动新建），
              三列都留空的行会失败
            </li>
            <li>面价填「待核价 / 面议」或留空时，按占位价 99999 导入并标成「待补充」</li>
            <li>
              图片有三种给法：①把图片直接贴进「主图 / 产品图 / 场景图」单元格
              （WPS 的嵌入单元格、Excel 365 的置于单元格内、压在该行上的浮动图片都能识别）；
              ②把表格和图片一起打成 .zip 上传，格里填图片文件名，或者让文件名以产品编号开头
              （SUNON-001.jpg、SUNON-001_2.jpg 会自动归到该产品，名字带「场景 / scene」的进场景图）；
              ③格里填 http(s) 图片直链（需要管理员先开启外链抓取）
            </li>
            <li>主图列的第一张图设为封面；同一张场景图被多行引用时只入库一份并共享</li>
            <li>每行独立提交，一行失败不影响其它行；失败明细会给出行号、编号和原因</li>
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
          accept=".xlsx,.xlsm,.zip"
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
              表格支持 .xlsx / .xlsm；需要连图片一起导入时，把表格和图片打成 .zip 上传。<br>
              默认上限：单文件 512MB、5000 行、单张图片 20MB（可由管理员在服务端调整）
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
        <el-button
          :disabled="importing"
          @click="handleReset"
        >
          重置
        </el-button>
      </div>

      <div
        v-if="importing"
        class="import-progress"
      >
        <el-progress
          :percentage="uploadPercent"
          :status="phase === 'processing' ? 'success' : ''"
        />
        <div class="progress-hint">
          {{ phase === 'processing'
            ? '文件已送达，服务端正在解析图片、上传并写入数据库。带图的大文件可能要几分钟，请不要关闭页面。'
            : '正在上传…' }}
        </div>
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
          <el-descriptions-item label="数据行数">
            {{ importResult.total }}
          </el-descriptions-item>
          <el-descriptions-item label="成功">
            <el-tag type="success">
              {{ importResult.successCount }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="失败">
            <el-tag :type="importResult.failCount > 0 ? 'danger' : 'info'">
              {{ importResult.failCount }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="产品图片">
            {{ importResult.imageCount }} 张
          </el-descriptions-item>
          <el-descriptions-item label="场景图">
            {{ importResult.sceneImageCount }} 张
          </el-descriptions-item>
          <el-descriptions-item label="实际上传">
            {{ importResult.uploadedCount }} 个文件（同一张图只存一份）
          </el-descriptions-item>
          <el-descriptions-item label="表头行">
            第 {{ importResult.headerRow }} 行
          </el-descriptions-item>
          <el-descriptions-item
            label="图片来源"
            :span="2"
          >
            <template v-if="importResult.imageSources.length > 0">
              <el-tag
                v-for="source in importResult.imageSources"
                :key="source"
                size="small"
                type="info"
                class="source-tag"
              >
                {{ sourceLabel(source) }}
              </el-tag>
            </template>
            <span
              v-else
              class="muted"
            >
              这次没识别到图片
            </span>
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="importResult.imageWarnings.length > 0"
          type="warning"
          :closable="false"
          class="result-alert"
        >
          <template #title>
            图片提示（{{ importResult.imageWarnings.length }} 条）
          </template>
          <template #default>
            <ul class="tips-list">
              <li
                v-for="(item, index) in importResult.imageWarnings"
                :key="`img-${index}`"
              >
                {{ item }}
              </li>
            </ul>
          </template>
        </el-alert>

        <el-alert
          v-if="importResult.notes.length > 0"
          type="info"
          :closable="false"
          class="result-alert"
        >
          <template #title>
            数据提示（{{ importResult.notes.length }} 条）
          </template>
          <template #default>
            <ul class="tips-list">
              <li
                v-for="(item, index) in importResult.notes"
                :key="`note-${index}`"
              >
                {{ item }}
              </li>
            </ul>
          </template>
        </el-alert>

        <el-alert
          v-if="importResult.unknownHeaders.length > 0"
          type="info"
          :closable="false"
          class="result-alert"
        >
          <template #title>
            有 {{ importResult.unknownHeaders.length }} 列没被识别，已忽略
          </template>
          <template #default>
            <span class="muted">{{ importResult.unknownHeaders.join('、') }}</span>
          </template>
        </el-alert>

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
            <!-- 排版层级用 class-name（不是 class）：class 会落到 hidden-columns 的隐藏占位 div 上，规则不生效 -->
            <el-table-column
              prop="row"
              label="行号"
              width="80"
              align="center"
              class-name="cell-num"
            />
            <el-table-column
              prop="product_no"
              label="产品编号"
              width="150"
              class-name="cell-code"
            />
            <el-table-column
              prop="reason"
              label="失败原因"
              class-name="cell-meta"
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
import { UploadFilled, Download } from '@element-plus/icons-vue'
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
const downloading = ref(false)
const uploadPercent = ref(0)
// uploading = 请求体还在往上传；processing = 后端在解包/传图/写库（进度条不动的那段）。
type ImportPhase = 'idle' | 'uploading' | 'processing'
const phase = ref<ImportPhase>('idle')
// 走函数赋值，不在 handleImport 里直接写 phase.value = 'uploading'：那样 TS 的控制流
// 分析会把 phase.value 收窄成字面量 'uploading'，catch 里再比 'processing' 就成了
// 「两个类型没有交集」的编译错误（上传回调里的赋值它看不到）。
const setPhase = (next: ImportPhase) => {
  phase.value = next
}

type ImportFailure = { row: number; product_no: string; reason: string }

const importResult = ref<{
  total: number
  successCount: number
  failCount: number
  failures: ImportFailure[]
  notes: string[]
  imageCount: number
  sceneImageCount: number
  uploadedCount: number
  imageSources: string[]
  imageWarnings: string[]
  headerRow: number
  unknownHeaders: string[]
} | null>(null)

// 后端给的是取图方式的内部标记（excel_images / product_import_media 里的 source）。
const SOURCE_LABELS: Record<string, string> = {
  anchor: '贴在单元格上的浮动图片',
  dispimg: 'WPS 嵌入单元格',
  richvalue: 'Excel 置于单元格内',
  zip: '压缩包内的图片文件',
  convention: '压缩包内按产品编号匹配',
  url: '外链抓取',
}

const sourceLabel = (source: string) => SOURCE_LABELS[source] || source

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
  uploadPercent.value = 0
  setPhase('idle')
  uploadRef.value?.clearFiles()
}

const handleDownloadTemplate = async () => {
  downloading.value = true
  try {
    const blob = await productApi.importTemplate()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'products_import_template.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    // 错误提示由 api 拦截器统一弹出
  } finally {
    downloading.value = false
  }
}

const handleImport = async () => {
  if (!selectedFile.value?.raw) {
    ElMessage.warning('请先选择文件')
    return
  }

  importing.value = true
  importResult.value = null
  uploadPercent.value = 0
  setPhase('uploading')
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value.raw)

    const res = await productApi.import(
      formData,
      { skipIfExists: skipIfExists.value },
      (percent) => {
        uploadPercent.value = percent
        if (percent >= 100) setPhase('processing')
      }
    )
    const data = res.data || {}
    importResult.value = {
      total: data.total || 0,
      successCount: data.success_count || 0,
      failCount: data.fail_count || 0,
      failures: data.failures || [],
      notes: data.notes || [],
      imageCount: data.image_count || 0,
      sceneImageCount: data.scene_image_count || 0,
      uploadedCount: data.uploaded_count || 0,
      imageSources: data.image_sources || [],
      imageWarnings: data.image_warnings || [],
      headerRow: data.header_row || 1,
      unknownHeaders: data.unknown_headers || [],
    }

    const images = importResult.value.imageCount + importResult.value.sceneImageCount
    const withImages = images > 0 ? `，图片 ${images} 张` : ''
    if (importResult.value.failCount === 0) {
      ElMessage.success(`导入完成，成功 ${importResult.value.successCount} 条${withImages}`)
    } else {
      ElMessage.warning(
        `导入完成，成功 ${importResult.value.successCount} 条，` +
        `失败 ${importResult.value.failCount} 条${withImages}`
      )
    }
  } catch (e: any) {
    // productApi.import 带 suppressErrorMessage，这里是唯一的报错出口。
    // 超时和 413 都不带后端的 detail.msg（前者压根没响应，后者是 nginx 的 HTML），
    // 单独给话术，否则用户只会看到 "Request failed with status code 413"。
    let msg: string
    if (e?.code === 'ECONNABORTED' || e?.code === 'ETIMEDOUT') {
      msg = phase.value === 'processing'
        ? '等待服务端处理超时。导入可能仍在后台继续，请先去产品列表确认，再决定是否重传'
        : '上传超时，请检查网络或把文件拆小后重试'
    } else if (e?.response?.status === 413) {
      msg = '文件超过网关允许的大小，请拆分成多个文件，或让管理员调大 nginx 的 client_max_body_size'
    } else {
      msg = e?.response?.data?.detail?.msg || e?.message || '导入失败'
    }
    ElMessage.error(msg)
  } finally {
    importing.value = false
    setPhase('idle')
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

.btn-icon {
  margin-right: 4px;
}

.tips-list {
  margin: 8px 0 0 0;
  padding-left: 20px;
  line-height: 1.7;
}

.import-progress {
  max-width: 600px;
  margin: 0 auto 24px auto;
}

.progress-hint {
  margin-top: 8px;
  font-size: 13px;
  color: #5E6470;
  text-align: center;
}

.result-alert {
  margin-bottom: 16px;
  border-radius: 12px;
}

.source-tag {
  margin-right: 6px;
}

.muted {
  color: #909399;
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
