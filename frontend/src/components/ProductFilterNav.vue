<template>
  <div class="filter-nav">
    <div
      ref="tabsRef"
      class="filter-nav__tabs"
      role="tablist"
      aria-label="产品筛选维度"
    >
      <button
        v-for="tab in TABS"
        :key="tab.key"
        :ref="(el) => setTabRef(tab.key, el as HTMLElement | null)"
        type="button"
        role="tab"
        class="filter-nav__tab"
        :class="{ 'is-active': activeTab === tab.key }"
        :aria-selected="activeTab === tab.key"
        @click="switchTab(tab.key)"
      >
        {{ tab.label }}
      </button>
      <span
        class="filter-nav__indicator"
        :style="indicatorStyle"
        aria-hidden="true"
      />
    </div>

    <div class="filter-nav__row">
      <span class="filter-nav__row-label">{{ rowLabels.level2 }}</span>
      <div
        v-if="level2Loading"
        class="filter-nav__hint"
      >
        加载中…
      </div>
      <div
        v-else-if="level2Error"
        class="filter-nav__hint is-error"
      >
        {{ level2Error }}
        <button
          type="button"
          class="filter-nav__retry"
          @click="reload"
        >
          重试
        </button>
      </div>
      <div
        v-else-if="level2Options.length"
        class="filter-nav__chips"
        role="group"
        :aria-label="rowLabels.level2"
      >
        <button
          type="button"
          class="filter-chip"
          :class="{ 'is-active': !level2 }"
          @click="selectLevel2('')"
        >
          全部
        </button>
        <button
          v-for="option in level2Options"
          :key="option.value"
          type="button"
          class="filter-chip"
          :class="{ 'is-active': level2 === option.value }"
          @click="selectLevel2(option.value)"
        >
          {{ option.label }}
          <span class="filter-chip__count">{{ option.count }}</span>
        </button>
      </div>
      <div
        v-else
        class="filter-nav__hint"
      >
        暂无可选{{ rowLabels.level2 }}
      </div>
    </div>

    <div
      v-if="hasThirdLevel"
      class="filter-nav__row filter-nav__row--sub"
    >
      <span class="filter-nav__row-label">{{ rowLabels.level3 }}</span>
      <div
        v-if="level3Loading"
        class="filter-nav__hint"
      >
        加载中…
      </div>
      <div
        v-else-if="level3Options.length"
        class="filter-nav__chips filter-nav__chips--compact"
        role="group"
        :aria-label="rowLabels.level3"
      >
        <button
          type="button"
          class="filter-chip filter-chip--sub"
          :class="{ 'is-active': !level3 }"
          @click="selectLevel3('')"
        >
          全部
        </button>
        <button
          v-for="option in level3Options"
          :key="option.value"
          type="button"
          class="filter-chip filter-chip--sub"
          :class="{ 'is-active': level3 === option.value }"
          @click="selectLevel3(option.value)"
        >
          {{ option.label }}
          <span class="filter-chip__count">{{ option.count }}</span>
        </button>
      </div>
      <div
        v-else
        class="filter-nav__hint"
      >
        该{{ rowLabels.level2 }}下没有{{ rowLabels.level3 }}，直接按{{ rowLabels.level2 }}筛选即可
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 产品列表三级筛选导航：一级滑动标签 → 二级分类 → 三级标签。
 *
 * 所有选项都来自 /products/filter-options（产品表实时聚合），前端不写死任何
 * 分类、品牌、系列或规格；同一层级的重复值由后端 GROUP BY 去重。
 *
 * 维度之间的三级数据源互不相通：
 *   系列 → 分类 → 系列标签
 *   品牌 / 供应商 → 分类
 *   状态 / 库存 → 无三级
 *   品类 → 分类 → 规格长度（1800 / 2200 …）
 *
 * 组件只负责「选了什么」，把选择结果交给父页面映射成接口参数；
 * 切一级标签会清空二级/三级，避免带着上一个维度的条件继续查。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  productApi,
  type ProductFilterDimension,
  type ProductFilterOption,
} from '@/api'

interface ProductNavSelection {
  dimension: ProductFilterDimension
  level2: string
  level3: string
}

const TABS: Array<{ key: ProductFilterDimension; label: string }> = [
  { key: 'series', label: '系列' },
  { key: 'brand', label: '品牌' },
  { key: 'supplier', label: '供应商' },
  { key: 'status', label: '状态' },
  { key: 'stock', label: '库存' },
  { key: 'category', label: '品类' },
]

/** 各维度下二级/三级行的叫法，文案跟着维度走，避免「分类 → 分类」这种歧义。 */
const ROW_LABELS: Record<ProductFilterDimension, { level2: string; level3: string }> = {
  series: { level2: '分类', level3: '系列' },
  brand: { level2: '品牌', level3: '分类' },
  supplier: { level2: '供应商', level3: '分类' },
  status: { level2: '状态', level3: '' },
  stock: { level2: '库存', level3: '' },
  category: { level2: '品类', level3: '长度(mm)' },
}

const emit = defineEmits<{
  (event: 'change', selection: ProductNavSelection): void
}>()

const activeTab = ref<ProductFilterDimension>('series')
const level2 = ref('')
const level3 = ref('')
const level2Options = ref<ProductFilterOption[]>([])
const level3Options = ref<ProductFilterOption[]>([])
const level2Loading = ref(false)
const level3Loading = ref(false)
const level2Error = ref('')

const tabsRef = ref<HTMLElement | null>(null)
const tabEls: Partial<Record<ProductFilterDimension, HTMLElement>> = {}
const indicator = reactive({ x: 0, y: 0, width: 0 })

const rowLabels = computed(() => ROW_LABELS[activeTab.value])
const THIRD_LEVEL_DIMENSIONS = new Set<ProductFilterDimension>([
  'series',
  'brand',
  'supplier',
  'category',
])
const hasThirdLevel = computed(() => THIRD_LEVEL_DIMENSIONS.has(activeTab.value))
const indicatorStyle = computed(() => ({
  transform: `translate(${indicator.x}px, ${indicator.y}px)`,
  width: `${indicator.width}px`,
}))

let requestToken = 0

function setTabRef(key: ProductFilterDimension, el: HTMLElement | null) {
  if (el) tabEls[key] = el
}

function syncIndicator() {
  const el = tabEls[activeTab.value]
  if (!el) return
  indicator.x = el.offsetLeft
  indicator.y = el.offsetTop + el.offsetHeight - 2
  indicator.width = el.offsetWidth
}

async function loadLevel2(dimension: ProductFilterDimension) {
  const token = ++requestToken
  level2Loading.value = true
  level2Error.value = ''
  level2Options.value = []
  level3Options.value = []
  try {
    const res = await productApi.filterOptions({ dimension })
    if (token !== requestToken) return
    level2Options.value = res.data?.items ?? []
  } catch {
    if (token !== requestToken) return
    level2Options.value = []
    level2Error.value = '筛选项加载失败'
  } finally {
    if (token === requestToken) level2Loading.value = false
  }
}

async function loadLevel3(dimension: ProductFilterDimension, parentId: string) {
  if (!parentId || !THIRD_LEVEL_DIMENSIONS.has(dimension)) {
    level3Options.value = []
    return
  }
  const token = ++requestToken
  level3Loading.value = true
  level3Options.value = []
  try {
    const res = await productApi.filterOptions({ dimension, parent_id: parentId })
    if (token !== requestToken) return
    level3Options.value = res.data?.items ?? []
  } catch {
    if (token !== requestToken) return
    level3Options.value = []
  } finally {
    if (token === requestToken) level3Loading.value = false
  }
}

function emitChange() {
  emit('change', {
    dimension: activeTab.value,
    level2: level2.value,
    level3: level3.value,
  })
}

function switchTab(next: ProductFilterDimension) {
  if (next === activeTab.value) return
  activeTab.value = next
  level2.value = ''
  level3.value = ''
  loadLevel2(next)
  emitChange()
}

function selectLevel2(value: string) {
  level2.value = value
  level3.value = ''
  loadLevel3(activeTab.value, value)
  emitChange()
}

function selectLevel3(value: string) {
  level3.value = value
  emitChange()
}

function reload() {
  loadLevel2(activeTab.value)
}

function reset() {
  activeTab.value = 'series'
  level2.value = ''
  level3.value = ''
  loadLevel2('series')
  emitChange()
}

defineExpose({ reset })

watch(activeTab, () => nextTick(syncIndicator))

onMounted(() => {
  loadLevel2(activeTab.value)
  nextTick(syncIndicator)
  window.addEventListener('resize', syncIndicator)
})

onBeforeUnmount(() => window.removeEventListener('resize', syncIndicator))
</script>

<style scoped>
.filter-nav {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 2px 0 14px;
  margin-bottom: 14px;
  border-bottom: 1px solid var(--pim-line);
}

/* ===== 一级：滑动指示标签 ===== */
.filter-nav__tabs {
  position: relative;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 26px;
}

.filter-nav__tab {
  position: relative;
  padding: 6px 2px 10px;
  border: 0;
  background: transparent;
  color: var(--pim-text-soft);
  font-size: 14px;
  font-weight: 500;
  line-height: 1.4;
  cursor: pointer;
  transition: color 180ms ease;
}

.filter-nav__tab:hover {
  color: var(--pim-text-primary);
}

.filter-nav__tab.is-active {
  color: var(--pim-text-strong);
  font-weight: 600;
}

.filter-nav__indicator {
  position: absolute;
  top: 0;
  left: 0;
  height: 2px;
  border-radius: 2px;
  background: var(--pim-accent-solid);
  transition: transform 260ms cubic-bezier(0.4, 0, 0.2, 1), width 260ms cubic-bezier(0.4, 0, 0.2, 1);
  pointer-events: none;
}

/* ===== 二级 / 三级 ===== */
.filter-nav__row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-height: 26px;
}

.filter-nav__row--sub {
  padding-top: 2px;
}

.filter-nav__row-label {
  flex: none;
  width: 38px;
  padding-top: 5px;
  color: var(--pim-text-faint);
  font-size: 12px;
  line-height: 1.5;
}

.filter-nav__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px 14px;
  /* 高度取整行数（4×30 + 3×8 = 144px）：再多就滚动，且不会露出半行被截断的胶囊。 */
  max-height: 144px;
  overflow-y: auto;
  scrollbar-gutter: stable;
  scrollbar-width: thin;
  padding-right: 4px;
}

.filter-nav__chips::-webkit-scrollbar {
  width: 6px;
}

.filter-nav__chips::-webkit-scrollbar-thumb {
  border-radius: 3px;
  background: var(--pim-line-strong);
}

.filter-nav__chips::-webkit-scrollbar-track {
  background: transparent;
}

.filter-nav__chips--compact {
  /* 3×28 + 2×8 = 100px */
  max-height: 100px;
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 2px;
  border: 0;
  background: transparent;
  color: var(--pim-text-primary);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  border-radius: 8px;
  transition: color 160ms ease, background-color 160ms ease;
}

.filter-chip:hover {
  color: var(--pim-accent-ink);
  background: rgba(var(--pim-brand), 0.05);
}

.filter-chip.is-active {
  padding: 0 10px;
  background: var(--pim-accent-solid);
  color: var(--pim-on-accent);
  font-weight: 600;
}

.filter-chip--sub {
  height: 28px;
  font-size: 12.5px;
}

.filter-chip__count {
  font-size: 11px;
  opacity: 0.62;
  font-variant-numeric: tabular-nums;
}

.filter-nav__hint {
  padding-top: 5px;
  color: var(--pim-text-faint);
  font-size: 12.5px;
}

.filter-nav__hint.is-error {
  color: var(--pim-danger, #c45656);
}

.filter-nav__retry {
  margin-left: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--pim-accent-ink);
  font-size: 12.5px;
  text-decoration: underline;
  cursor: pointer;
}

@media (max-width: 720px) {
  .filter-nav__tabs {
    gap: 4px 18px;
  }

  .filter-nav__row {
    flex-direction: column;
    gap: 4px;
  }

  .filter-nav__row-label {
    width: auto;
    padding-top: 0;
  }
}
</style>
