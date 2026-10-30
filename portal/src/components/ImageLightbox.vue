<script setup lang="ts">
/**
 * 极简图片灯箱：门户没有引入组件库，比较表的主图放大只需要一层遮罩。
 *
 * 键盘与无障碍：Esc 关闭、遮罩点击关闭、关闭按钮可聚焦；
 * 打开期间锁住 body 滚动，避免背景跟着滑。
 */
import { onBeforeUnmount, onMounted, watch } from 'vue'

const props = defineProps<{
  open: boolean
  images: string[]
  index: number
}>()

const emit = defineEmits<{
  (event: 'close'): void
}>()

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close')
}

watch(
  () => props.open,
  (open) => {
    document.body.style.overflow = open ? 'hidden' : ''
  },
)

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <div
    v-if="open && images.length"
    class="image-lightbox"
    role="dialog"
    aria-modal="true"
    aria-label="产品图片预览"
    @click.self="emit('close')"
  >
    <button
      type="button"
      class="image-lightbox__close"
      aria-label="关闭预览"
      @click="emit('close')"
    >
      ×
    </button>
    <img
      class="image-lightbox__img"
      :src="images[Math.min(index, images.length - 1)]"
      alt=""
    >
  </div>
</template>
