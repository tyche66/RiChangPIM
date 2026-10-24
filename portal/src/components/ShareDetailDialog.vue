<script setup lang="ts">
/**
 * 商品详情弹窗：分享页明细表只放摘要（商品/面价/单价/数量/行合计），
 * 分类、规格、材质、颜色、材质说明、场景图在这里展开，避免一上来就把
 * 十几列塞进手机屏。
 *
 * 与 ShareSceneDialog 一样用原生 <dialog>，自带焦点陷阱、Escape 关闭和遮罩；
 * 场景图不在这里自己渲染，交给调用方打开已有的灯箱。
 */
import { computed, ref, watch } from 'vue'

import type { ShareProductItem } from '@/api'
import { MISSING_TEXT, formatPrice } from '@/utils/format'

const props = defineProps<{
  item: ShareProductItem | null
  /** 报价单要额外显示单价、税率、未税小计 */
  isQuotation?: boolean
}>()
const emit = defineEmits<{
  close: []
  openScenes: [item: ShareProductItem]
}>()

const dialog = ref<HTMLDialogElement | null>(null)
const failed = ref(false)

const open = computed(() => Boolean(props.item))

const snapshot = computed(() => props.item?.product_snapshot ?? null)

/** 快照优先、当前字段其次：历史方案不因产品资料后续改动而漂移。 */
function pick(snapshotValue: string | null | undefined, current: string | null | undefined): string {
  const value = snapshotValue ?? current
  return value ? String(value) : MISSING_TEXT
}

const category = computed(() => pick(snapshot.value?.category_name, props.item?.category_name))
const specification = computed(() => pick(snapshot.value?.specification, props.item?.specification))
const material = computed(() => pick(snapshot.value?.material, props.item?.material))
const colors = computed(() => pick(snapshot.value?.colors, props.item?.colors))
const materialDesc = computed(() => {
  // 业务员在明细行填的材质说明是给客户的最终口径，产品快照只作旧数据兜底。
  const value =
    props.item?.material_desc ||
    snapshot.value?.material_description ||
    props.item?.material_description
  return value || MISSING_TEXT
})
const location = computed(() => {
  const parts = [props.item?.floor_label, props.item?.space_label]
    .map((value) => (value || '').trim())
    .filter(Boolean)
  return parts.length ? parts.join(' · ') : MISSING_TEXT
})
const lineTotal = computed(() => {
  const item = props.item
  if (!item) return MISSING_TEXT
  if (item.line_total !== null && item.line_total !== undefined) return formatPrice(item.line_total)
  if (item.face_price === null || item.face_price === undefined) return MISSING_TEXT
  return formatPrice(item.face_price * (item.quantity ?? 0))
})
const taxRate = computed(() => {
  const rate = props.item?.tax_rate
  if (rate === null || rate === undefined) return MISSING_TEXT
  return `${(rate * 100).toFixed(0)}%`
})
const sceneImages = computed(() =>
  (props.item?.scene_images || []).filter((image) => Boolean(image.image_url)),
)

function close() {
  emit('close')
}

watch(
  () => props.item,
  (value) => {
    failed.value = false
    const el = dialog.value
    if (!el) return
    if (value && !el.open) el.showModal()
    if (!value && el.open) el.close()
  },
)
</script>

<template>
  <dialog
    ref="dialog"
    class="share-detail-dialog"
    aria-label="商品详情"
    @close="close"
  >
    <div v-if="item" class="share-detail-dialog__header">
      <div class="share-detail-dialog__heading">
        <h2>{{ item.product_name || MISSING_TEXT }}</h2>
        <span class="product-code">{{ item.product_no || MISSING_TEXT }}</span>
      </div>
      <button type="button" class="icon-button icon-button--quiet" aria-label="关闭商品详情" @click="close">
        <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
        </svg>
      </button>
    </div>

    <div v-if="item" class="share-detail-dialog__body">
      <div class="share-detail-dialog__cover">
        <img
          v-if="item.cover_image_url && !failed"
          :src="item.cover_image_url"
          alt=""
          decoding="async"
          @error="failed = true"
        />
        <span v-else class="share-product__fallback">无图</span>
      </div>

      <dl class="share-detail-dialog__facts">
        <div>
          <dt>分类</dt>
          <dd>{{ category }}</dd>
        </div>
        <div>
          <dt>楼层 / 空间</dt>
          <dd>{{ location }}</dd>
        </div>
        <div>
          <dt>规格</dt>
          <dd>{{ specification }}</dd>
        </div>
        <div>
          <dt>材质</dt>
          <dd>{{ material }}</dd>
        </div>
        <div>
          <dt>颜色</dt>
          <dd>{{ colors }}</dd>
        </div>
        <div>
          <dt>材质说明</dt>
          <dd>{{ materialDesc }}</dd>
        </div>
        <div>
          <dt>面价</dt>
          <dd>{{ formatPrice(item.face_price) }}</dd>
        </div>
        <div v-if="isQuotation">
          <dt>单价</dt>
          <dd>{{ formatPrice(item.unit_price) }}</dd>
        </div>
        <div>
          <dt>数量</dt>
          <dd>{{ item.quantity ?? MISSING_TEXT }}</dd>
        </div>
        <div v-if="isQuotation">
          <dt>税率</dt>
          <dd>{{ taxRate }}</dd>
        </div>
        <div>
          <dt>{{ isQuotation ? '含税小计' : '行合计' }}</dt>
          <dd class="share-detail-dialog__total">{{ lineTotal }}</dd>
        </div>
      </dl>

      <div v-if="sceneImages.length" class="share-detail-dialog__scenes">
        <button
          type="button"
          class="button button--secondary button--small"
          @click="emit('openScenes', item)"
        >
          查看 {{ sceneImages.length }} 张场景图
        </button>
      </div>
    </div>

    <div v-if="item" class="share-detail-dialog__footer">
      <button type="button" class="button button--secondary button--small" @click="close">关闭</button>
    </div>
  </dialog>
</template>