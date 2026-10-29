<script setup lang="ts">
/**
 * 平面图全屏查看器。
 *
 * 用原生 <dialog> + showModal()：赞助商/客户浏览器不需要额外的弹层库，
 * Esc 关闭与焦点陷阱由浏览器负责（与 ShareSceneDialog / ShareDetailDialog 同口径）。
 *
 * 交互：
 *   - 滚轮 / +- 按钮 / 双击缩放（0.5x ~ 5x），放大后可拖拽平移
 *   - 双指捏合缩放（平板）
 *   - 多张时左右方向键或两侧按钮切换，标题栏显示「第 N / M 张」
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { ShareFloorPlan } from '@/api'

const props = withDefaults(
  defineProps<{
    /** null = 关闭；非空数组 = 打开。 */
    images: ShareFloorPlan[] | null
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

let dragStartX = 0
let dragStartY = 0
let dragOriginX = 0
let dragOriginY = 0
const pointers = new Map<number, { x: number; y: number }>()
let pinchStartDistance = 0
let pinchStartScale = 1

const usable = computed(() => (props.images || []).filter((image) => Boolean(image.image_url)))
const current = computed(() => usable.value[index.value] || null)

const title = computed(() => {
  const name = (current.value?.name || '').trim()
  return name || (usable.value.length ? `平面图 ${index.value + 1}` : '平面图')
})

/** 位置信息只在后台填了楼层/空间时显示，不在前台编造。 */
const subtitle = computed(() => {
  const image = current.value
  if (!image) return ''
  return [image.floor_label, image.space_label].filter(Boolean).join(' · ')
})

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
  reset()
}

function close() {
  dialogRef.value?.close()
}

function onNativeClose() {
  document.body.classList.remove('plan-viewer-open')
  emit('close')
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
      document.body.classList.add('plan-viewer-open')
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  document.body.classList.remove('plan-viewer-open')
  if (dialogRef.value?.open) dialogRef.value.close()
})
</script>

<template>
  <dialog
    ref="dialogRef"
    class="plan-viewer"
    @close="onNativeClose"
    @keydown="onKeydown"
  >
    <header class="plan-viewer__header">
      <div class="plan-viewer__heading">
        <h2>{{ title }}</h2>
        <p
          v-if="subtitle"
          class="plan-viewer__subtitle"
        >
          {{ subtitle }}
        </p>
      </div>
      <div class="plan-viewer__tools">
        <span
          v-if="usable.length > 1"
          class="plan-viewer__counter"
        >{{ index + 1 }} / {{ usable.length }}</span>
        <button
          type="button"
          class="plan-viewer__tool"
          aria-label="缩小"
          @click="zoomBy(-0.25)"
        >
          −
        </button>
        <span class="plan-viewer__zoom">{{ Math.round(scale * 100) }}%</span>
        <button
          type="button"
          class="plan-viewer__tool"
          aria-label="放大"
          @click="zoomBy(0.25)"
        >
          +
        </button>
        <button
          type="button"
          class="plan-viewer__tool plan-viewer__tool--text"
          @click="reset"
        >
          适应
        </button>
        <button
          type="button"
          class="plan-viewer__tool"
          aria-label="关闭全屏"
          @click="close"
        >
          ✕
        </button>
      </div>
    </header>

    <div
      class="plan-viewer__stage"
      :class="{ 'is-dragging': dragging, 'is-zoomed': scale > 1 }"
      @wheel="onWheel"
      @dblclick="onDoubleClick"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <img
        v-if="current"
        :src="current.image_url as string"
        :alt="title"
        draggable="false"
        :style="{
          transform: `translate(${translateX}px, ${translateY}px) scale(${scale})`,
        }"
      >
    </div>

    <button
      v-if="usable.length > 1"
      type="button"
      class="plan-viewer__nav plan-viewer__nav--prev"
      aria-label="上一张"
      :disabled="index === 0"
      @click="step(-1)"
    >
      ‹
    </button>
    <button
      v-if="usable.length > 1"
      type="button"
      class="plan-viewer__nav plan-viewer__nav--next"
      aria-label="下一张"
      :disabled="index === usable.length - 1"
      @click="step(1)"
    >
      ›
    </button>

    <footer class="plan-viewer__hint">
      <span>滚轮 / 双指缩放 · 放大后可拖拽 · ← → 切换</span>
      <span>Esc 关闭</span>
    </footer>
  </dialog>
</template>
