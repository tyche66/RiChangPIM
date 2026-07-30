<script setup lang="ts">
/**
 * 产品卡。价格与库存一律走 utils/format：
 * 99999 / unknown 这类占位值不能渲染成看起来像真实数据的内容。
 */
import { computed, ref } from 'vue'
import { formatPrice, formatStock } from '@/utils/format'

const props = defineProps<{
  product: Record<string, unknown>
  detailUrl: string
}>()

const imageFailed = ref(false)

const productName = computed(() => String(props.product.product_name || props.product.product_no || '未命名产品'))
const productNo = computed(() => String(props.product.product_no || '未编号'))
const brandName = computed(() => String(props.product.brand_name || '品牌资料未提供'))
const categoryName = computed(() => String(props.product.category_name || '未分类'))
const price = computed(() => formatPrice(props.product.face_price_display ?? props.product.face_price))
const stock = computed(() => formatStock(props.product.stock_status_display ?? props.product.stock_status))
const stockTone = computed(() => (stock.value === '库存待确认' ? 'status-pill--warn' : ''))

const coverImageUrl = computed(() => {
  const value = props.product.cover_image_url
  return typeof value === 'string' && value ? value : null
})
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
    <div class="product-card__media">
      <img
        v-if="coverImageUrl && !imageFailed"
        class="product-card__image"
        :src="coverImageUrl"
        :alt="`${productName}（${categoryName}）产品图`"
        loading="lazy"
        decoding="async"
        @error="imageFailed = true"
      />
      <span v-else class="product-card__placeholder" aria-hidden="true">{{ placeholderText }}</span>
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
