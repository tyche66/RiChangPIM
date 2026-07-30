<script setup lang="ts">
/**
 * 首屏产品卡堆。视觉与动效对齐 reeoo.com 首页的扇形卡片组：
 * 中间一张最靠前，之后左右交替向外展开，每一环有固定的位移、旋转角
 * 和入场延迟；hover 只做「抬升 + 放大 + 阴影加深」，旋转角保留在
 * 外层卡位上（参考页就是这么处理的，卡片不会转正）。
 *
 * 两个约定：
 * 1. 容器沿用 `.card-list`。整个门户只有两个 `.card-list`——第一个是产品区、
 *    第二个是来源区，e2e 用序号定位（tests/e2e/portal.spec.ts），
 *    所以产品卡不能再另开一个列表容器。
 * 2. 卡片数超过卡位数就退回常规产品栅格，宁可不扇形也不能丢数据。
 */
import { computed, type CSSProperties } from 'vue'
import ProductCard from './ProductCard.vue'

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

const SLOTS: DeckSlot[] = [
  { x: 0, y: -10, rotate: 0, enterX: 0, z: 5, delay: 40 },
  { x: -168, y: -30, rotate: -3, enterX: 96, z: 4, delay: 150 },
  { x: 168, y: -27, rotate: 3, enterX: -96, z: 4, delay: 150 },
  { x: -336, y: 10, rotate: -6, enterX: 164, z: 3, delay: 260 },
  { x: 336, y: 13, rotate: 6, enterX: -164, z: 3, delay: 260 },
  { x: -490, y: -30, rotate: -9, enterX: 236, z: 2, delay: 370 },
  { x: 490, y: -33, rotate: 9, enterX: -236, z: 2, delay: 370 },
  { x: -630, y: 13, rotate: -11, enterX: 300, z: 1, delay: 480 },
  { x: 630, y: 10, rotate: 11, enterX: -300, z: 1, delay: 480 },
]

const props = withDefaults(
  defineProps<{
    products: Array<Record<string, unknown>>
    detailUrl: (product: Record<string, unknown>) => string
    /** 数据来源。切换来源时 key 变化，整堆卡会重新发一次牌。 */
    variant: 'result' | 'recommend' | 'placeholder'
    label: string
    /** 没有任何产品时铺几张空白卡，撑住首屏的构图（参考页本身也有空白卡）。 */
    placeholderCount?: number
  }>(),
  { placeholderCount: 5 },
)

const fanned = computed(() => props.products.length <= SLOTS.length)
const placeholders = computed(() =>
  props.products.length ? 0 : Math.min(Math.max(props.placeholderCount, 0), SLOTS.length),
)
/**
 * 真正用到的卡位。卡位表是「中间一张 + 左右交替向外」的顺序，
 * 张数为偶数时跳过中间那一张，剩下的正好左右成对，卡堆才是对称的
 * （否则两张卡会变成「中间 + 左边」，整堆偏向一侧）。
 */
const usedSlots = computed<DeckSlot[]>(() => {
  const count = props.products.length || placeholders.value
  if (!count || count > SLOTS.length) return []
  return count % 2 === 0 ? SLOTS.slice(1, count + 1) : SLOTS.slice(0, count)
})

function slotStyle(index: number): CSSProperties | undefined {
  const slot = usedSlots.value[index]
  if (!fanned.value || !slot) return undefined
  return {
    '--deck-x': `${slot.x}px`,
    '--deck-y': `${slot.y}px`,
    '--deck-rot': `${slot.rotate}deg`,
    '--deck-enter-x': `${slot.enterX}px`,
    '--deck-z': String(slot.z),
    '--deck-delay': `${slot.delay}ms`,
  }
}

function productKey(product: Record<string, unknown>, index: number): string {
  return `${props.variant}-${String(product.id || product.product_no || index)}`
}
</script>

<template>
  <TransitionGroup
    tag="section"
    name="deck"
    class="card-list hero-deck"
    :class="fanned ? 'hero-deck--fan' : 'hero-deck--grid product-grid'"
    :aria-label="label"
  >
    <div
      v-for="(product, index) in products"
      :key="productKey(product, index)"
      class="hero-deck__slot"
      :style="slotStyle(index)"
    >
      <ProductCard :product="product" :detail-url="detailUrl(product)" />
    </div>
    <div
      v-for="index in placeholders"
      :key="`placeholder-${index}`"
      class="hero-deck__slot"
      :style="slotStyle(index - 1)"
      aria-hidden="true"
    >
      <span class="product-card product-card--empty" />
    </div>
  </TransitionGroup>
</template>
