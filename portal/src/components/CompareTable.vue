<script setup lang="ts">
defineProps<{ products: Array<Record<string, unknown>> }>()
</script>

<template>
  <div v-if="products.length > 1" class="compare-panel">
    <div class="panel-heading">
      <p class="eyebrow">Side by side</p>
      <h3>比较</h3>
    </div>
    <div class="table-scroll">
      <table class="compare-table">
        <thead>
          <tr>
            <th>字段</th>
            <th v-for="product in products" :key="String(product.id)">{{ product.product_no }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="field in ['product_name', 'brand_name', 'category_name', 'material', 'specification', 'colors']" :key="field">
            <td>{{ field }}</td>
            <td v-for="product in products" :key="`${String(product.id)}-${field}`">{{ product[field] || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
