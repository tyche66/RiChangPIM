<script setup lang="ts">
/**
 * 公开分享页 /share/:token。
 *
 * 为什么在门户而不是后台：后台是以 base '/admin/' 构建的，`/share/xxx` 这种
 * 根路径落不到后台路由上；而分享链接由后端生成为 `/share/{token}`（见
 * backend/app/api/v1/shares.py），必须由 nginx 的 location /（门户）接住。
 * 门户视觉语言也更贴近 C 端访客：中性黑白灰、无 UI 框架、暖色只来自产品照片。
 *
 * 这页面对访客不做任何鉴权：鉴权由分享令牌本身承担（后端会校验状态/过期/
 * 次数上限/访问密码，并逐次写 ShareLog）。因此绝不能在这里带 Authorization。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import AppHeader from '@/components/AppHeader.vue'
import FloorPlanGallery from '@/components/FloorPlanGallery.vue'
import FloorPlanViewer from '@/components/FloorPlanViewer.vue'
import ImageViewer from '@/components/ImageViewer.vue'
import type { ImageViewerImage } from '@/components/ImageViewer.vue'
import ShareDetailDialog from '@/components/ShareDetailDialog.vue'
import {
  ShareAccessError,
  getShareContent,
  type ShareEnvelopeData,
  type ShareFloorPlan,
  type ShareProductItem,
  type ShareProposalContent,
  type ShareQuotationContent,
  type ShareSceneImage,
} from '@/api'
import { MISSING_TEXT, formatPrice } from '@/utils/format'
import { useSettingsStore } from '@/stores/settings'

const settings = useSettingsStore()

const route = useRoute()
const token = String(route.params.token || '')

type Phase = 'loading' | 'ok' | 'need-password' | 'failed'

const phase = ref<Phase>('loading')
const message = ref('')
const passwordInput = ref('')
const share = ref<ShareEnvelopeData | null>(null)
const detailOpen = ref(false)
const detailItem = ref<ShareProductItem | null>(null)
const failedImages = ref<Set<string>>(new Set())

const STATUS_LABELS: Record<string, string> = { draft: '草稿', confirmed: '已确认' }

const isProposal = computed(() => share.value?.share_type === 'proposal')
const proposal = computed(() =>
  isProposal.value ? (share.value?.content as ShareProposalContent | null) : null,
)
const quotation = computed(() =>
  share.value && !isProposal.value ? (share.value.content as ShareQuotationContent | null) : null,
)
const items = computed<ShareProductItem[]>(
  () => (isProposal.value ? proposal.value?.items : quotation.value?.items) || [],
)

/**
 * Track D：平面图只在方案分享里出现；报价分享与旧分享没有这个字段，
 * 一律当成「没有平面图」，不渲染右侧栏。
 */
const floorPlans = computed<ShareFloorPlan[]>(() =>
  isProposal.value
    ? (proposal.value?.floor_plans || []).filter((plan) => Boolean(plan.image_url))
    : [],
)

const planOpen = ref(false)
const planIndex = ref(0)

function openPlan(index: number) {
  planIndex.value = index
  planOpen.value = true
}

const headline = computed(() => {
  if (!share.value) return '分享预览'
  return isProposal.value ? '产品方案' : '产品报价'
})

const summaryRows = computed<Array<[string, string]>>(() => {
  if (isProposal.value) {
    const content = proposal.value
    return [
      ['方案编号', content?.proposal_no || MISSING_TEXT],
      ['方案名称', content?.proposal_name || MISSING_TEXT],
      ['客户名称', content?.customer_name || MISSING_TEXT],
      ['状态', statusLabel(content?.status)],
      ['总面价', formatPrice(content?.total_face_value)],
    ]
  }
  const content = quotation.value
  return [
    ['报价单号', content?.quotation_no || MISSING_TEXT],
    ['状态', statusLabel(content?.status)],
    ['总金额', formatPrice(content?.total_amount)],
  ]
})

function statusLabel(status?: string | null): string {
  if (!status) return MISSING_TEXT
  return STATUS_LABELS[status] || status
}

function taxRateText(rate?: number | null): string {
  if (rate === null || rate === undefined) return MISSING_TEXT
  return `${(rate * 100).toFixed(0)}%`
}

// ---------------------------------------------------------------------------
// FR-1：商品图片画廊（ImageViewer）
// 画廊内容 = 主图 cover_image_url（存在时第一张）+ 场景图（按 sort 升序），
// 过滤空地址；缩略图、详情封面、「查看 N 张场景图」三个入口打开同一个画廊。
// ---------------------------------------------------------------------------

/** 场景图按 sort 升序；缺 sort 的排在有值的后面，同为空保持接口顺序。 */
function bySort(a: ShareSceneImage, b: ShareSceneImage): number {
  const va = a.sort ?? Number.POSITIVE_INFINITY
  const vb = b.sort ?? Number.POSITIVE_INFINITY
  return va - vb
}

function galleryImagesOf(item: ShareProductItem): ImageViewerImage[] {
  const images: ImageViewerImage[] = []
  if (item.cover_image_url) {
    images.push({
      url: item.cover_image_url,
      title: item.product_name || MISSING_TEXT,
      subtitle: '商品主图',
    })
  }
  for (const scene of (item.scene_images || []).filter((image) => Boolean(image.image_url)).sort(bySort)) {
    images.push({
      url: scene.image_url as string,
      title: item.product_name || MISSING_TEXT,
      subtitle: (scene.name || '').trim(),
    })
  }
  return images
}

const galleryOpen = ref(false)
const galleryImages = ref<ImageViewerImage[]>([])
const galleryIndex = ref(0)

function openGallery(item: ShareProductItem, startIndex = 0) {
  const images = galleryImagesOf(item)
  if (!images.length) return
  galleryImages.value = images
  galleryIndex.value = Math.max(0, Math.min(startIndex, images.length - 1))
  galleryOpen.value = true
}

/** 详情弹窗「查看 N 张场景图」：有主图时画廊从第一张场景图开始。 */
function openScenes(item: ShareProductItem) {
  openGallery(item, item.cover_image_url ? 1 : 0)
}

/** 含税小计由未税单价、数量、税率现算，后端只给未税 subtotal。 */
function taxedSubtotal(item: ShareProductItem): string {
  if (item.unit_price === null || item.unit_price === undefined) return MISSING_TEXT
  const quantity = item.quantity ?? 0
  const rate = item.tax_rate ?? 0
  return formatPrice(item.unit_price * quantity * (1 + rate))
}

function lineTotal(item: ShareProductItem): string {
  if (item.line_total !== null && item.line_total !== undefined) return formatPrice(item.line_total)
  if (item.face_price === null || item.face_price === undefined) return MISSING_TEXT
  return formatPrice(item.face_price * (item.quantity ?? 0))
}

function placeholderText(name?: string | null): string {
  if (!name) return '无图'
  const cjk = name.match(/^[一-鿿]+/)
  if (cjk) return cjk[0].slice(0, 2)
  return name.slice(0, 4)
}

function imageKey(item: ShareProductItem, index: number): string {
  return item.product_id || `${index}`
}

function coverUrl(item: ShareProductItem, index: number): string | null {
  if (failedImages.value.has(imageKey(item, index))) return null
  return item.cover_image_url || null
}

function onImageError(item: ShareProductItem, index: number) {
  const next = new Set(failedImages.value)
  next.add(imageKey(item, index))
  failedImages.value = next
}

// ---------------------------------------------------------------------------
// Track C：按楼层/空间分组展示
// ---------------------------------------------------------------------------

interface SpaceGroup {
  key: string
  floor: string
  space: string
  items: ShareProductItem[]
}

/** 楼层/空间分组标题：优先 floor_label + space_label，缺失时归入"未指定位置"。 */
const spaceGroups = computed<SpaceGroup[]>(() => {
  const map = new Map<string, SpaceGroup>()
  for (const item of items.value) {
    const floor = (item.floor_label || '').trim()
    const space = (item.space_label || '').trim()
    const key = `${floor}||${space}`
    if (!map.has(key)) {
      map.set(key, {
        key,
        floor: floor || MISSING_TEXT,
        space: space || MISSING_TEXT,
        items: [],
      })
    }
    map.get(key)!.items.push(item)
  }
  return [...map.values()]
})

function groupTitle(group: SpaceGroup): string {
  if (group.floor !== MISSING_TEXT && group.space !== MISSING_TEXT) {
    return `${group.floor} · ${group.space}`
  }
  if (group.floor !== MISSING_TEXT) return group.floor
  if (group.space !== MISSING_TEXT) return group.space
  return '未指定位置'
}

/** 材质/颜色/材质说明/规格：只在商品详情弹窗里使用，见 ShareDetailDialog。 */
function categoryText(item: ShareProductItem): string {
  const snapshot = item.product_snapshot
  const value = snapshot?.category_name ?? item.category_name
  return value || MISSING_TEXT
}

/** 打开商品详情弹窗；弹窗内再点“查看场景图”时才进入灯箱。 */
function openDetail(item: ShareProductItem) {
  detailItem.value = item
  detailOpen.value = true
}

/** 关闭后必须把 item 一起复位，否则再次点同一个商品（或点关闭）时 watch 不会触发。 */
function closeDetail() {
  detailOpen.value = false
  detailItem.value = null
}

async function load() {
  if (!token) {
    phase.value = 'failed'
    message.value = '这个链接缺少分享编号，请向发送方索取完整链接。'
    return
  }
  phase.value = 'loading'
  try {
    share.value = await getShareContent(token, passwordInput.value || undefined)
    phase.value = 'ok'
    message.value = ''
  } catch (error) {
    share.value = null
    if (error instanceof ShareAccessError && error.code === 40304) {
      // 首次访问带密码分享时后端同样返回 40304：既用于「需要密码」也用于「密码错误」。
      phase.value = 'need-password'
      message.value = passwordInput.value ? error.message : '该分享需要访问密码。'
      return
    }
    phase.value = 'failed'
    message.value = error instanceof Error ? error.message : '分享链接无效或已过期'
  }
}

onMounted(load)
</script>

<template>
  <AppHeader />

  <main class="share-shell">
    <section class="share-head">
      <p class="eyebrow">分享预览</p>
      <h1>{{ headline }}</h1>
      <p v-if="phase === 'ok'" class="muted-text">
        本页由发送方通过分享链接开放，内容与后台数据实时一致。
      </p>
    </section>

    <p v-if="phase === 'loading'" class="status-line">
      <span class="spinner" aria-hidden="true" />
      正在校验分享链接…
    </p>

    <!-- 需要访问密码 -->
    <section v-else-if="phase === 'need-password'" class="panel share-gate">
      <div class="panel__header">
        <div class="panel__title"><h2>请输入访问密码</h2></div>
        <span class="status-pill status-pill--warn">受密码保护</span>
      </div>
      <p class="notice notice--warn">{{ message }}</p>
      <form class="share-gate__form" @submit.prevent="load">
        <label class="field">
          <span>访问密码</span>
          <input v-model="passwordInput" type="password" autocomplete="off" placeholder="向发送方索取" />
        </label>
        <button class="button button--primary" type="submit" :disabled="!passwordInput">查看内容</button>
      </form>
    </section>

    <!-- 彻底不可用 -->
    <section v-else-if="phase === 'failed'" class="panel">
      <div class="panel__header">
        <div class="panel__title"><h2>链接不可用</h2></div>
        <span class="status-pill">已失效</span>
      </div>
      <p class="notice notice--error">{{ message }}</p>
      <p class="muted-text">
        分享链接可能已被撤销、超过有效期或访问次数已用完。请联系发送方重新生成。
      </p>
    </section>

    <!-- 正文 -->
    <template v-else-if="phase === 'ok'">
      <section class="panel">
        <div class="panel__header">
          <div class="panel__title"><h2>{{ isProposal ? '方案信息' : '报价信息' }}</h2></div>
          <span class="status-pill status-pill--ok">有效链接</span>
        </div>
        <!-- 右侧留给平面图：没有平面图时退回单列，卡片不会无故变窄 -->
        <div
          class="summary-layout"
          :class="{ 'summary-layout--with-plans': floorPlans.length > 0 }"
        >
          <div class="kv-grid">
            <template v-for="row in summaryRows" :key="row[0]">
              <span>{{ row[0] }}</span>
              <strong>{{ row[1] }}</strong>
            </template>
          </div>
          <div
            v-if="floorPlans.length"
            class="summary-plans"
          >
            <p class="summary-plans__label">
              平面图
              <span class="summary-plans__count">{{ floorPlans.length }} 张</span>
            </p>
            <FloorPlanGallery
              :images="floorPlans"
              @open="openPlan"
            />
          </div>
        </div>
      </section>

      <section class="panel">
        <div class="panel__header">
          <div class="panel__title"><h2>{{ isProposal ? '商品列表' : '商品明细' }}</h2></div>
          <span class="section-head__count">{{ items.length }} 项</span>
        </div>

        <p v-if="!items.length" class="muted-text">这份分享暂无商品明细。</p>

        <div v-else class="space-groups">
          <section
            v-for="group in spaceGroups"
            :key="group.key"
            class="space-group"
          >
            <header class="space-group__head">
              <h3>{{ groupTitle(group) }}</h3>
              <span class="section-head__count">{{ group.items.length }} 项</span>
            </header>

            <div class="table-scroll">
              <table class="compare-table share-table">
                <thead>
                  <tr>
                    <th scope="col">商品</th>
                    <th scope="col" class="is-numeric">面价</th>
                    <th v-if="!isProposal" scope="col" class="is-numeric">单价</th>
                    <th scope="col" class="is-numeric">数量</th>
                    <th scope="col" class="is-numeric">{{ isProposal ? '行合计' : '含税小计' }}</th>
                    <th scope="col" class="share-table__action-head">详情</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(item, index) in group.items" :key="item.product_id || index">
                    <td>
                      <!-- FR-1：缩略图是独立按钮，只开画廊；商品名/「查看详情」才开详情，互不误触 -->
                      <div class="share-product">
                        <button
                          v-if="galleryImagesOf(item).length"
                          type="button"
                          class="share-product__thumb share-product__thumb--button"
                          :aria-label="`查看「${item.product_name || MISSING_TEXT}」的图片`"
                          @click="openGallery(item)"
                        >
                          <img
                            v-if="coverUrl(item, index)"
                            :src="coverUrl(item, index) as string"
                            alt=""
                            loading="lazy"
                            decoding="async"
                            width="56"
                            height="56"
                            @error="onImageError(item, index)"
                          />
                          <span v-else class="share-product__fallback">{{ placeholderText(item.product_name) }}</span>
                        </button>
                        <span
                          v-else
                          class="share-product__thumb"
                        >
                          <span class="share-product__fallback">{{ placeholderText(item.product_name) }}</span>
                        </span>
                        <button
                          type="button"
                          class="share-product__text"
                          title="查看商品详情"
                          @click="openDetail(item)"
                        >
                          <span class="share-product__name">{{ item.product_name || MISSING_TEXT }}</span>
                          <span class="product-code">{{ item.product_no || MISSING_TEXT }}</span>
                          <span class="share-product__hint">{{ categoryText(item) }}</span>
                        </button>
                      </div>
                    </td>
                    <td class="is-numeric">{{ formatPrice(item.face_price) }}</td>
                    <td v-if="!isProposal" class="is-numeric">{{ formatPrice(item.unit_price) }}</td>
                    <td class="is-numeric">{{ item.quantity ?? MISSING_TEXT }}</td>
                    <td class="is-numeric">
                      <strong>{{ isProposal ? lineTotal(item) : taxedSubtotal(item) }}</strong>
                    </td>
                    <td class="share-table__action">
                      <button type="button" class="button button--secondary button--small" @click="openDetail(item)">
                        查看详情
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </section>

      <footer class="share-foot">
        <span>访问次数 {{ share?.access_count ?? 0 }}</span>
        <span>{{ settings.footerText }}</span>
      </footer>
    </template>

    <!-- 商品图片画廊（FR-1）：缩略图 / 详情封面 / 「查看 N 张场景图」共用一个查看器 -->
    <ImageViewer
      :images="galleryOpen ? galleryImages : null"
      :start-index="galleryIndex"
      @close="galleryOpen = false"
    />

    <!-- 平面图全屏：缩略图只是入口，缩放与多张切换都在这里 -->
    <FloorPlanViewer
      :images="planOpen ? floorPlans : null"
      :start-index="planIndex"
      @close="planOpen = false"
    />

    <!-- 商品详情：明细表只放摘要，规格/材质/颜色/材质说明与场景图在点击后展开 -->
    <ShareDetailDialog
      :item="detailOpen ? detailItem : null"
      @close="closeDetail"
      @open-scenes="openScenes"
      @open-gallery="openGallery($event)"
    />
  </main>
</template>

<style scoped>
.space-groups {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.space-group {
  border: 1px solid var(--color-border, #e5e7eb);
  border-radius: 8px;
  overflow: hidden;
}

.space-group__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px;
  background: var(--color-muted, #f5f5f5);
  border-bottom: 1px solid var(--color-border, #e5e7eb);
}

.space-group__head h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.share-cell--wrap {
  max-width: 260px;
  white-space: normal;
  word-break: break-word;
  font-size: 13px;
  color: var(--color-muted-foreground, #6b7280);
}
</style>
