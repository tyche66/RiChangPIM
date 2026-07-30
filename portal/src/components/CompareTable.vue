<script setup lang="ts">
/**
 * 产品比较表：行是属性、列是产品（AI-Docs/04 §3.2）。
 *
 * 两处折叠：所有产品都没有该属性的行直接不显示；
 * 有差异的行才加重字段名，避免用户逐格对照。
 */
import { computed } from 'vue'
import { COMPARE_FIELDS, MISSING_TEXT, cellText } from '@/utils/format'

const props = defineProps<{ products: Array<Record<string, unknown>> }>()

type Row = { key: string; label: string; cells: string[]; diff: boolean }

const columns = computed(() =>
  props.products.map((product, position) => ({
    key: String(product.id || product.product_no || position),
    label: String(product.product_no || product.product_name || `产品 ${position + 1}`),
  })),
)

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
</script>

<template>
  <section v-if="products.length > 1 && rows.length" class="panel panel--compare" aria-label="产品比较">
    <div class="panel__header">
      <div class="panel__title">
        <h2>逐项比较</h2>
        <span class="status-pill">{{ products.length }} 个产品</span>
      </div>
    </div>
    <div class="table-scroll">
      <table class="compare-table">
        <thead>
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
        </tbody>
      </table>
    </div>
    <p class="compare-note">
      加粗属性表示各产品之间存在差异。
      <template v-if="hiddenCount > 0">已隐藏 {{ hiddenCount }} 个所有产品都未提供的属性。</template>
    </p>
  </section>
</template>
