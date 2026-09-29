<script setup lang="ts">
/**
 * 首屏产品卡堆。视觉对齐参考页：中间一张最靠前，左右各两张依次向后错位，
 * 每张卡有固定的位移、旋转角、层级和投影；hover 只做「抬升 + 放大 + 阴影
 * 加深」，旋转角保留在外层卡位上（卡片不会转正）。
 *
 * 与旧版的区别（排错要点）：
 * 1. **永远不再退回普通栅格**。旧版在结果数超过卡位数时切换成
 *    `.product-grid`，20 条结果就是一整页没有层级的平铺网格（截图 1 的
 *    问题）。现在无论多少条结果都走叠卡，同屏最多 5 张。
 * 2. 结果超过 5 张时用 `windowStart` 做窗口轮换：滚轮只在卡堆容器内
 *    preventDefault，页面主体不跟滚；支持连续循环，鼠标移出卡堆后页面
 *    恢复正常滚动。键盘上下/左右、以及窄屏下的前后按钮共用同一套轮换。
 * 3. 卡片 key 用「数据索引 + 业务 ID」，轮换时同一张卡始终绑定同一条产
 *    品数据，图片、标题、价格不会错位。
 * 4. 状态显式区分：查询中（loading）→ 骨架卡；查过但没产品（empty）→
 *    空状态卡；没有推荐数据（placeholder）→ 空白占位卡。三者不会混。
 */
import { computed, onBeforeUnmount, ref, watch, type CSSProperties } from 'vue'
import ProductCard from './ProductCard.vue'

/** 卡堆的展示状态。data 两种数据来源（结果 / 推荐）+ 三种无数据状态。 */
type DeckVariant = 'result' | 'recommend' | 'loading' | 'empty' | 'placeholder'

type DeckSlot = {
  /** 相对中心的水平位移（px） */
  x: number
  /** 相对中心的垂直位移（px），让卡堆有高低错落 */
  y: number
  /** 旋转角（deg） */
  rotate: number
  /** 入场时的起始水平位移（px），方向与 x 相反，卡片从中间「发牌」出去 */
  enterX: number
  z: number
  /** 入场延迟（ms），同一环的两张卡同时进场 */
  delay: number
}

/** 同屏最多 5 张：中间一张 + 左右各两张。 */
const MAX_SLOTS = 5

const SLOTS: DeckSlot[] = [
  { x: 0, y: -10, rotate: 0, enterX: 0, z: 6, delay: 40 },
  { x: -170, y: -22, rotate: -3, enterX: 88, z: 5, delay: 150 },
  { x: 170, y: -20, rotate: 3, enterX: -88, z: 5, delay: 150 },
  { x: -340, y: 6, rotate: -6, enterX: 150, z: 4, delay: 260 },
  { x: 340, y: 8, rotate: 6, enterX: -150, z: 4, delay: 260 },
]

/**
 * 张数 → 卡位。卡位表是「中间一张 + 左右交替向外」的顺序，偶数张时跳过
 * 中间那张，剩下的正好左右成对，卡堆才是对称的（否则两张卡会变成
 * 「中间 + 左边」，整堆偏向一侧）。
 */
const SLOT_ORDER: Record<number, number[]> = {
  1: [0],
  2: [1, 2],
  3: [0, 1, 2],
  4: [1, 2, 3, 4],
  5: [0, 1, 2, 3, 4],
}

type CardKind = 'product' | 'placeholder' | 'loading' | 'empty'
type DeckCard = { key: string; kind: CardKind; product?: Record<string, unknown>; index: number }

const props = withDefaults(
  defineProps<{
    products: Array<Record<string, unknown>>
    detailUrl: (product: Record<string, unknown>) => string
    /** 数据来源。切换来源时整堆卡重新发一次牌。 */
    variant: DeckVariant
    label: string
    /** 没有任何产品时铺几张空白卡，撑住首屏的构图。 */
    placeholderCount?: number
  }>(),
  { placeholderCount: MAX_SLOTS },
)

const total = computed(() => props.products.length)
const placeholders = computed(() =>
  props.products.length ? 0 : Math.min(Math.max(props.placeholderCount, 0), MAX_SLOTS),
)
/** 只有超过 5 张产品结果才需要轮换。 */
const rotatable = computed(() => props.variant === 'result' && total.value > MAX_SLOTS)
const windowStart = ref(0)

/**
 * 换一次查询就回到第一张。既要盯结果数变化，也要盯 products 数组本身——
 * 「12 条 → 12 条」这种同数量的重查不会改变 length，只换引用。
 */
watch(
  () => props.products,
  () => {
    windowStart.value = 0
  },
)

const slotOrder = computed<number[]>(() => SLOT_ORDER[Math.min(total.value, MAX_SLOTS)] || [])

/** 当前可见的产品：带上「数据索引」，轮换时产品与卡位一对一绑定。 */
const visible = computed<DeckCard[]>(() => {
  const count = Math.min(total.value, MAX_SLOTS)
  const out: DeckCard[] = []
  if (!total.value) return out
  const start = ((windowStart.value % total.value) + total.value) % total.value
  for (let offset = 0; offset < count; offset += 1) {
    const index = (start + offset) % total.value
    const product = props.products[index]
    out.push({
      key: `${props.variant}-${index}-${String(product.id || product.product_no || 'na')}`,
      kind: 'product',
      product,
      index,
    })
  }
  return out
})

/** 一次渲染出来的全部卡位内容，TransitionGroup 只面对这一个列表。 */
const cards = computed<DeckCard[]>(() => {
  if (props.variant === 'loading') {
    return Array.from({ length: MAX_SLOTS }, (_, i) => ({ key: `loading-${i}`, kind: 'loading', index: i }))
  }
  if (props.variant === 'empty') {
    return [{ key: 'empty-0', kind: 'empty', index: 0 }]
  }
  if (props.variant === 'placeholder') {
    return Array.from({ length: placeholders.value }, (_, i) => ({
      key: `placeholder-${i}`,
      kind: 'placeholder',
      index: i,
    }))
  }
  return visible.value
})

/** 轮换指示里的「2-6 / 12」。 */
const rangeText = computed(() => {
  if (!total.value) return ''
  if (!rotatable.value) return `${total.value} / ${total.value}`
  const start = (((windowStart.value % total.value) + total.value) % total.value) + 1
  const end = Math.min(start + MAX_SLOTS - 1, total.value)
  return `${start}-${end} / ${total.value}`
})

function step(delta: number) {
  if (!rotatable.value || !total.value) return
  windowStart.value = (((windowStart.value + delta) % total.value) + total.value) % total.value
}

/**
 * 滚轮只在卡堆容器内生效。监听是手动挂的 non-passive，preventDefault 才
 * 真的拦得住页面滚动（passive 监听下 preventDefault 无效还会打警告）。
 */
let wheelEl: HTMLElement | null = null
let wheelLock = 0
const WHEEL_COOLDOWN = 220

function onWheel(event: WheelEvent) {
  if (!rotatable.value) return
  event.preventDefault()
  const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX
  if (!delta) return
  // 一次手势只翻一张，避免触控板惯性连跳
  const now = performance.now()
  if (now < wheelLock) return
  wheelLock = now + WHEEL_COOLDOWN
  step(delta > 0 ? 1 : -1)
}

/** 键盘：卡堆获得焦点后用方向键轮换，鼠标用户用滚轮，两条路共用 step()。 */
function onKeydown(event: KeyboardEvent) {
  if (!rotatable.value) return
  switch (event.key) {
    case 'ArrowDown':
    case 'ArrowRight':
    case 'PageDown':
      event.preventDefault()
      step(1)
      break
    case 'ArrowUp':
    case 'ArrowLeft':
    case 'PageUp':
      event.preventDefault()
      step(-1)
      break
    default:
      break
  }
}

type RefTarget = Element | { $el?: Element } | null

function attachWheel(el: RefTarget) {
  // 函数 ref：挂载时拿到 DOM，卸载时 Vue 会用 null 再调一次，这里顺手摘监听。
  detachWheel()
  const node =
    el instanceof HTMLElement ? el : el && '$el' in el && el.$el instanceof HTMLElement ? el.$el : null
  wheelEl = node
  wheelEl?.addEventListener('wheel', onWheel, { passive: false })
}
function detachWheel() {
  wheelEl?.removeEventListener('wheel', onWheel)
  wheelEl = null
}
onBeforeUnmount(detachWheel)

function slotStyle(position: number): CSSProperties | undefined {
  const slot = SLOTS[slotOrder.value[position]]
  if (!slot) return undefined
  return {
    '--deck-x': `${slot.x}px`,
    '--deck-y': `${slot.y}px`,
    '--deck-rot': `${slot.rotate}deg`,
    '--deck-enter-x': `${slot.enterX}px`,
    '--deck-z': String(slot.z),
    '--deck-delay': `${slot.delay}ms`,
  }
}
</script>

<template>
  <section
    :ref="attachWheel"
    class="hero-deck hero-deck--fan"
    :class="{ 'hero-deck--rotatable': rotatable }"
    role="group"
    :tabindex="rotatable ? 0 : -1"
    :aria-label="label"
    @keydown="onKeydown"
  >
    <TransitionGroup tag="div" name="deck" class="hero-deck__track card-list">
      <div
        v-for="(card, position) in cards"
        :key="card.key"
        class="hero-deck__slot"
        :style="slotStyle(position)"
        :data-index="card.kind === 'product' ? card.index : undefined"
      >
        <ProductCard
          v-if="card.kind === 'product' && card.product"
          :product="card.product"
          :detail-url="detailUrl(card.product)"
        />
        <span v-else-if="card.kind === 'loading'" class="product-card product-card--loading">
          <span class="spinner" aria-hidden="true" />
          <span class="product-card--loading__text">正在检索产品</span>
        </span>
        <span
          v-else
          class="product-card product-card--empty"
          :class="{ 'product-card--empty--noresult': card.kind === 'empty' }"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <circle cx="8.5" cy="9.5" r="1.6" />
            <path d="M4 17l5-5 3.5 3.5L15 13l5 5" />
          </svg>
          <template v-if="card.kind === 'empty'">
            <span>本次查询没有返回产品</span>
            <span class="product-card--empty__hint">换个型号、场景或材质再试一次</span>
          </template>
          <template v-else>
            <span>产品位</span>
          </template>
        </span>
      </div>
    </TransitionGroup>

    <p v-if="rotatable" class="hero-deck__nav" aria-live="polite">
      <button type="button" class="hero-deck__nav-btn" aria-label="上一组产品" @click="step(-1)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M15 6l-6 6l6 6" />
        </svg>
      </button>
      <span class="hero-deck__nav-count">{{ rangeText }}</span>
      <button type="button" class="hero-deck__nav-btn" aria-label="下一组产品" @click="step(1)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M9 6l6 6l-6 6" />
        </svg>
      </button>
      <span class="hero-deck__nav-hint">滚轮翻页</span>
    </p>
  </section>
</template>
