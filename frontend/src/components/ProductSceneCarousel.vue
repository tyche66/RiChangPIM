<template>
  <Transition name="carousel-fade">
    <div
      v-if="modelValue"
      class="scene-overlay"
      @click.self="close"
    >
      <div class="scene-container">
        <button
          class="scene-close"
          type="button"
          @click="close"
        >
          <el-icon><Close /></el-icon>
        </button>

        <div
          v-if="currentImage?.name"
          class="scene-name"
        >
          {{ currentImage.name }}
        </div>

        <div
          class="scene-image-wrapper"
          @touchstart="onTouchStart"
          @touchend="onTouchEnd"
        >
          <img
            :key="currentIndex"
            :src="currentImage?.image_url"
            :alt="currentImage?.name || '场景图'"
            class="scene-image"
          >
        </div>

        <button
          v-if="images.length > 1"
          class="nav-btn nav-prev"
          type="button"
          @click="prev"
        >
          <el-icon><ArrowLeft /></el-icon>
        </button>
        <button
          v-if="images.length > 1"
          class="nav-btn nav-next"
          type="button"
          @click="next"
        >
          <el-icon><ArrowRight /></el-icon>
        </button>

        <div class="scene-counter">
          {{ currentIndex + 1 }} / {{ images.length }}
        </div>

        <div
          v-if="images.length > 1"
          class="scene-dots"
        >
          <span
            v-for="(_, i) in images"
            :key="i"
            class="dot"
            :class="{ active: i === currentIndex }"
            @click="currentIndex = i"
          />
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import { Close, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'

export interface SceneImage {
  name?: string
  image_url: string
  [key: string]: unknown
}

const props = withDefaults(defineProps<{
  modelValue: boolean
  images: SceneImage[]
  initialIndex?: number
}>(), {
  initialIndex: 0,
})

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
  (e: 'close'): void
}>()

const currentIndex = ref(props.initialIndex)

const currentImage = computed(() => props.images[currentIndex.value])

const close = () => {
  emit('update:modelValue', false)
  emit('close')
}

const prev = () => {
  if (currentIndex.value > 0) {
    currentIndex.value--
  } else {
    currentIndex.value = props.images.length - 1
  }
}

const next = () => {
  if (currentIndex.value < props.images.length - 1) {
    currentIndex.value++
  } else {
    currentIndex.value = 0
  }
}

let touchStartX = 0
const onTouchStart = (e: TouchEvent) => {
  touchStartX = e.touches[0].clientX
}
const onTouchEnd = (e: TouchEvent) => {
  const diff = touchStartX - e.changedTouches[0].clientX
  if (Math.abs(diff) > 50) {
    if (diff > 0) next()
    else prev()
  }
}

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape') close()
  if (e.key === 'ArrowLeft') prev()
  if (e.key === 'ArrowRight') next()
}

watch(() => props.modelValue, (val) => {
  if (val) {
    currentIndex.value = props.initialIndex
    document.addEventListener('keydown', handleKeydown)
  } else {
    document.removeEventListener('keydown', handleKeydown)
  }
}, { immediate: false })

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.scene-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(0, 0, 0, 0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  backdrop-filter: blur(4px);
}

.scene-container {
  position: relative;
  background: #fff;
  border-radius: 16px;
  padding: 20px;
  width: 90vw;
  max-width: 800px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.scene-close {
  position: absolute;
  top: 8px;
  right: 8px;
  z-index: 10;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.06);
  color: #333;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  transition: background 0.2s;
}

.scene-close:hover {
  background: rgba(0, 0, 0, 0.12);
}

.scene-name {
  font-size: 14px;
  font-weight: 600;
  color: rgb(30, 50, 90);
  margin-bottom: 12px;
  text-align: center;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0 40px;
}

.scene-image-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  max-height: 65vh;
  width: 100%;
  overflow: hidden;
  border-radius: 8px;
  background: #f5f5f5;
  touch-action: pan-y;
}

.scene-image {
  max-width: 100%;
  max-height: 65vh;
  object-fit: contain;
  display: block;
  user-select: none;
  -webkit-user-drag: none;
}

.nav-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 10;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.9);
  color: #333;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  transition: all 0.2s;
}

.nav-btn:hover {
  background: #fff;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}

.nav-prev {
  left: 12px;
}

.nav-next {
  right: 12px;
}

.scene-counter {
  font-size: 14px;
  color: #888;
  margin-top: 12px;
  font-weight: 500;
}

.scene-dots {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d0d0d0;
  cursor: pointer;
  transition: background 0.2s, transform 0.2s;
}

.dot.active {
  background: rgb(30, 50, 90);
  transform: scale(1.3);
}

.carousel-fade-enter-active,
.carousel-fade-leave-active {
  transition: opacity 0.25s ease;
}

.carousel-fade-enter-from,
.carousel-fade-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {
  .scene-container {
    width: 100vw;
    max-width: 100vw;
    height: 100vh;
    max-height: 100vh;
    border-radius: 0;
    padding: 16px;
    justify-content: center;
  }

  .scene-image-wrapper {
    max-height: 70vh;
  }

  .scene-image {
    max-height: 70vh;
  }

  .nav-btn {
    width: 40px;
    height: 40px;
    font-size: 20px;
  }

  .nav-prev {
    left: 8px;
  }

  .nav-next {
    right: 8px;
  }
}
</style>
