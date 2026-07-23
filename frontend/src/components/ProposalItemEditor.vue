<template>
  <div class="proposal-item-editor">
    <el-select
      v-model="pendingProductId"
      placeholder="搜索商品名称 / 编号"
      filterable
      remote
      :remote-show-suffix="true"
      :loading="searchLoading"
      :remote-method="handleRemoteSearch"
      class="capsule-select full-width"
      style="width: 100%"
    >
      <el-option
        v-for="p in productOptions"
        :key="p.id"
        :label="`${p.product_name}（${p.product_no}）`"
        :value="p.id"
      >
        <div class="option-info">
          <span class="option-name">{{ p.product_name }}</span>
          <span class="option-no">{{ p.product_no }}</span>
          <span class="option-price">¥{{ p.face_price?.toFixed(2) ?? '-' }}</span>
           <span class="option-stock">库存状态 {{ p.stock_status || '-' }}</span>
        </div>
      </el-option>
    </el-select>

    <el-button
      type="primary"
      :disabled="!pendingProductId"
      class="capsule-btn capsule-btn-primary"
      @click="addItem"
    >
      添加商品
    </el-button>

    <div v-if="items.length" class="items-list">
      <el-card
        v-for="(item, idx) in items"
        :key="idx"
        class="item-card glass-card"
      >
        <div class="item-card-header">
          <div class="item-product-info">
            <img
              v-if="item.cover_image_url"
              :src="item.cover_image_url"
              class="item-cover"
              @error="onCoverError"
            />
            <div class="item-name-no">
              <span class="item-name">{{ item.product_name || '-' }}</span>
              <span class="item-no">{{ item.product_no || '-' }}</span>
            </div>
            <div class="item-meta">
              <span class="item-face-price">面价 ¥{{ item.face_price?.toFixed(2) ?? '-' }}</span>
               <span class="item-stock">库存状态 {{ item.stock_status || '-' }}</span>
            </div>
          </div>
          <el-button
            type="danger"
            link
            class="item-remove"
            @click="removeItem(idx)"
          >
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
        <div class="item-card-body">
          <div class="item-field">
            <label>数量</label>
            <el-input-number
              :model-value="item.quantity"
              :min="1"
              :step="1"
              :precision="0"
              controls-position="right"
              class="capsule-number"
              @update:model-value="updateQuantity(idx, $event)"
            />
          </div>
          <div class="item-field">
            <label>备注</label>
            <el-input
              :model-value="item.remark ?? ''"
              placeholder="备注（可选）"
              clearable
              class="capsule-input"
              @update:model-value="updateRemark(idx, $event)"
            />
          </div>
        </div>
      </el-card>
    </div>

    <div v-else class="items-empty">
      <el-empty description="暂未添加商品" :image-size="80" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { productApi } from '@/api'
import type { ProposalItem, ProductOption } from '@/types/sales'
import { Close } from '@element-plus/icons-vue'

interface Props {
  modelValue?: ProposalItem[]
}

interface Emits {
  (e: 'update:modelValue', value: ProposalItem[]): void
  (e: 'change', value: ProposalItem[]): void
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
})

const emit = defineEmits<Emits>()

const productOptions = ref<ProductOption[]>([])
const searchLoading = ref(false)
const pendingProductId = ref('')

let searchTimer: ReturnType<typeof setTimeout> | null = null

const items = computed({
  get: () => props.modelValue,
  set: (val: ProposalItem[]) => {
    emit('update:modelValue', val)
    emit('change', val)
  },
})

const handleRemoteSearch = (query: string) => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    if (query.trim()) {
      fetchProducts(query.trim())
    } else {
      productOptions.value = []
    }
  }, 300)
}

const fetchProducts = async (kw: string) => {
  searchLoading.value = true
  try {
    const res = await productApi.list({ keyword: kw, status: 'active', page: 1, size: 50 })
    productOptions.value = res.data.list.filter((p) => p.status === 'active').map((p) => ({
      id: p.id,
      product_name: p.product_name,
      product_no: p.product_no,
      face_price: p.face_price,
      stock_status: p.stock_status ?? null,
      cover_image_url: p.cover_image_url,
    }))
  } catch {
    productOptions.value = []
  } finally {
    searchLoading.value = false
  }
}

const findProductOption = (pid: string): ProductOption | undefined =>
  productOptions.value.find((p) => p.id === pid)

const addItem = () => {
  const pid = pendingProductId.value
  if (!pid) return
  // Deduplicate: skip if already selected
  if (items.value.some((i) => i.product_id === pid)) return
  const opt = findProductOption(pid)
  items.value = [...items.value, {
    product_id: pid,
    quantity: 1,
    remark: undefined,
    product_name: opt?.product_name,
    product_no: opt?.product_no,
    face_price: opt?.face_price,
    stock_status: opt?.stock_status,
    cover_image_url: opt?.cover_image_url,
  }]
  pendingProductId.value = ''
  productOptions.value = []
}

const removeItem = (idx: number) => {
  items.value = items.value.filter((_, i) => i !== idx)
}

const updateItemField = (idx: number, field: keyof ProposalItem, value: unknown) => {
  items.value = items.value.map((item, i) => {
    if (i !== idx) return item
    return { ...item, [field]: value }
  })
}

const updateQuantity = (idx: number, val: number | null) => {
  updateItemField(idx, 'quantity', Math.max(1, Math.round(val ?? 1)))
}

const updateRemark = (idx: number, val: string) => {
  updateItemField(idx, 'remark', val)
}

const onCoverError = (e: Event) => {
  const img = e.target as HTMLImageElement
  if (img) img.style.display = 'none'
}

</script>

<style scoped>
.proposal-item-editor {
  --brand-deep: rgba(30, 50, 90, 0.92);
  --brand-primary: rgba(30, 50, 90, 0.85);
  --brand-light: rgba(30, 50, 90, 0.08);
  --brand-lighter: rgba(30, 50, 90, 0.04);
  --text-primary: #5E6470;
  --text-secondary: rgba(30, 50, 90, 0.6);
  --radius-sm: 12px;
  --transition-fast: 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.full-width {
  width: 100%;
}

/* Option display inside select dropdown */
.option-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
}

.option-name {
  font-weight: 600;
  color: var(--brand-deep);
}

.option-no {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: monospace;
}

.option-price,
.option-stock {
  font-size: 12px;
  color: var(--text-secondary);
}

/* Items list */
.items-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
}

.item-card {
  border-radius: var(--radius-sm) !important;
  box-shadow: none !important;
  border: 1px solid rgba(30, 50, 90, 0.08) !important;
}

.item-card :deep(.el-card__body) {
  padding: 12px 14px;
}

.item-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.item-product-info {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.item-cover {
  width: 44px;
  height: 44px;
  border-radius: 8px;
  object-fit: cover;
  background: var(--brand-lighter);
  flex-shrink: 0;
}

.item-name-no {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.item-name {
  font-weight: 600;
  color: var(--brand-deep);
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-no {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: monospace;
}

.item-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.item-face-price {
  margin-right: 12px;
  color: var(--brand-deep);
}

.item-remove {
  flex-shrink: 0;
}

.item-card-body {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.item-field {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 140px;
}

.item-field label {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
  flex-shrink: 0;
}

/* Capsule styling */
.capsule-input :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.1) inset;
  padding: 4px 16px;
}

.capsule-select :deep(.el-select__wrapper),
.capsule-select :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(30, 50, 90, 0.1) inset;
  padding: 4px 16px;
}

.capsule-number :deep(.el-input__wrapper) {
  border-radius: 20px;
}

.capsule-btn {
  border-radius: 20px !important;
  padding: 8px 20px;
  font-weight: 500;
  transition: var(--transition-fast);
}

.capsule-btn:hover {
  transform: scale(1.03);
}

.capsule-btn:active {
  transform: scale(0.97);
}

.capsule-btn-primary {
  background: var(--brand-primary);
  border-color: var(--brand-primary);
}

.capsule-btn-primary:hover {
  background: var(--brand-deep);
  border-color: var(--brand-deep);
}

.items-empty {
  margin-top: 16px;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .item-card-body {
    flex-direction: column;
  }

  .item-field {
    min-width: 0;
    width: 100%;
  }

  .item-card-header {
    flex-direction: column;
  }

  .item-meta {
    flex-direction: column;
    gap: 2px;
  }

  .item-face-price {
    margin-right: 0;
  }
}
</style>
