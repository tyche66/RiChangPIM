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
            <li>
              重传同一个产品包时先做<strong>预检</strong>：弹窗里会写清「新增 / 已存在 / 无法导入」各多少条，
              再由你选择<strong>覆盖</strong>、<strong>追加信息</strong>还是<strong>跳过已存在</strong>
            </li>
            <li>
              覆盖与追加都遵循「<strong>空白 = 不改</strong>」：表格里没填的单元格不会把系统里已有的名称、
              面价、状态清掉；覆盖模式下图片会整套替换，追加模式下图片只增不减
            </li>
            <li>每行独立提交，一行失败不影响其它行；失败明细会给出行号、编号和原因</li>
          </ul>
        </template>
      </el-alert>

      <el-alert
        v-if="preflightError"
        type="error"
        :closable="false"
        class="result-alert"
      >
        <template #title>
          {{ preflightError }}
        </template>
      </el-alert>

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
          :loading="preflighting"
          :disabled="!selectedFile"
          @click="handlePreflight"
        >
          开始导入
        </el-button>
        <el-button
          :disabled="preflighting || confirming"
          @click="handleReset"
        >
          重置
        </el-button>
      </div>

      <div
        v-if="preflighting || confirming"
        class="import-progress"
      >
        <el-progress
          :percentage="uploadPercent"
          :status="phase === 'processing' || confirming ? 'success' : ''"
        />
        <div class="progress-hint">
          {{ progressHint }}
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
          <el-descriptions-item label="新增">
            <el-tag type="success">
              {{ importResult.createdCount }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="更新">
            {{ importResult.updatedCount }}
          </el-descriptions-item>
          <el-descriptions-item label="追加">
            {{ importResult.appendedCount }}
          </el-descriptions-item>
          <el-descriptions-item label="跳过">
            {{ importResult.skippedCount }}
          </el-descriptions-item>
          <el-descriptions-item label="失败">
            <el-tag :type="importResult.failCount > 0 ? 'danger' : 'info'">
              {{ importResult.failCount }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="产品图片">
            {{ importResult.imageCount }} 张
            <span
              v-if="importResult.imagesReplaced || importResult.imagesAppended"
              class="muted"
            >
              （替换 {{ importResult.imagesReplaced }} · 追加 {{ importResult.imagesAppended }}）
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="场景图">
            {{ importResult.sceneImageCount }} 张
          </el-descriptions-item>
          <el-descriptions-item label="新建标签">
            {{ importResult.createdTags }} 个
            <span
              v-if="importResult.newTagNames.length"
              class="muted"
            >（{{ importResult.newTagNames.slice(0, 6).join('、') }}{{ importResult.newTagNames.length > 6 ? '…' : '' }}）</span>
          </el-descriptions-item>
          <el-descriptions-item label="实际上传">
            {{ importResult.uploadedCount }} 个文件（同一张图只存一份）
          </el-descriptions-item>
          <el-descriptions-item label="表头行">
            第 {{ importResult.headerRow }} 行
          </el-descriptions-item>
          <el-descriptions-item
            v-if="importResult.backupId"
            label="覆盖前快照"
            :span="3"
          >
            <span class="cell-code">{{ importResult.backupId }}</span>
            <span class="muted">
              如需回滚，让管理员执行
              <code>python -m app.scripts.restore_import_backup {{ importResult.backupId }}</code>
            </span>
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

    <!-- 预检弹窗：先看清新增/已存在/无法导入，再决定覆盖、追加还是跳过 -->
    <ImportConflictDialog
      v-model="showConflictDialog"
      :preflight="preflight"
      :confirming="confirming"
      @confirm="handleCommit"
      @cancel="handleCancelPreflight"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Download } from '@element-plus/icons-vue'
import type { UploadUserFile, UploadInstance } from 'element-plus'
import { productApi } from '@/api'
import type { ImportMode, ImportPreflightPayload } from '@/api'
import ImportConflictDialog from '@/components/ImportConflictDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { hasPermission } from '@/types/permissions'

const authStore = useAuthStore()
const userPermissions = computed(() => authStore.userPermissions)
const canImport = computed(() => hasPermission(userPermissions.value, 'product:import'))

const uploadRef = ref<UploadInstance>()
const selectedFile = ref<UploadUserFile | null>(null)
// 预检阶段（上传 + 解析 + 查重，零写库）与提交阶段分开，界面上的进度条也分两段。
const preflighting = ref(false)
const confirming = ref(false)
const downloading = ref(false)
const uploadPercent = ref(0)
const preflight = ref<ImportPreflightPayload | null>(null)
const showConflictDialog = ref(false)
const preflightError = ref('')

// uploading = 请求体还在往上传；processing = 后端在解包/查重或写库（进度条不动的那段）。
type ImportPhase = 'idle' | 'uploading' | 'processing'
const phase = ref<ImportPhase>('idle')
// 走函数赋值，不在 handle 里直接写 phase.value = 'uploading'：那样 TS 的控制流
// 分析会把 phase.value 收窄成字面量 'uploading'，catch 里再比 'processing' 就成了
// 「两个类型没有交集」的编译错误（上传回调里的赋值它看不到）。
const setPhase = (next: ImportPhase) => {
  phase.value = next
}

const progressHint = computed(() => {
  if (confirming.value) {
    return '正在按你选择的模式写入数据库（含图片替换 / 追加）。带图的大文件可能要几分钟，请不要关闭页面。'
  }
  if (phase.value === 'processing') {
    return '文件已送达，服务端正在解析表格并查重（不会写库）。带图的大文件可能要一两分钟。'
  }
  return '正在上传…'
})

type ImportFailure = { row: number; product_no: string; reason: string }

const importResult = ref<{
  total: number
  successCount: number
  failCount: number
  createdCount: number
  updatedCount: number
  appendedCount: number
  skippedCount: number
  imagesReplaced: number
  imagesAppended: number
  createdTags: number
  newTagNames: string[]
  backupId: string | null
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
  preflightError.value = ''
}

const handleFileRemove = () => {
  void cancelPendingPreflight()
  selectedFile.value = null
  importResult.value = null
}

const cancelPendingPreflight = async () => {
  const token = preflight.value?.token
  preflight.value = null
  showConflictDialog.value = false
  if (token) {
    try {
      await productApi.cancelImportPreflight(token)
    } catch {
      // 取消只是尽力清理暂存，TTL 到期也会被扫掉，不打扰用户
    }
  }
}

const handleReset = async () => {
  await cancelPendingPreflight()
  selectedFile.value = null
  importResult.value = null
  preflightError.value = ''
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

const importErrorMessage = (e: any, stage: 'preflight' | 'commit'): string => {
  if (e?.code === 'ECONNABORTED' || e?.code === 'ETIMEDOUT') {
    return stage === 'commit'
      ? '等待服务端处理超时。导入可能仍在后台继续，请先去产品列表确认，再决定是否重传'
      : '解析预检超时，请检查网络或把文件拆小后重试'
  }
  if (e?.response?.status === 413) {
    return '文件超过网关允许的大小，请拆分成多个文件，或让管理员调大 nginx 的 client_max_body_size'
  }
  return e?.response?.data?.detail?.msg || e?.message || '导入失败'
}

/**
 * 第一步：上传 + 预检。服务端只解析与查重，不写库，返回 token 与冲突清单。
 * 预检失败不弹窗——文件根本没被接收，用户改完直接重传即可。
 */
const handlePreflight = async () => {
  if (!selectedFile.value?.raw) {
    ElMessage.warning('请先选择文件')
    return
  }

  preflighting.value = true
  importResult.value = null
  preflightError.value = ''
  uploadPercent.value = 0
  setPhase('uploading')
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value.raw)

    const res = await productApi.importPreflight(formData, (percent) => {
      uploadPercent.value = percent
      if (percent >= 100) setPhase('processing')
    })
    preflight.value = res.data
    showConflictDialog.value = true
  } catch (e: any) {
    preflightError.value = importErrorMessage(e, 'preflight')
    ElMessage.error(preflightError.value)
  } finally {
    preflighting.value = false
    setPhase('idle')
  }
}

/**
 * 第二步：按用户在弹窗里选的模式真正写库（覆盖 / 追加 / 跳过）。
 * token 单次消费：重复点确认、或预检已过期，后端都会回 409/404，这里关掉弹窗
 * 让用户重新选文件，绝不自动重试（重试等于把同一份包写两遍）。
 */
const handleCommit = async ({
  mode,
  backup,
  new_tag_type,
}: {
  mode: ImportMode
  backup: boolean
  new_tag_type: string
}) => {
  const token = preflight.value?.token
  if (!token) {
    ElMessage.warning('预检已过期，请重新选择文件')
    showConflictDialog.value = false
    return
  }

  confirming.value = true
  uploadPercent.value = 100
  try {
    const res = await productApi.importCommit({ token, mode, backup, new_tag_type })
    showConflictDialog.value = false
    preflight.value = null
    applyCommitResult(res.data || {})
  } catch (e: any) {
    ElMessage.error(importErrorMessage(e, 'commit'))
    const status = e?.response?.status
    if (status === 404 || status === 409) {
      showConflictDialog.value = false
      preflight.value = null
    }
  } finally {
    confirming.value = false
  }
}

const handleCancelPreflight = async () => {
  await cancelPendingPreflight()
  ElMessage.info('已取消，这轮预检的暂存文件已清理')
}

const applyCommitResult = (data: Record<string, any>) => {
  importResult.value = {
    total: data.total || 0,
    successCount: data.success_count || 0,
    failCount: data.fail_count || 0,
    createdCount: data.created_count || 0,
    updatedCount: data.updated_count || 0,
    appendedCount: data.appended_count || 0,
    skippedCount: data.skipped_count || 0,
    imagesReplaced: data.images_replaced || 0,
    imagesAppended: data.images_appended || 0,
    createdTags: data.created_tags || 0,
    newTagNames: data.new_tag_names || [],
    backupId: data.backup_id || null,
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

  const result = importResult.value
  const parts = [
    result.createdCount ? `新增 ${result.createdCount}` : '',
    result.updatedCount ? `更新 ${result.updatedCount}` : '',
    result.appendedCount ? `追加 ${result.appendedCount}` : '',
    result.skippedCount ? `跳过 ${result.skippedCount}` : '',
    result.failCount ? `失败 ${result.failCount}` : '',
  ].filter(Boolean)

  if (result.failCount > 0) {
    ElMessage.warning(`导入完成：${parts.join('，')}`)
  } else {
    ElMessage.success(`导入完成：${parts.join('，') || '没有需要写入的行'}`)
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
  background: var(--pim-page);
  padding: 24px;
  box-sizing: border-box;
}

.import-page :deep(.el-card) {
  background: var(--pim-glass);
  border-radius: 28px;
  border: 1px solid var(--pim-surface-border);
  box-shadow: 0 4px 32px rgba(var(--pim-brand), 0.06);
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
  color: rgb(var(--pim-brand));
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
  color: var(--pim-text-primary);
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
  color: var(--pim-text-faint);
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
  border: 2px dashed rgba(var(--pim-brand), 0.2);
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.upload-dropzone :deep(.el-upload-dragger:hover) {
  border-color: rgb(var(--pim-brand));
  background: rgba(var(--pim-brand), 0.03);
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
  color: var(--pim-text-primary);
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
