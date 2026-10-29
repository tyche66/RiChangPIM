<template>
  <div class="share-page">
    <div class="share-brand-header">
      <div class="brand-logo">
        AI-PIM
      </div>
      <div class="brand-subtitle">
        产品信息共享平台
      </div>
    </div>

    <el-card
      v-loading="loading"
      class="share-card"
    >
      <template #header>
        <div class="card-header">
          <span class="card-title">分享预览</span>
          <el-tag
            :type="accessResult === 'success' ? 'success' : 'danger'"
            class="status-tag"
          >
            {{ accessResult === 'success' ? '有效链接' : '链接失效' }}
          </el-tag>
        </div>
      </template>

      <!-- Password prompt -->
      <el-alert
        v-if="needPassword && accessResult !== 'success'"
        type="warning"
        title="该分享需要访问密码"
        :closable="false"
        class="password-alert"
      />

      <el-input
        v-if="needPassword && accessResult !== 'success'"
        v-model="passwordInput"
        type="password"
        placeholder="请输入访问密码"
        show-password
        class="password-input"
      >
        <template #append>
          <el-button
            type="primary"
            :loading="loading"
            class="verify-btn"
            @click="fetchContent"
          >
            验证
          </el-button>
        </template>
      </el-input>

      <!-- Error state -->
      <el-alert
        v-if="accessResult && accessResult !== 'success' && accessResult !== 'denied_password'"
        type="error"
        :title="errorMessage"
        :closable="false"
        class="error-alert"
      />

      <!-- Content -->
      <div
        v-if="proposalContent || quotationContent"
        class="share-content"
      >
        <!-- Proposal content -->
        <template v-if="shareData.share_type === 'proposal'">
          <div class="content-section">
            <h3 class="section-heading">
              方案信息
            </h3>
            <el-descriptions
              :column="1"
              border
              class="info-descriptions"
            >
              <el-descriptions-item label="方案编号">
                <span class="mono-text">{{ proposalContent?.proposal_no || '-' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="方案名称">
                {{ proposalContent?.proposal_name || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="客户名称">
                {{ proposalContent?.customer_name || '-' }}
              </el-descriptions-item>
              <el-descriptions-item label="状态">
                <el-tag
                  :type="proposalContent?.status === 'confirmed' ? 'success' : 'info'"
                  class="capsule-tag"
                >
                  {{ statusMap[proposalContent?.status || ''] || proposalContent?.status }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="总面价">
                <span class="price-text">¥{{ formatCNY(proposalContent?.total_face_value) }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <div class="content-section">
            <h3 class="section-heading">
              商品列表
              <span class="section-hint">点击商品行查看规格、材质与颜色等详细信息</span>
            </h3>
            <div class="table-responsive">
              <el-table
                :data="proposalContent?.items || []"
                border
                stripe
                class="share-table"
                row-class-name="share-table__row"
                @row-click="handleRowOpen"
              >
                <el-table-column
                  label="商品名称"
                >
                  <template #default="{ row }">
                    <div class="product-name-cell">
                      <div class="product-thumb">
                        <img
                          v-if="row.cover_image_url && !row._imgError"
                          :src="row.cover_image_url"
                          class="thumb-img"
                          @error="onImgError(row)"
                        >
                        <span
                          v-else
                          class="thumb-placeholder"
                        >{{ getPlaceholderText(row.product_name) }}</span>
                      </div>
                      <div class="product-info-text">
                        <span class="product-name-text">{{ row.product_name || '-' }}</span>
                        <span class="product-no-text">{{ row.product_no || '-' }}</span>
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column
                  label="面价"
                  align="right"
                >
                  <template #default="{ row }">
                    <span class="price-text">¥{{ formatCNY(row.face_price) }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="quantity"
                  label="数量"
                  width="80"
                  align="center"
                />
                <el-table-column
                  label="行合计"
                  align="right"
                >
                  <template #default="{ row }">
                    <span class="row-subtotal">¥{{ formatCNY(row.face_price ? row.face_price * row.quantity : 0) }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  label=""
                  width="96"
                  align="center"
                >
                  <template #default="{ row }">
                    <button
                      type="button"
                      class="row-detail-btn"
                      @click.stop="handleRowOpen(row)"
                    >
                      查看详情
                    </button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </template>

        <!-- Quotation content -->
        <template v-else-if="shareData.share_type === 'quotation'">
          <div class="content-section">
            <h3 class="section-heading">
              报价信息
            </h3>
            <el-descriptions
              :column="1"
              border
              class="info-descriptions"
            >
              <el-descriptions-item label="报价单号">
                <span class="mono-text">{{ quotationContent?.quotation_no || '-' }}</span>
              </el-descriptions-item>
              <el-descriptions-item label="状态">
                <el-tag
                  :type="quotationContent?.status === 'confirmed' ? 'success' : 'info'"
                  class="capsule-tag"
                >
                  {{ statusMap[quotationContent?.status || ''] || quotationContent?.status }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="总金额">
                <span class="total-amount">¥{{ formatCNY(quotationContent?.total_amount) }}</span>
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <div class="content-section">
            <h3 class="section-heading">
              商品明细
              <span class="section-hint">点击商品行查看规格、材质与颜色等详细信息</span>
            </h3>
            <div class="table-responsive">
              <el-table
                :data="quotationContent?.items || []"
                border
                stripe
                class="share-table"
                row-class-name="share-table__row"
                @row-click="handleRowOpen"
              >
                <el-table-column
                  label="商品名称"
                >
                  <template #default="{ row }">
                    <div class="product-name-cell">
                      <div class="product-thumb">
                        <img
                          v-if="row.cover_image_url && !row._imgError"
                          :src="row.cover_image_url"
                          class="thumb-img"
                          @error="onImgError(row)"
                        >
                        <span
                          v-else
                          class="thumb-placeholder"
                        >{{ getPlaceholderText(row.product_name) }}</span>
                      </div>
                      <div class="product-info-text">
                        <span class="product-name-text">{{ row.product_name || '-' }}</span>
                        <span class="product-no-text">{{ row.product_no || '-' }}</span>
                      </div>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column
                  label="面价"
                  align="right"
                >
                  <template #default="{ row }">
                    <span class="price-text">¥{{ formatCNY(row.face_price) }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  label="单价"
                  align="right"
                >
                  <template #default="{ row }">
                    <span class="price-text">¥{{ formatCNY(row.unit_price) }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  prop="quantity"
                  label="数量"
                  width="80"
                  align="center"
                />
                <el-table-column
                  label="税率"
                  align="center"
                >
                  <template #default="{ row }">
                    {{ row.tax_rate !== undefined ? (row.tax_rate * 100).toFixed(0) + '%' : '-' }}
                  </template>
                </el-table-column>
                <el-table-column
                  label="未税小计"
                  align="right"
                >
                  <template #default="{ row }">
                    <span class="subtotal-text">¥{{ formatCNY(row.subtotal) }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  label="含税小计"
                  align="right"
                >
                  <template #default="{ row }">
                    <span class="subtotal-text">¥{{ formatCNY(row.unit_price ? row.unit_price * row.quantity * (1 + (row.tax_rate ?? 0)) : 0) }}</span>
                  </template>
                </el-table-column>
                <el-table-column
                  label=""
                  width="96"
                  align="center"
                >
                  <template #default="{ row }">
                    <button
                      type="button"
                      class="row-detail-btn"
                      @click.stop="handleRowOpen(row)"
                    >
                      查看详情
                    </button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>
        </template>

        <div class="share-footer">
          <el-divider />
          <p class="footer-text">
            访问次数: <strong>{{ shareData.access_count }}</strong>
          </p>
          <p class="footer-brand">
            由 <strong>AI-PIM</strong> 提供技术支持
          </p>
        </div>
      </div>

      <!-- 商品详情弹窗：规格 / 材质 / 颜色 / 材质说明 / 场景图在点击后展开 -->
      <el-dialog
        v-model="detailVisible"
        :title="detailItem?.product_name || '商品详情'"
        append-to-body
        align-center
        width="640px"
        class="share-detail-dialog"
      >
        <template v-if="detailItem">
          <div class="detail-head">
            <div class="detail-thumb">
              <img
                v-if="detailItem.cover_image_url && !detailItem._imgError"
                :src="detailItem.cover_image_url"
                class="thumb-img"
                alt=""
                @error="onImgError(detailItem)"
              >
              <span
                v-else
                class="thumb-placeholder"
              >{{ getPlaceholderText(detailItem.product_name) }}</span>
            </div>
            <div class="detail-head__text">
              <span class="detail-name">{{ detailItem.product_name || '-' }}</span>
              <span class="detail-no">{{ detailItem.product_no || '-' }}</span>
              <div class="detail-tags">
                <el-tag
                  v-if="detailItem.category_name"
                  size="small"
                  class="capsule-tag"
                >
                  {{ detailItem.category_name }}
                </el-tag>
                <el-tag
                  v-if="detailLocation"
                  size="small"
                  type="warning"
                  class="capsule-tag"
                >
                  {{ detailLocation }}
                </el-tag>
              </div>
            </div>
          </div>

          <el-descriptions
            :column="1"
            border
            size="small"
            class="detail-descriptions"
          >
            <el-descriptions-item label="规格">
              {{ detailItem.specification || '未提供' }}
            </el-descriptions-item>
            <el-descriptions-item label="材质">
              {{ detailMaterial || '未提供' }}
            </el-descriptions-item>
            <el-descriptions-item label="颜色">
              {{ detailItem.colors || '未提供' }}
            </el-descriptions-item>
            <el-descriptions-item label="材质说明">
              {{ detailItem.material_desc || '未提供' }}
            </el-descriptions-item>
            <el-descriptions-item label="面价">
              <span class="price-text">¥{{ formatCNY(detailItem.face_price) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="数量">
              {{ detailItem.quantity }}
            </el-descriptions-item>
            <el-descriptions-item
              v-if="shareData.share_type === 'quotation'"
              label="单价"
            >
              <span class="price-text">¥{{ formatCNY(detailItem.unit_price) }}</span>
            </el-descriptions-item>
            <el-descriptions-item
              v-if="shareData.share_type === 'quotation'"
              label="税率"
            >
              {{ detailItem.tax_rate !== undefined && detailItem.tax_rate !== null ? (detailItem.tax_rate * 100).toFixed(0) + '%' : '-' }}
            </el-descriptions-item>
          </el-descriptions>

          <div
            v-if="detailItem.scene_images?.length"
            class="detail-scenes"
          >
            <div class="detail-scenes__title">
              场景图 {{ detailSceneCount }} 张，点击查看大图
            </div>
            <div class="detail-scenes__grid">
              <button
                v-for="(image, idx) in detailItem.scene_images.filter((s) => s.image_url)"
                :key="image.id"
                type="button"
                class="scene-cell"
                @click="openSceneCarousel(idx)"
              >
                <img
                  :src="image.image_url as string"
                  :alt="image.name || '场景图'"
                  loading="lazy"
                >
                <span class="scene-cell__name">{{ image.name || `场景图 ${idx + 1}` }}</span>
              </button>
            </div>
          </div>
          <p
            v-else
            class="detail-scenes__empty"
          >
            暂无场景图
          </p>
        </template>
        <template #footer>
          <el-button
            class="capsule-btn"
            @click="detailVisible = false"
          >
            关闭
          </el-button>
        </template>
      </el-dialog>

      <ProductSceneCarousel
        v-model="sceneCarouselVisible"
        :images="currentSceneImages"
        :initial-index="sceneCarouselIndex"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { shareApi } from '@/api'
import ProductSceneCarousel from '@/components/ProductSceneCarousel.vue'
import type { ShareContent, ShareProductItem, ShareProposalContent, ShareQuotationContent } from '@/types/sales'
import type { AxiosError } from 'axios'

const route = useRoute()
const token = route.params.token as string

const loading = ref(false)
const needPassword = ref(false)
const passwordInput = ref('')
const accessResult = ref('')
const errorMessage = ref('分享链接无效或已过期')

const shareData = reactive({
  share_type: '' as 'proposal' | 'quotation' | '',
  target_id: '',
  access_count: 0,
})

const proposalContent = ref<ShareProposalContent | null>(null)
const quotationContent = ref<ShareQuotationContent | null>(null)

const sceneCarouselVisible = ref(false)
const sceneCarouselIndex = ref(0)
const currentSceneImages = ref<Array<{ name?: string; image_url: string }>>([])

// 商品详情改为点击后的弹窗展示，明细表只保留摘要列
const detailVisible = ref(false)
const detailItem = ref<ShareProductItem | null>(null)

const statusMap: Record<string, string> = { draft: '草稿', confirmed: '已确认' }

const detailLocation = computed<string>(() => {
  const item = detailItem.value
  if (!item) return ''
  return [item.floor_label, item.space_label].filter(Boolean).join(' · ')
})

const detailMaterial = computed<string>(() => {
  const item = detailItem.value
  if (!item) return ''
  return item.material || item.material_description || ''
})

const detailSceneCount = computed<number>(() => {
  return (detailItem.value?.scene_images || []).filter((s) => Boolean(s.image_url)).length
})

const handleRowOpen = (row: ShareProductItem) => {
  detailItem.value = row
  detailVisible.value = true
}

const openSceneCarousel = (idx: number) => {
  const images = (detailItem.value?.scene_images || []).filter(
    (image): image is typeof image & { image_url: string } => Boolean(image.image_url),
  )
  currentSceneImages.value = images.map((image) => ({ name: image.name, image_url: image.image_url }))
  sceneCarouselIndex.value = idx
  sceneCarouselVisible.value = true
}

const getPlaceholderText = (name: string | undefined): string => {
  if (!name) return '无图'
  const match = name.match(/^[\u4e00-\u9fff]+/)
  if (match) {
    return match[0].slice(0, 2)
  }
  return name.slice(0, 4)
}

const onImgError = (row: ShareProductItem) => {
  row._imgError = true
}

// Format CNY with null/undefined fallback to '-'
const formatCNY = (value: number | null | undefined | string): string => {
  if (value === null || value === undefined || value === '') return '-'
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num) || num === null) return '-'
  return num.toFixed(2)
}

const fetchContent = async () => {
  loading.value = true
  try {
    const res = await shareApi.get(token, passwordInput.value || undefined) as { data?: { share_type: string; target_id: string; access_count: number; content: ShareContent } }
    const data = res.data
    if (!data) return
    shareData.share_type = data.share_type as 'proposal' | 'quotation'
    shareData.target_id = data.target_id
    shareData.access_count = data.access_count
    if (data.share_type === 'proposal') {
      proposalContent.value = data.content as ShareProposalContent
      quotationContent.value = null
    } else {
      quotationContent.value = data.content as ShareQuotationContent
      proposalContent.value = null
    }
    accessResult.value = 'success'
    needPassword.value = false
  } catch (error: unknown) {
    const e = error as AxiosError<{ detail?: { code?: number; msg?: string } }>
    const code = e.response?.data?.detail?.code
    const msg = e.response?.data?.detail?.msg
    if (code === 40304) {
      needPassword.value = true
      accessResult.value = 'denied_password'
      errorMessage.value = msg || '访问密码错误'
      ElMessage.error(errorMessage.value)
    } else {
      accessResult.value = 'denied'
      errorMessage.value = msg || '分享链接无效或已过期'
      ElMessage.error(errorMessage.value)
    }
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchContent()
})
</script>

<style scoped>
.share-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--pim-page);
  padding: 24px 16px 40px;
}

.share-brand-header {
  text-align: center;
  margin-bottom: 24px;
  padding: 20px 0 8px;
}

.brand-logo {
  font-size: 28px;
  font-weight: 700;
  color: rgb(var(--pim-brand));
  letter-spacing: 4px;
  margin-bottom: 4px;
}

.brand-subtitle {
  font-size: 13px;
  color: var(--pim-text-primary);
  letter-spacing: 2px;
  font-weight: 400;
}

.share-card {
  width: 100%;
  max-width: 800px;
  background: var(--pim-surface);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 32px;
  border: 1px solid var(--pim-surface-border);
  box-shadow: 0 8px 40px rgba(var(--pim-brand), 0.08);
  overflow: hidden;
}

.share-card :deep(.el-card__header) {
  background: rgba(var(--pim-brand), 0.04);
  border-bottom: 1px solid rgba(var(--pim-brand), 0.08);
  padding: 20px 24px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 20px;
  font-weight: 600;
  color: rgb(var(--pim-brand));
  letter-spacing: 0.5px;
}

.status-tag {
  border-radius: 20px;
}

.share-card :deep(.el-card__body) {
  padding: 24px;
}

.password-alert {
  border-radius: 16px;
  margin-bottom: 16px !important;
}

.password-input {
  margin-bottom: 16px;
  border-radius: 20px;
}

.password-input :deep(.el-input__wrapper) {
  border-radius: 20px;
}

.verify-btn {
  border-radius: 20px;
}

.error-alert {
  border-radius: 16px;
}

.share-content {
  margin-top: 8px;
}

.content-section {
  margin-bottom: 24px;
}

.content-section:last-of-type {
  margin-bottom: 0;
}

.section-heading {
  font-size: 16px;
  font-weight: 600;
  color: rgb(var(--pim-brand));
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid rgba(var(--pim-brand), 0.08);
}

.info-descriptions {
  border-radius: 16px;
  overflow: hidden;
}

.info-descriptions :deep(.el-descriptions__body) {
  border-radius: 16px;
}

.mono-text {
  font-family: monospace;
  font-size: 12px;
  color: var(--pim-text-primary);
}

.price-text {
  font-weight: 600;
  color: rgb(var(--pim-brand));
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.row-subtotal {
  font-family: monospace;
  color: rgb(var(--pim-brand));
  font-weight: 600;
}

.subtotal-text {
  font-family: monospace;
  color: rgb(var(--pim-brand));
  font-weight: 600;
}

.total-amount {
  font-size: 20px;
  font-weight: 700;
  color: rgb(var(--pim-brand));
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.capsule-tag {
  border-radius: 12px;
  padding: 2px 10px;
  font-weight: 500;
}

.table-responsive {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 12px;
}

.share-table {
  min-width: 600px;
  border-radius: 12px;
  overflow: hidden;
  cursor: pointer;
}

.section-hint {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 400;
  color: var(--pim-text-faint);
}

.row-detail-btn {
  padding: 2px 10px;
  border: 1px solid rgba(var(--pim-brand), 0.25);
  border-radius: 12px;
  background: transparent;
  color: rgb(var(--pim-brand));
  font-size: 12px;
  line-height: 1.6;
  cursor: pointer;
  transition: background 160ms ease, border-color 160ms ease;
}

.row-detail-btn:hover {
  background: rgba(var(--pim-brand), 0.08);
  border-color: rgba(var(--pim-brand), 0.45);
}

/* ===== 商品详情弹窗 ===== */
.share-detail-dialog :deep(.el-dialog) {
  border-radius: 24px;
  overflow: hidden;
}

.share-detail-dialog :deep(.el-dialog__header) {
  padding: 18px 22px 12px;
  border-bottom: 1px solid rgba(var(--pim-brand), 0.08);
}

.share-detail-dialog :deep(.el-dialog__title) {
  font-size: 17px;
  font-weight: 600;
  color: rgb(var(--pim-brand));
}

.share-detail-dialog :deep(.el-dialog__body) {
  padding: 18px 22px;
}

.share-detail-dialog :deep(.el-dialog__footer) {
  padding: 12px 22px 18px;
}

.detail-head {
  display: flex;
  gap: 14px;
  margin-bottom: 16px;
}

.detail-thumb {
  width: 72px;
  height: 72px;
  border-radius: 12px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--pim-media-bg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.detail-thumb .thumb-img {
  width: 72px;
  height: 72px;
}

.detail-head__text {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.detail-name {
  font-size: 16px;
  font-weight: 600;
  color: rgb(var(--pim-brand));
}

.detail-no {
  font-size: 12px;
  font-family: monospace;
  color: var(--pim-text-faint);
}

.detail-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.detail-descriptions {
  border-radius: 12px;
  overflow: hidden;
}

.detail-scenes {
  margin-top: 18px;
}

.detail-scenes__title {
  font-size: 13px;
  font-weight: 600;
  color: rgb(var(--pim-brand));
  margin-bottom: 10px;
}

.detail-scenes__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
}

.scene-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  border: 1px solid rgba(var(--pim-brand), 0.1);
  border-radius: 12px;
  overflow: hidden;
  background: var(--pim-surface);
  cursor: pointer;
  text-align: left;
}

.scene-cell img {
  width: 100%;
  height: 86px;
  object-fit: cover;
  display: block;
}

.scene-cell__name {
  padding: 0 8px 6px;
  font-size: 11px;
  color: var(--pim-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.detail-scenes__empty {
  margin: 16px 0 0;
  font-size: 12px;
  color: var(--pim-text-faint);
}

.share-footer {
  margin-top: 28px;
  text-align: center;
}

.footer-text {
  color: var(--pim-text-primary);
  font-size: 13px;
  margin: 0 0 4px 0;
}

.footer-brand {
  color: var(--pim-text-primary);
  font-size: 12px;
  margin: 0;
  opacity: 0.7;
}

/* Mobile optimizations */
@media (max-width: 768px) {
  .share-page {
    padding: 16px 8px 32px;
  }

  .share-brand-header {
    margin-bottom: 16px;
    padding-top: 12px;
  }

  .brand-logo {
    font-size: 24px;
    letter-spacing: 3px;
  }

  .brand-subtitle {
    font-size: 12px;
  }

  .share-card {
    border-radius: 24px;
    width: 95vw;
    max-width: 95vw;
  }

  .share-card :deep(.el-card__header) {
    padding: 16px;
  }

  .share-card :deep(.el-card__body) {
    padding: 16px;
  }

  .card-title {
    font-size: 18px;
  }

  .section-heading {
    font-size: 15px;
  }

  .content-section {
    margin-bottom: 20px;
  }

  .footer-text,
  .footer-brand {
    font-size: 11px;
  }
}

@media (max-width: 380px) {
  .brand-logo {
    font-size: 22px;
  }

  .share-card {
    border-radius: 20px;
  }
}

.product-name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.product-thumb {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--pim-media-bg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb-img {
  width: 48px;
  height: 48px;
  object-fit: cover;
  display: block;
}

.thumb-placeholder {
  font-size: 12px;
  font-weight: 600;
  color: var(--pim-text-faint);
  line-height: 1.2;
  text-align: center;
  word-break: keep-all;
}

.product-info-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.product-name-text {
  font-size: 14px;
  color: rgb(var(--pim-brand));
  line-height: 1.4;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.product-no-text {
  font-size: 11px;
  color: var(--pim-text-faint);
  font-family: monospace;
}
</style>
