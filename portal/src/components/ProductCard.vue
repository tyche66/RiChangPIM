<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{
  product: Record<string, unknown>
  detailUrl: string
}>()

const imageFailed = ref(false)
const productName = computed(() => String(props.product.product_name || props.product.product_no || '未命名产品'))
const coverImageUrl = computed(() => {
  const value = props.product.cover_image_url
  return typeof value === 'string' && value ? value : null
})
const placeholderText = computed(() => String(props.product.category_name || props.product.brand_name || 'PIM').slice(0, 2))

function displayPrice(value: unknown) {
  if (value === 99999 || value === '待核价' || value === null || value === undefined) return '待核价'
  const price = Number(value)
  return Number.isFinite(price) ? `¥${price.toLocaleString('zh-CN')}` : String(value)
}

function displayStatus(value: unknown) {
  if (value === 'unknown') return '库存待确认'
  return String(value || '状态待确认')
}
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
        :alt="productName"
        @error="imageFailed = true"
      />
      <span v-else class="product-card__placeholder" aria-hidden="true">{{ placeholderText }}</span>
    </div>
    <div class="product-card__body">
      <div class="product-card__meta">
        <span class="product-code">{{ product.product_no || '未编号' }}</span>
        <span class="status-pill">{{ displayStatus(product.stock_status_display ?? product.stock_status) }}</span>
      </div>
      <h3>{{ productName }}</h3>
      <p class="product-card__brand">{{ product.brand_name || '未设置品牌' }}</p>
      <div class="product-card__footer">
        <strong>{{ displayPrice(product.face_price_display ?? product.face_price) }}</strong>
        <span>{{ product.category_name || '未分类' }}</span>
      </div>
      <span class="product-card__open">打开详情</span>
    </div>
  </a>
</template>
