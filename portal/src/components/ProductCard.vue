<script setup lang="ts">
/**
 * 产品卡。价格与库存一律走 utils/format：
 * 99999 / unknown 这类占位值不能渲染成看起来像真实数据的内容。
 *
 * 图片按 utils/image 做字段兼容（`cover_image_url` → `images[].file_url`），
 * 加载失败时退回统一的占位块。占位块不是「掩盖问题」：卡片媒体区有固定
 * 的 aspect-ratio，图能不能加载都不影响卡片高度，布局不会跳。
 */
import { computed, ref, watch } from 'vue'
import { formatPrice, formatStock } from '@/utils/format'
import { resolveImageUrl } from '@/utils/image'

const props = defineProps<{
  product: Record<string, unknown>
  detailUrl: string
}>()

const imageUrl = computed(() => resolveImageUrl(props.product))
/** 记录**哪一条地址**加载失败，而不是布尔值：同一条地址重复触发 error 不会重复处理。 */
const failedUrl = ref('')
const loadedUrl = ref('')

// 换了产品（或换了地址）就重置成败记录，否则上一张图的失败会被误判到下一张上。
watch(
  imageUrl,
  (url) => {
    if (url !== failedUrl.value && url !== loadedUrl.value) {
      failedUrl.value = ''
      loadedUrl.value = ''
    }
  },
  { immediate: true },
)

function onImageError() {
  if (imageUrl.value && failedUrl.value !== imageUrl.value) failedUrl.value = imageUrl.value
}
function onImageLoad() {
  if (imageUrl.value) loadedUrl.value = imageUrl.value
}

const showImage = computed(() => Boolean(imageUrl.value) && failedUrl.value !== imageUrl.value)
/** 供 e2e 与排障使用的图片状态：ok / error / missing。 */
const imageState = computed(() => {
  if (showImage.value) return 'ok'
  return imageUrl.value ? 'error' : 'missing'
})

const productName = computed(() => String(props.product.product_name || props.product.product_no || '未命名产品'))
const productNo = computed(() => String(props.product.product_no || '未编号'))
const brandName = computed(() => String(props.product.brand_name || '品牌资料未提供'))
const categoryName = computed(() => String(props.product.category_name || '未分类'))
const price = computed(() => formatPrice(props.product.face_price_display ?? props.product.face_price))
const stock = computed(() => formatStock(props.product.stock_status_display ?? props.product.stock_status))
const stockTone = computed(() => (stock.value === '库存待确认' ? 'status-pill--warn' : ''))
const placeholderText = computed(() =>
  String(props.product.category_name || props.product.brand_name || 'PIM').slice(0, 2),
)
</script>

<template>
  <a
    class="product-card"
    :href="detailUrl"
    target="_blank"
    rel="noopener noreferrer"
    :aria-label="`在新标签页打开 ${productName} 详情`"
  >
    <div class="product-card__media" :data-image-state="imageState">
      <img
        v-if="showImage"
        :key="imageUrl || ''"
        class="product-card__image"
        :src="imageUrl || ''"
        :alt="`${productName}（${categoryName}）产品图`"
        loading="lazy"
        decoding="async"
        @error="onImageError"
        @load="onImageLoad"
      />
      <span v-else class="product-card__placeholder" aria-hidden="true">
        <svg class="product-card__placeholder-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <circle cx="8.5" cy="9.5" r="1.6" />
          <path d="M4 17l5-5 3.5 3.5L15 13l5 5" />
        </svg>
        <span class="product-card__placeholder-text">{{ placeholderText }}</span>
      </span>
    </div>
    <div class="product-card__body">
      <div class="product-card__meta">
        <span class="product-code">{{ productNo }}</span>
        <span class="status-pill" :class="stockTone">{{ stock }}</span>
      </div>
      <h3>{{ productName }}</h3>
      <p class="product-card__brand">{{ brandName }}</p>
      <div class="product-card__footer">
        <strong>{{ price }}</strong>
        <span>{{ categoryName }}</span>
      </div>
    </div>
  </a>
</template>
