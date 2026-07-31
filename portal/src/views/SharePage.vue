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
import ShareSceneDialog from '@/components/ShareSceneDialog.vue'
import {
  ShareAccessError,
  getShareContent,
  type ShareEnvelopeData,
  type ShareProductItem,
  type ShareProposalContent,
  type ShareQuotationContent,
  type ShareSceneImage,
} from '@/api'
import { MISSING_TEXT, formatPrice } from '@/utils/format'

const route = useRoute()
const token = String(route.params.token || '')

type Phase = 'loading' | 'ok' | 'need-password' | 'failed'

const phase = ref<Phase>('loading')
const message = ref('')
const passwordInput = ref('')
const share = ref<ShareEnvelopeData | null>(null)
const scenes = ref<ShareSceneImage[]>([])
const sceneOpen = ref(false)
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

function sceneImagesOf(item: ShareProductItem): ShareSceneImage[] {
  return (item.scene_images || []).filter((image) => Boolean(image.image_url))
}

function openScenes(item: ShareProductItem) {
  const available = sceneImagesOf(item)
  if (!available.length) return
  scenes.value = available
  sceneOpen.value = true
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
        <div class="kv-grid">
          <template v-for="row in summaryRows" :key="row[0]">
            <span>{{ row[0] }}</span>
            <strong>{{ row[1] }}</strong>
          </template>
        </div>
      </section>

      <section class="panel">
        <div class="panel__header">
          <div class="panel__title"><h2>{{ isProposal ? '商品列表' : '商品明细' }}</h2></div>
          <span class="section-head__count">{{ items.length }} 项</span>
        </div>

        <p v-if="!items.length" class="muted-text">这份分享暂无商品明细。</p>

        <div v-else class="table-scroll">
          <table class="compare-table share-table">
            <thead>
              <tr>
                <th scope="col">商品</th>
                <th scope="col" class="is-numeric">面价</th>
                <th v-if="!isProposal" scope="col" class="is-numeric">单价</th>
                <th scope="col" class="is-numeric">数量</th>
                <th v-if="!isProposal" scope="col" class="is-numeric">税率</th>
                <th v-if="!isProposal" scope="col" class="is-numeric">未税小计</th>
                <th scope="col" class="is-numeric">{{ isProposal ? '行合计' : '含税小计' }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(item, index) in items" :key="item.product_id || index">
                <td>
                  <button
                    type="button"
                    class="share-product"
                    :class="{ 'share-product--static': !sceneImagesOf(item).length }"
                    :disabled="!sceneImagesOf(item).length"
                    @click="openScenes(item)"
                  >
                    <span class="share-product__thumb">
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
                    </span>
                    <span class="share-product__text">
                      <span class="share-product__name">{{ item.product_name || MISSING_TEXT }}</span>
                      <span class="product-code">{{ item.product_no || MISSING_TEXT }}</span>
                      <span v-if="sceneImagesOf(item).length" class="share-product__hint">
                        {{ sceneImagesOf(item).length }} 张场景图 · 点击查看
                      </span>
                    </span>
                  </button>
                </td>
                <td class="is-numeric">{{ formatPrice(item.face_price) }}</td>
                <td v-if="!isProposal" class="is-numeric">{{ formatPrice(item.unit_price) }}</td>
                <td class="is-numeric">{{ item.quantity ?? MISSING_TEXT }}</td>
                <td v-if="!isProposal" class="is-numeric">{{ taxRateText(item.tax_rate) }}</td>
                <td v-if="!isProposal" class="is-numeric">{{ formatPrice(item.subtotal) }}</td>
                <td class="is-numeric">
                  <strong>{{ isProposal ? lineTotal(item) : taxedSubtotal(item) }}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <footer class="share-foot">
        <span>访问次数 {{ share?.access_count ?? 0 }}</span>
        <span>由 RiChangPIM 提供</span>
      </footer>
    </template>

    <ShareSceneDialog :images="sceneOpen ? scenes : null" @close="sceneOpen = false" />
  </main>
</template>
