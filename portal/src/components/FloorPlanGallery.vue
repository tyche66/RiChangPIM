<script setup lang="ts">
/**
 * 方案信息右侧的平面图缩略图列。
 *
 * 只负责「看得见什么」：不判断权限、不发请求。点击只把序号抛给父组件，由全屏
 * 查看器负责前后切换，因为「当前看第几张」属于查看器状态。
 *
 * 多于 4 张时只显示前 4 张，最后一张盖一个「+N」角标，避免 20 张图把方案信息
 * 卡片撑成一屏半；完整列表在全屏查看器里左右切换浏览。
 */
import { computed } from 'vue'
import type { ShareFloorPlan } from '@/api'

const props = defineProps<{ images: ShareFloorPlan[] }>()
const emit = defineEmits<{ open: [index: number] }>()

const MAX_TILES = 4

const usable = computed(() => props.images.filter((image) => Boolean(image.image_url)))
const tiles = computed(() => usable.value.slice(0, MAX_TILES))
const overflowCount = computed(() => Math.max(0, usable.value.length - MAX_TILES))

function planName(image: ShareFloorPlan, index: number): string {
  return (image.name || '').trim() || `平面图 ${index + 1}`
}
</script>

<template>
  <div
    v-if="usable.length"
    class="plan-gallery"
  >
    <button
      v-for="(image, index) in tiles"
      :key="image.id || index"
      type="button"
      class="plan-tile"
      :aria-label="`全屏查看：${planName(image, index)}`"
      @click="emit('open', index)"
    >
      <span class="plan-tile__thumb">
        <img
          :src="image.image_url as string"
          :alt="planName(image, index)"
          loading="lazy"
          decoding="async"
        >
        <span
          v-if="index === MAX_TILES - 1 && overflowCount"
          class="plan-tile__overflow"
        >+{{ overflowCount }}</span>
      </span>
      <span
        class="plan-tile__name"
        :title="planName(image, index)"
      >{{ planName(image, index) }}</span>
    </button>
  </div>
</template>
