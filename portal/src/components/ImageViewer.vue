<script lang="ts">
/**
 * 单张图片的通用描述。title 为条目主标题（如商品名/平面图名），
 * subtitle 为补充信息（如场景图名、楼层·空间），均可为空。
 */
export interface ImageViewerImage {
  url: string
  title?: string | null
  subtitle?: string | null
}
</script>

<script setup lang="ts">
/**
 * 通用全屏图片查看器（FR-1）。从 FloorPlanViewer 抽出，平面图与分享页商品
 * 画廊共用；调用方只传「url + 标题/副标题」列表，不感知业务字段。
 *
 * 用原生 <dialog> + showModal()：Esc 关闭与焦点陷阱由浏览器负责
 * （与 ShareDetailDialog 同口径），不引入任何弹层/轮播依赖。
 *
 * 交互：
 *   - 滚轮 / +- 按钮 / 双击缩放（0.5x ~ 5x），放大后可拖拽平移
 *   - 双指捏合缩放（平板）
 *   - 多张时左右方向键或两侧按钮切换，标题栏显示「N / M」
 *   - Esc / 关闭按钮 / 点遮罩（event.target === dialog）关闭
 *   - 打开期间给 body 加 image-viewer-open 锁住页面滚动
 *
 * 图片地址带时效（分享附件代理 token 15 分钟有效）：加载失败显示固定兜底
 * 文案，不自动重试、不重新请求分享内容（避免增加分享访问次数）；
 * 切换图片或重新打开时重置失败态。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    /** null = 关闭；空数组不打开；url 为空的项会被过滤。 */
    images: ImageViewerImage[] | null
    startIndex?: number
  }>(),
  { startIndex: 0 },
)

const emit = defineEmits<{ close: [] }>()

const MIN_SCALE = 0.5
const MAX_SCALE = 5

const dialogRef = ref<HTMLDialogElement | null>(null)
const index = ref(0)
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const dragging = ref(false)
/** 当前图片加载失败：显示兜底文案而不是坏掉的 <img>。 */
const failed = ref(false)

let dragStartX = 0
let dragStartY = 0
let dragOriginX = 0
let dragOriginY = 0
const pointers = new Map<number, { x: number; y: number }>()
let pinchStartDistance = 0
let pinchStartScale = 1

const usable = computed(() => (props.images || []).filter((image) => Boolean(image.url)))
const current = computed(() => usable.value[index.value] || null)

const title = computed(() => {
  const name = (current.value?.title || '').trim()
  return name || (usable.value.length ? `图片 ${index.value + 1}` : '图片')
})

const subtitle = computed(() => (current.value?.subtitle || '').trim())

function clampScale(value: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))
}

function applyScale(next: number) {
  scale.value = clampScale(next)
  if (scale.value <= 1) resetPan()
}

function zoomBy(delta: number) {
  applyScale(scale.value + delta)
}

function resetPan() {
  translateX.value = 0
  translateY.value = 0
}

function reset() {
  scale.value = 1
  resetPan()
}

function step(delta: number) {
  if (usable.value.length < 2) return
  const next = index.value + delta
  if (next < 0 || next >= usable.value.length) return
  index.value = next
  failed.value = false
  reset()
}

function close() {
  dialogRef.value?.close()
}

function onNativeClose() {
  document.body.classList.remove('image-viewer-open')
  emit('close')
}

/** 遮罩点击关闭：只有直接点在 dialog 本体上才关，点图片/工具按钮不关。 */
function onClick(event: MouseEvent) {
  if (event.target === dialogRef.value) close()
}

function onImageError() {
  failed.value = true
}

function onWheel(event: WheelEvent) {
  event.preventDefault()
  zoomBy(event.deltaY < 0 ? 0.2 : -0.2)
}

function onDoubleClick() {
  if (scale.value > 1) reset()
  else applyScale(2)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    step(-1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    step(1)
  } else if (event.key === '+' || event.key === '=') {
    event.preventDefault()
    zoomBy(0.25)
  } else if (event.key === '-') {
    event.preventDefault()
    zoomBy(-0.25)
  } else if (event.key === '0') {
    event.preventDefault()
    reset()
  }
}

function pointerDistance(): number {
  const points = [...pointers.values()]
  if (points.length < 2) return 0
  const [a, b] = points
  return Math.hypot(a.x - b.x, a.y - b.y)
}

function onPointerDown(event: PointerEvent) {
  const target = event.currentTarget as HTMLElement
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  try {
    target.setPointerCapture(event.pointerId)
  } catch {
    // 某些浏览器在 pointercancel 后拒绝捕获，忽略即可，不影响滚轮与按钮缩放
  }

  if (pointers.size === 2) {
    pinchStartDistance = pointerDistance()
    pinchStartScale = scale.value
    dragging.value = false
    return
  }
  if (pointers.size === 1 && scale.value > 1) {
    dragging.value = true
    dragStartX = event.clientX
    dragStartY = event.clientY
    dragOriginX = translateX.value
    dragOriginY = translateY.value
  }
}

function onPointerMove(event: PointerEvent) {
  if (!pointers.has(event.pointerId)) return
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })

  if (pointers.size === 2) {
    if (pinchStartDistance > 0) {
      applyScale((pinchStartScale * pointerDistance()) / pinchStartDistance)
    }
    return
  }

  if (!dragging.value) return
  translateX.value = dragOriginX + (event.clientX - dragStartX)
  translateY.value = dragOriginY + (event.clientY - dragStartY)
}

function onPointerUp(event: PointerEvent) {
  pointers.delete(event.pointerId)
  if (pointers.size < 2) pinchStartDistance = 0
  if (pointers.size === 0) dragging.value = false
}

watch(
  () => props.images,
  (value) => {
    const dialog = dialogRef.value
    if (!dialog) return
    failed.value = false
    if (!value || !value.length) {
      if (dialog.open) dialog.close()
      return
    }
    index.value = Math.min(Math.max(0, props.startIndex), value.length - 1)
    // startIndex 可能指向被过滤掉的空地址，夹到可用列表范围内
    index.value = Math.min(index.value, Math.max(0, usable.value.length - 1))
    reset()
    if (!dialog.open) {
      dialog.showModal()
      document.body.classList.add('image-viewer-open')
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.body.classList.remove('image-viewer-open')
  if (dialogRef.value?.open) dialogRef.value.close()
})
</script>

<template>
  <dialog
    ref="dialogRef"
    class="image-viewer"
    @close="onNativeClose"
    @keydown="onKeydown"
    @click="onClick"
  >
    <header class="image-viewer__header">
      <div class="image-viewer__heading">
        <h2>{{ title }}</h2>
        <p
          v-if="subtitle"
          class="image-viewer__subtitle"
        >
          {{ subtitle }}
        </p>
      </div>
      <div class="image-viewer__tools">
        <span
          v-if="usable.length > 1"
          class="image-viewer__counter"
        >{{ index + 1 }} / {{ usable.length }}</span>
        <button
          type="button"
          class="image-viewer__tool"
          aria-label="缩小"
          @click="zoomBy(-0.25)"
        >
          −
        </button>
        <span class="image-viewer__zoom">{{ Math.round(scale * 100) }}%</span>
        <button
          type="button"
          class="image-viewer__tool"
          aria-label="放大"
          @click="zoomBy(0.25)"
        >
          +
        </button>
        <button
          type="button"
          class="image-viewer__tool image-viewer__tool--text"
          @click="reset"
        >
          适应
        </button>
        <button
          type="button"
          class="image-viewer__tool"
          aria-label="关闭全屏"
          @click="close"
        >
          ✕
        </button>
      </div>
    </header>

    <div
      class="image-viewer__stage"
      :class="{ 'is-dragging': dragging, 'is-zoomed': scale > 1 }"
      @wheel="onWheel"
      @dblclick="onDoubleClick"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <img
        v-if="current && !failed"
        :src="current.url"
        :alt="title"
        draggable="false"
        :style="{
          transform: `translate(${translateX}px, ${translateY}px) scale(${scale})`,
        }"
        @error="onImageError"
      >
      <p
        v-else-if="failed"
        class="image-viewer__fallback"
      >图片已过期，请刷新页面查看</p>
    </div>

    <button
      v-if="usable.length > 1"
      type="button"
      class="image-viewer__nav image-viewer__nav--prev"
      aria-label="上一张"
      :disabled="index === 0"
      @click="step(-1)"
    >
      ‹
    </button>
    <button
      v-if="usable.length > 1"
      type="button"
      class="image-viewer__nav image-viewer__nav--next"
      aria-label="下一张"
      :disabled="index === usable.length - 1"
      @click="step(1)"
    >
      ›
    </button>

    <footer class="image-viewer__hint">
      <span>滚轮 / 双指缩放 · 放大后可拖拽 · ← → 切换</span>
      <span>Esc 关闭</span>
    </footer>
  </dialog>
</template>
