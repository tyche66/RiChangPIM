<template>
  <div
    class="proposal-item-editor"
    :class="{ 'proposal-item-editor--compact': compact, 'proposal-item-editor--page': page }"
  >
    <div class="product-picker">
      <el-select
        v-model="pendingProductId"
        placeholder="搜索商品名称 / 编号"
        filterable
        remote
        :remote-show-suffix="true"
        :loading="searchLoading"
        :remote-method="handleRemoteSearch"
        class="capsule-select full-width product-picker__select"
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
            <span class="option-price">{{ formatMoney(p.face_price) }}</span>
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
      <el-button
        class="capsule-btn"
        title="跳转到产品列表，可按分类/品牌等筛选后多选，选完点「完成」返回"
        @click="$emit('pick-from-list')"
      >
        从产品列表选择
      </el-button>
      <el-button
        class="capsule-btn"
        title="自定义产品不入产品库，仅在本方案中对外展示"
        @click="customOpen = true"
      >
        添加自定义产品
      </el-button>
    </div>

    <div
      v-if="items.length"
      class="items-groups"
    >
      <el-collapse
        v-model="openGroups"
        class="items-collapse"
      >
        <el-collapse-item
          v-for="group in itemGroups"
          :key="group.key"
          :name="group.key"
        >
          <template #title>
            <span class="group-title">{{ group.label }}</span>
            <span class="group-count">{{ groupCount(group.key) }} 项</span>
          </template>
          <div class="group-cards">
            <el-card
              v-for="item in groupItems(group.key)"
              :key="itemKey(item)"
              class="item-card glass-card"
            >
              <div class="item-card-header">
                <div class="item-product-info">
                  <img
                    v-if="item.cover_image_url"
                    :src="item.cover_image_url"
                    class="item-cover"
                    @error="onCoverError"
                  >
                  <div class="item-name-no">
                    <span class="item-name">
                      {{ item.is_custom ? (item.custom_product?.name || '自定义产品') : (item.display_name || item.product_name || '-') }}
                    </span>
                    <span
                      v-if="item.is_custom"
                      class="item-no"
                    >自定义产品</span>
                    <template v-else>
                      <span class="item-no">{{ item.product_no || '-' }}</span>
                      <span
                        v-if="item.display_name && item.product_name && item.product_name !== item.display_name"
                        class="item-original-name"
                        :title="item.product_name"
                      >原名：{{ item.product_name }}</span>
                    </template>
                  </div>
                  <div class="item-meta">
                    <span class="item-face-price">面价 {{ formatMoney(item.is_custom ? item.custom_product?.face_price : item.face_price) }}</span>
                    <span class="item-stock">
                      {{ item.is_custom ? '仅本方案展示' : `库存状态 ${item.stock_status || '-'}` }}
                    </span>
                  </div>
                </div>
                <el-button
                  type="danger"
                  link
                  class="item-remove"
                  @click="removeItem(item)"
                >
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
              <div class="item-fields">
                <div class="item-field">
                  <label>数量</label>
                  <el-input-number
                    :model-value="item.quantity"
                    :min="1"
                    :step="1"
                    :precision="0"
                    controls-position="right"
                    class="capsule-number"
                    @update:model-value="updateQuantity(item, $event)"
                  />
                </div>
                <div class="item-field">
                  <label>备注</label>
                  <el-input
                    :model-value="item.remark ?? ''"
                    placeholder="备注（可选）"
                    clearable
                    class="capsule-input"
                    @update:model-value="updateRemark(item, $event)"
                  />
                </div>
                <div class="item-field">
                  <label>楼层名称</label>
                  <el-input
                    :model-value="item.floor_label ?? ''"
                    placeholder="请输入楼层名称（可选）"
                    clearable
                    class="capsule-input"
                    @update:model-value="(val: string) => updateLocation(item, 'floor_label', val)"
                    @blur="commitGroupKey(item)"
                  />
                </div>
                <div class="item-field">
                  <label>空间名称</label>
                  <el-input
                    :model-value="item.space_label ?? ''"
                    placeholder="请输入空间名称（可选）"
                    clearable
                    class="capsule-input"
                    @update:model-value="(val: string) => updateLocation(item, 'space_label', val)"
                    @blur="commitGroupKey(item)"
                  />
                </div>
                <div
                  v-if="item.project_space_id"
                  class="item-space-id"
                  :title="`已绑定项目空间 ID：${item.project_space_id}`"
                >
                  已绑定空间 ID：{{ item.project_space_id }}
                </div>
                <div
                  v-if="!item.is_custom"
                  class="item-field"
                >
                  <label>方案内名称</label>
                  <el-input
                    :model-value="item.display_name ?? ''"
                    placeholder="方案中展示的名称，留空用产品名"
                    clearable
                    class="capsule-input"
                    @update:model-value="updateDisplayName(item, $event)"
                  />
                </div>
                <div
                  v-if="item.is_custom"
                  class="item-field item-field--wide"
                >
                  <label>自定义产品字段</label>
                  <el-button
                    link
                    type="primary"
                    class="custom-edit-btn"
                    @click="editCustom(item)"
                  >
                    编辑名称 / 面价 / 图片 / 规格 / 材质 / 颜色 / 材质说明
                  </el-button>
                </div>
                <div class="item-field item-field--wide">
                  <label>材质说明</label>
                  <el-input
                    :model-value="item.material_desc ?? ''"
                    type="textarea"
                    :rows="2"
                    resize="none"
                    placeholder="该明细的材质说明（可选）"
                    clearable
                    class="capsule-input"
                    @update:model-value="updateMaterialDesc(item, $event)"
                  />
                </div>
              </div>
            </el-card>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <div
      v-else
      class="items-empty"
    >
      <el-empty
        description="暂未添加商品"
        :image-size="80"
      />
    </div>

    <el-dialog
      v-model="customOpen"
      :title="customEditIndex >= 0 ? '编辑自定义产品' : '添加自定义产品'"
      width="560px"
      class="custom-dialog"
    >
      <el-form
        ref="customFormRef"
        :model="customForm"
        :rules="customRules"
        label-position="top"
        class="custom-form"
      >
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item
              label="名称 *"
              prop="name"
            >
              <el-input
                v-model="customForm.name"
                placeholder="自定义产品名称"
                maxlength="255"
                class="capsule-input"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="面价">
              <el-input-number
                v-model="customForm.face_price"
                :min="0"
                :precision="2"
                controls-position="right"
                class="capsule-number custom-price"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="图片（可选，随方案随用随删）">
          <div class="custom-upload">
            <img
              v-if="customForm.image_url"
              :src="customForm.image_url"
              class="custom-upload__preview"
              @error="onCoverError"
            >
            <el-button
              size="small"
              class="capsule-btn"
              :loading="customUploading"
              @click="customFileInput?.click()"
            >
              {{ customForm.image_url ? '更换图片' : '上传图片' }}
            </el-button>
            <el-button
              v-if="customForm.image_url"
              size="small"
              class="capsule-btn"
              @click="clearCustomImage"
            >
              移除图片
            </el-button>
          </div>
          <input
            ref="customFileInput"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            class="custom-file-input"
            @change="onCustomFilePicked"
          >
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="规格">
              <el-input
                v-model="customForm.specification"
                placeholder="如 1200×600×750mm"
                maxlength="255"
                class="capsule-input"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="材质">
              <el-input
                v-model="customForm.material"
                placeholder="如 红橡木"
                maxlength="128"
                class="capsule-input"
              />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="颜色">
          <el-input
            v-model="customForm.colors"
            placeholder="如 原木色 / 胡桃色"
            maxlength="512"
            class="capsule-input"
          />
        </el-form-item>
        <el-form-item label="材质说明">
          <el-input
            v-model="customForm.material_description"
            type="textarea"
            :rows="3"
            resize="none"
            maxlength="2048"
            placeholder="自定义产品的材质说明"
            class="capsule-input"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button
          class="capsule-btn"
          @click="customOpen = false"
        >
          取消
        </el-button>
        <el-button
          type="primary"
          class="capsule-btn capsule-btn-primary"
          :disabled="customSaving"
          @click="saveCustom"
        >
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { productApi } from '@/api'
import { mediaApi } from '@/api/media'
import { formatMoney } from '@/utils/money'
import type { ProposalCustomProduct, ProposalItem, ProductOption } from '@/types/sales'
import { Close } from '@element-plus/icons-vue'

interface Props {
  modelValue?: ProposalItem[]
  /** 紧凑模式：字段排成两列网格，适合放在较窄的弹窗里 */
  compact?: boolean
  /**
   * 页面级模式（FR-2）：用在全宽编辑页。去掉内部滚动（页面自然滚动）、
   * 商品搜索固定在明细区顶部、字段栅格按视口宽度走 4/2/1 列三档。
   */
  page?: boolean
}

interface Emits {
  (e: 'update:modelValue', value: ProposalItem[]): void
  (e: 'change', value: ProposalItem[]): void
  (e: 'pick-from-list'): void
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: () => [],
  compact: false,
  page: false,
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

// ---------------------------------------------------------------------------
// 楼层/空间折叠分组：与分享页分组同口径，产品多时按位置收纳，减少上下滑动。
//
// 分组归属用 groupKeys（itemKey → 分组键）单独保存，只在输入框失焦时更新：
// 若直接按 floor_label/space_label 实时分组，正在输入这两个字段时每敲一个字
// 卡片就会换组、输入框被重新挂载而丢失焦点，表现为「打不进字」。
// ---------------------------------------------------------------------------

const openGroups = ref<string[]>([])
const groupKeys = ref<Record<string, string>>({})

interface ItemGroup {
  key: string
  label: string
}

function currentGroupKey(item: ProposalItem): string {
  return `${(item.floor_label || '').trim()}||${(item.space_label || '').trim()}`
}

function groupKeyOf(item: ProposalItem): string {
  return groupKeys.value[itemKey(item)] ?? currentGroupKey(item)
}

const itemGroups = computed<ItemGroup[]>(() => {
  const map = new Map<string, ItemGroup>()
  for (const item of props.modelValue) {
    const key = groupKeyOf(item)
    if (!map.has(key)) {
      const [floor, space] = key.split('||')
      map.set(key, {
        key,
        label: [floor, space].filter(Boolean).join(' / ') || '未指定位置',
      })
    }
  }
  return [...map.values()]
})

function groupItems(key: string): ProposalItem[] {
  return props.modelValue.filter((item) => groupKeyOf(item) === key)
}

function groupCount(key: string): number {
  return groupItems(key).length
}

/** 失焦后才把卡片移到新的楼层/空间分组，避免输入过程中重挂载。 */
function commitGroupKey(item: ProposalItem) {
  const key = itemKey(item)
  const next = currentGroupKey(item)
  if (groupKeys.value[key] === next) return
  groupKeys.value = { ...groupKeys.value, [key]: next }
}

// 新条目登记初始分组；分组变化/default 全部展开，避免折叠后看不到条目
watch(
  () => props.modelValue.map((item) => itemKey(item)).join('|'),
  () => {
    const next = { ...groupKeys.value }
    let changed = false
    for (const item of props.modelValue) {
      const key = itemKey(item)
      if (!(key in next)) {
        next[key] = currentGroupKey(item)
        changed = true
      }
    }
    if (changed) groupKeys.value = next
  },
  { immediate: true },
)

watch(
  itemGroups,
  (groups) => {
    const missing = groups.map((g) => g.key).filter((k) => !openGroups.value.includes(k))
    if (missing.length) openGroups.value = [...new Set([...openGroups.value, ...missing])]
  },
  { immediate: true },
)

function itemKey(item: ProposalItem): string {
  return item._key
    || item.id
    || `${item.product_id || 'custom'}-${item.quantity}-${item.display_name || ''}`.slice(0, 64)
}

let uid = 0
function nextUid(): string {
  uid += 1
  return `draft-${Date.now()}-${uid}`
}

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
  if (items.value.some((i) => !i.is_custom && i.product_id === pid)) return
  const opt = findProductOption(pid)
  items.value = [...items.value, {
    _key: nextUid(),
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

const removeItem = (target: ProposalItem) => {
  items.value = items.value.filter((item) => item !== target)
}

const updateItemField = (target: ProposalItem, field: keyof ProposalItem, value: unknown) => {
  items.value = items.value.map((item) => (item === target ? { ...item, [field]: value } : item))
}

const updateQuantity = (target: ProposalItem, val: number | null) => {
  updateItemField(target, 'quantity', Math.max(1, Math.round(val ?? 1)))
}

const updateRemark = (target: ProposalItem, val: string) => {
  updateItemField(target, 'remark', val)
}

const updateDisplayName = (target: ProposalItem, val: string) => {
  updateItemField(target, 'display_name', val.trim() || null)
}

// ---------------------------------------------------------------------------
// Track C：自由输入空间标签与材质说明
// ---------------------------------------------------------------------------

function updateLocation(target: ProposalItem, field: 'floor_label' | 'space_label', val: string) {
  // 只做一次数组更新：连续两次 emit 时，第二次读到的 props.modelValue 还是
  // 旧值（Vue props 更新是异步的），会把刚输入的内容覆盖回去，表现为打不进字。
  items.value = items.value.map((item) =>
    item === target
      ? {
          ...item,
          [field]: val.trim() || undefined,
          // Typed labels are authoritative; an old compatibility ID must not
          // survive a manual location edit or a cleared label.
          project_space_id: undefined,
        }
      : item,
  )
}

function updateMaterialDesc(target: ProposalItem, val: string) {
  updateItemField(target, 'material_desc', val || undefined)
}

const onCoverError = (e: Event) => {
  const img = e.target as HTMLImageElement
  if (img) img.style.display = 'none'
}

// ---------------------------------------------------------------------------
// 自定义产品（不入产品库）：名称/面价/图片/规格/材质/颜色/材质说明自由填写
// ---------------------------------------------------------------------------

interface CustomFormModel {
  name: string
  face_price: number | null
  attachment_id: string | null
  image_url: string | null
  specification: string
  material: string
  colors: string
  material_description: string
}

const customOpen = ref(false)
const customSaving = ref(false)
const customUploading = ref(false)
/** >=0 表示编辑已有自定义产品；-1 表示新增 */
const customEditIndex = ref(-1)
const customFormRef = ref<FormInstance>()
const customFileInput = ref<HTMLInputElement>()

const customForm = reactive<CustomFormModel>({
  name: '',
  face_price: null,
  attachment_id: null,
  image_url: null,
  specification: '',
  material: '',
  colors: '',
  material_description: '',
})

const customRules: FormRules = {
  name: [{ required: true, message: '请输入自定义产品名称', trigger: 'blur' }],
}

function editCustom(target: ProposalItem) {
  customEditIndex.value = items.value.indexOf(target)
  const cp: ProposalCustomProduct = target.custom_product || {
    name: '',
    face_price: null,
    attachment_id: null,
    specification: null,
    material: null,
    colors: null,
    material_description: null,
  }
  customForm.name = cp.name || ''
  customForm.face_price = cp.face_price ?? null
  customForm.attachment_id = cp.attachment_id || null
  customForm.image_url = target.cover_image_url || null
  customForm.specification = cp.specification || ''
  customForm.material = cp.material || ''
  customForm.colors = cp.colors || ''
  customForm.material_description = cp.material_description || ''
  customOpen.value = true
}

async function onCustomFilePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ElMessage.warning('仅支持图片文件')
    return
  }
  customUploading.value = true
  try {
    const media = await mediaApi.upload(file)
    customForm.attachment_id = media.id
    customForm.image_url = media.url
  } catch {
    // 统一错误提示由 axios 拦截器给出
  } finally {
    customUploading.value = false
  }
}

function clearCustomImage() {
  customForm.attachment_id = null
  customForm.image_url = null
}

async function saveCustom() {
  if (customSaving.value) return
  if (customFormRef.value) {
    const valid = await customFormRef.value.validate().catch(() => false)
    if (!valid) return
  }
  const name = customForm.name.trim()
  if (!name) {
    ElMessage.warning('请输入自定义产品名称')
    return
  }

  const customProduct: ProposalCustomProduct = {
    name,
    face_price: customForm.face_price ?? null,
    attachment_id: customForm.attachment_id,
    specification: customForm.specification.trim() || null,
    material: customForm.material.trim() || null,
    colors: customForm.colors.trim() || null,
    material_description: customForm.material_description.trim() || null,
  }

  customSaving.value = true
  try {
    if (customEditIndex.value >= 0) {
      const item = items.value[customEditIndex.value]
      if (item) {
        items.value = items.value.map((it, i) =>
          i === customEditIndex.value
            ? {
                ...it,
                is_custom: true,
                custom_product: customProduct,
                product_name: name,
                face_price: customProduct.face_price,
                cover_image_url: customForm.image_url || undefined,
              }
            : it,
        )
      }
    } else {
      items.value = [...items.value, {
        _key: nextUid(),
        product_id: null,
        is_custom: true,
        custom_product: customProduct,
        quantity: 1,
        remark: undefined,
        product_name: name,
        product_no: undefined,
        face_price: customProduct.face_price,
        cover_image_url: customForm.image_url || undefined,
      }]
    }
    customOpen.value = false
  } finally {
    customSaving.value = false
  }
}
</script>

<style scoped>
.proposal-item-editor {
  --brand-deep: var(--pim-text-strong);
  --brand-primary: var(--pim-text-strong);
  --brand-light: rgba(var(--pim-brand), 0.08);
  --brand-lighter: rgba(var(--pim-brand), 0.04);
  --text-primary: var(--pim-text-primary);
  --text-secondary: var(--pim-text-secondary);
  --radius-sm: 12px;
  --transition-fast: 200ms cubic-bezier(0.4, 0, 0.2, 1);
}

.full-width {
  width: 100%;
}

/* 商品搜索 + 添加按钮：同一行、按钮不被挤压 */
.product-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.product-picker__select {
  flex: 1;
  min-width: 200px;
}

.product-picker > .capsule-btn {
  flex-shrink: 0;
  margin-left: 0;
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

/* 楼层/空间分组折叠 */
.items-groups {
  margin-top: 12px;
}

.items-collapse {
  border: none;
  width: 100%;
}

.items-collapse :deep(.el-collapse-item__header) {
  background: transparent;
  border-bottom: 1px solid rgba(var(--pim-brand), 0.08);
  height: auto;
  padding: 8px 4px;
  line-height: 1.4;
  font-weight: 600;
  color: var(--brand-deep);
}

.items-collapse :deep(.el-collapse-item__wrap) {
  background: transparent;
  border-bottom: none;
}

.group-title {
  font-size: 14px;
}

.group-count {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 400;
  color: var(--text-secondary);
}

.group-cards {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 0 4px;
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
  border: 1px solid rgba(var(--pim-brand), 0.08) !important;
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

.item-original-name {
  font-size: 12px;
  color: var(--text-faint, var(--pim-text-faint));
  font-style: normal;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.item-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.item-face-price {
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

/*
 * 明细字段网格：数量/备注/楼层/空间各占一列，材质说明跨整行。
 */
.item-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
  margin-top: 10px;
}

.item-field--wide {
  grid-column: 1 / -1;
}

.item-location-body {
  align-items: flex-start;
}

.item-space-id {
  width: 100%;
  color: var(--text-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}

.item-field {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  min-width: 0;
}

.item-field label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  flex-shrink: 0;
}

/* 网格布局下输入框撑满所在列 */
.item-fields .item-field :deep(.el-input),
.item-fields .item-field :deep(.el-input-number),
.item-fields .item-field :deep(.el-textarea) {
  width: 100%;
}

.custom-edit-btn {
  justify-content: flex-start;
  padding: 0;
  font-size: 12px;
}

/* 紧凑模式：缩小的明细卡片间距，避免弹窗里出现双层滚动条 */
.proposal-item-editor--compact .group-cards {
  max-height: 46vh;
  overflow-y: auto;
  gap: 10px;
}

.proposal-item-editor--compact .item-card :deep(.el-card__body) {
  padding: 12px 14px;
}

.proposal-item-editor--compact .item-cover {
  width: 40px;
  height: 40px;
}

/*
 * 页面级模式（FR-2）：全宽编辑页。去掉内部滚动（页面自然滚动）、
 * 商品搜索固定在明细区顶部（sticky）、字段栅格 ≥1200px 四列。
 */
.proposal-item-editor--page .group-cards {
  gap: 12px;
}

.proposal-item-editor--page .product-picker {
  position: sticky;
  top: 0;
  z-index: 5;
  padding: 10px 0;
  margin: -10px 0 2px;
  background: var(--pim-overlay);
  border-radius: var(--radius-sm);
}

.proposal-item-editor--page .item-fields {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.proposal-item-editor--page .item-space-id {
  grid-column: 1 / -1;
}

@media (max-width: 1199px) {
  .proposal-item-editor--page .item-fields {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 767px) {
  .proposal-item-editor--page .item-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}

/* Capsule styling */
.capsule-input :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(var(--pim-brand), 0.1) inset;
  padding: 4px 16px;
}

.capsule-select :deep(.el-select__wrapper),
.capsule-select :deep(.el-input__wrapper) {
  border-radius: 20px;
  box-shadow: 0 0 0 1px rgba(var(--pim-brand), 0.1) inset;
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

/* 自定义产品弹窗 */
.custom-form {
  width: 100%;
}

.custom-upload {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.custom-upload__preview {
  width: 72px;
  height: 72px;
  border-radius: 10px;
  object-fit: cover;
  background: var(--brand-lighter);
  border: 1px solid rgba(var(--pim-brand), 0.1);
}

.custom-file-input {
  display: none;
}

.custom-price {
  width: 100%;
}

.custom-price :deep(.el-input-number) {
  width: 100%;
}

.items-empty {
  margin-top: 16px;
}

/* Mobile responsive */
@media (max-width: 768px) {
  .product-picker {
    flex-direction: column;
    align-items: stretch;
  }

  .product-picker__select {
    width: 100% !important;
    max-width: none;
  }

  .item-card-body {
    flex-direction: column;
  }

  .item-fields {
    grid-template-columns: minmax(0, 1fr);
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