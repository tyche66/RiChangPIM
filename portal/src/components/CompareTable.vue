<script setup lang="ts">
/**
 * 产品比较表：行是属性、列是产品（AI-Docs/04 §3.2）。
 *
 * 两处折叠：所有产品都没有该属性的行直接不显示；
 * 有差异的行才加重字段名，避免用户逐格对照。
 *
 * 主图放在表头：选品时最先看的是「长什么样」，把它压进某一行里会让
 * 用户滚动找图。缩略图点击打开灯箱，导出按钮在同一块表头里。
 */
import { computed, ref } from 'vue'
import {
  COMPARE_FIELDS,
  MISSING_TEXT,
  cellText,
  formatPrice,
  formatStock,
} from '@/utils/format'
import { buildCompareMarkdown, downloadBlob, downloadTextFile } from '@/utils/export'
import { exportComparePdf } from '@/api'
import { useAuthStore } from '@/stores/auth'
import ImageLightbox from '@/components/ImageLightbox.vue'

const props = defineProps<{ products: Array<Record<string, unknown>> }>()

type Row = { key: string; label: string; cells: string[]; diff: boolean }

const auth = useAuthStore()
const pdfBusy = ref(false)
const notice = ref('')
const viewerOpen = ref(false)
const viewerIndex = ref(0)

const columns = computed(() =>
  props.products.map((product, position) => {
    const cover = typeof product.cover_image_url === 'string' ? product.cover_image_url : ''
    return {
      key: String(product.id || product.product_no || position),
      label: String(product.product_no || product.product_name || `产品 ${position + 1}`),
      image: cover,
      name: String(product.product_name || ''),
    }
  }),
)

const images = computed(() => columns.value.map((column) => column.image).filter(Boolean))

function openViewer(position: number) {
  const url = columns.value[position]?.image
  if (!url) return
  viewerIndex.value = Math.max(images.value.indexOf(url), 0)
  viewerOpen.value = true
}

const rows = computed<Row[]>(() => {
  const result: Row[] = []
  for (const field of COMPARE_FIELDS) {
    const cells = props.products.map((product) => cellText(product[field.key]))
    if (cells.every((cell) => cell === MISSING_TEXT)) continue
    result.push({
      key: field.key,
      label: field.label,
      cells,
      diff: new Set(cells).size > 1,
    })
  }
  return result
})

const hiddenCount = computed(() => COMPARE_FIELDS.length - rows.value.length)

function handleExportMarkdown() {
  notice.value = ''
  downloadTextFile('product_compare.md', buildCompareMarkdown(props.products))
}

async function handleExportPdf() {
  notice.value = ''
  const token = auth.accessToken
  if (!token) {
    notice.value = '登录状态已失效，请重新登录后再导出'
    return
  }
  const ids = props.products
    .map((product) => (typeof product.id === 'string' ? product.id : ''))
    .filter(Boolean)
  if (!ids.length) {
    notice.value = '当前结果缺少产品 ID，无法导出 PDF'
    return
  }
  pdfBusy.value = true
  try {
    const blob = await exportComparePdf(token, ids)
    downloadBlob('product_compare.pdf', blob)
  } catch (error) {
    notice.value = error instanceof Error ? error.message : 'PDF 导出失败'
  } finally {
    pdfBusy.value = false
  }
}
</script>

<template>
  <section v-if="products.length > 1 && rows.length" class="panel panel--compare" aria-label="产品比较">
    <div class="panel__header">
      <div class="panel__title">
        <h2>逐项比较</h2>
        <span class="status-pill">{{ products.length }} 个产品</span>
      </div>
      <div class="panel__tools">
        <button type="button" class="button button--secondary button--small" @click="handleExportMarkdown">
          导出 MD
        </button>
        <button
          type="button"
          class="button button--secondary button--small"
          :disabled="pdfBusy"
          @click="handleExportPdf"
        >
          {{ pdfBusy ? '生成中…' : '导出 PDF' }}
        </button>
      </div>
    </div>
    <div class="table-scroll">
      <table class="compare-table">
        <thead>
          <tr class="compare-media">
            <th scope="col">主图</th>
            <th v-for="(column, position) in columns" :key="`media-${column.key}`" scope="col">
              <button
                v-if="column.image"
                type="button"
                class="compare-thumb"
                :aria-label="`查看 ${column.name || column.label} 大图`"
                @click="openViewer(position)"
              >
                <img :src="column.image" :alt="column.name" loading="lazy">
              </button>
              <span v-else class="compare-thumb compare-thumb--empty">无图</span>
            </th>
          </tr>
          <tr>
            <th scope="col">属性</th>
            <th v-for="column in columns" :key="column.key" scope="col">{{ column.label }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.key" :class="{ 'is-diff': row.diff }">
            <th scope="row">{{ row.label }}</th>
            <td
              v-for="(cell, position) in row.cells"
              :key="`${row.key}-${position}`"
              :class="{ 'cell-empty': cell === MISSING_TEXT }"
            >
              {{ cell }}
            </td>
          </tr>
          <tr>
            <th scope="row">价格</th>
            <td v-for="(product, position) in products" :key="`price-${position}`">
              {{ formatPrice(product.face_price) }}
            </td>
          </tr>
          <tr>
            <th scope="row">库存状态</th>
            <td v-for="(product, position) in products" :key="`stock-${position}`">
              {{ formatStock(product.stock_status) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="compare-note">
      加粗属性表示各产品之间存在差异。
      <template v-if="hiddenCount > 0">已隐藏 {{ hiddenCount }} 个所有产品都未提供的属性。</template>
    </p>
    <p v-if="notice" class="compare-note compare-note--warn">{{ notice }}</p>
    <ImageLightbox
      :open="viewerOpen"
      :images="images"
      :index="viewerIndex"
      @close="viewerOpen = false"
    />
  </section>
</template>
