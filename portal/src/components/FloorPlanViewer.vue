<script setup lang="ts">
/**
 * 平面图全屏查看器：ImageViewer 的薄封装（FR-1）。
 *
 * 缩放/平移/切换/键盘/触摸与失败兜底都在通用 ImageViewer 里，这里只负责
 * 把业务字段（平面图名、楼层/空间）翻译成「标题/副标题」；入参与事件保持
 * 原样（images: ShareFloorPlan[] | null、startIndex、close），SharePage
 * 的调用方式不变。
 *
 * 标题兜底沿用原行为：后台没填名称时显示「平面图 N」（N 为可用图序号）。
 */
import { computed } from 'vue'

import ImageViewer from '@/components/ImageViewer.vue'
import type { ImageViewerImage } from '@/components/ImageViewer.vue'
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

const gallery = computed<ImageViewerImage[] | null>(() => {
  if (!props.images) return null
  return props.images
    .filter((plan) => Boolean(plan.image_url))
    .map((plan, position) => ({
      url: plan.image_url as string,
      title: (plan.name || '').trim() || `平面图 ${position + 1}`,
      subtitle: [plan.floor_label, plan.space_label]
        .map((value) => (value || '').trim())
        .filter(Boolean)
        .join(' · '),
    }))
})
</script>

<template>
  <ImageViewer
    :images="gallery"
    :start-index="startIndex"
    @close="emit('close')"
  />
</template>
