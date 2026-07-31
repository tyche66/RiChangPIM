<script setup lang="ts">
/**
 * 分享页的场景图灯箱。用原生 <dialog>（与 SourceDialog 一致）：
 * 自带焦点陷阱、Escape 关闭和背景遮罩，不引入任何轮播依赖。
 */
import { computed, ref, watch } from 'vue'

import type { ShareSceneImage } from '@/api'

const props = defineProps<{ images: ShareSceneImage[] | null }>()
const emit = defineEmits<{ close: [] }>()

const dialog = ref<HTMLDialogElement | null>(null)
const index = ref(0)

const list = computed(() => props.images || [])
const current = computed(() => list.value[index.value] || null)

function step(delta: number) {
  if (!list.value.length) return
  index.value = (index.value + delta + list.value.length) % list.value.length
}

watch(
  () => props.images,
  (value) => {
    const el = dialog.value
    index.value = 0
    if (!el) return
    if (value && value.length && !el.open) el.showModal()
    if ((!value || !value.length) && el.open) el.close()
  },
)
</script>

<template>
  <dialog
    ref="dialog"
    class="scene-dialog"
    aria-label="产品场景图"
    @close="emit('close')"
    @keydown.left="step(-1)"
    @keydown.right="step(1)"
  >
    <div v-if="current" class="scene-dialog__header">
      <h2>{{ current.name || '场景图' }}</h2>
      <button type="button" class="icon-button icon-button--quiet" aria-label="关闭场景图" @click="emit('close')">
        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
        </svg>
      </button>
    </div>
    <div v-if="current" class="scene-dialog__stage">
      <img :src="current.image_url as string" :alt="current.name || ''" decoding="async" />
    </div>
    <div v-if="current" class="scene-dialog__footer">
      <button
        type="button"
        class="button button--secondary button--small"
        :disabled="list.length < 2"
        @click="step(-1)"
      >
        上一张
      </button>
      <span class="muted-text">{{ index + 1 }} / {{ list.length }}</span>
      <button
        type="button"
        class="button button--secondary button--small"
        :disabled="list.length < 2"
        @click="step(1)"
      >
        下一张
      </button>
    </div>
  </dialog>
</template>
