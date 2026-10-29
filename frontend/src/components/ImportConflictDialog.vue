<template>
  <el-dialog
    :model-value="modelValue"
    title="导入预检：这次重传会发生什么"
    class="glass-dialog import-conflict-dialog"
    append-to-body
    lock-scroll
    :close-on-click-modal="false"
    width="820px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template v-if="preflight">
      <el-alert
        v-if="preflight.existing_count > 0"
        type="warning"
        :closable="false"
        class="preflight-alert"
      >
        <template #title>
          将影响 {{ preflight.existing_count }} 个已存在的产品编号
          <template v-if="conflictWithImages > 0">
            （其中 {{ conflictWithImages }} 个带图片，覆盖模式下图片会整套替换）
          </template>
        </template>
      </el-alert>
      <el-alert
        v-else
        type="success"
        :closable="false"
        class="preflight-alert"
      >
        <template #title>
          全部是新增产品，确认后直接导入 {{ preflight.new_count }} 条
        </template>
      </el-alert>

      <div class="stat-grid">
        <div class="stat">
          <span class="stat__label">新增</span>
          <strong class="stat__value stat__value--new">{{ preflight.new_count }}</strong>
        </div>
        <div class="stat">
          <span class="stat__label">已存在</span>
          <strong class="stat__value stat__value--exists">{{ preflight.existing_count }}</strong>
        </div>
        <div class="stat">
          <span class="stat__label">无法导入</span>
          <strong class="stat__value stat__value--invalid">{{ preflight.invalid_count }}</strong>
        </div>
        <div class="stat">
          <span class="stat__label">表格行数</span>
          <strong class="stat__value">{{ preflight.total_rows }}</strong>
        </div>
      </div>

      <div class="mode-block">
        <p class="mode-block__title">
          已存在的产品怎么处理？
        </p>
        <el-radio-group
          v-model="mode"
          class="mode-group"
        >
          <el-radio
            value="overwrite"
            class="mode-option"
          >
            <span class="mode-option__name">覆盖</span>
            <span class="mode-option__hint">
              表格里有值的字段才覆盖，空白单元格保留原值；图片整套替换
            </span>
          </el-radio>
          <el-radio
            value="append"
            class="mode-option"
          >
            <span class="mode-option__name">追加信息</span>
            <span class="mode-option__hint">
              只补库里为空的字段，已有内容不动；图片与标签只增不减
            </span>
          </el-radio>
          <el-radio
            value="skip"
            class="mode-option"
          >
            <span class="mode-option__name">跳过</span>
            <span class="mode-option__hint">
              只导入新增编号，已存在的产品完全不动
            </span>
          </el-radio>
        </el-radio-group>

        <el-checkbox
          v-if="mode !== 'skip'"
          v-model="backup"
          class="mode-backup"
        >
          覆盖前把受影响产品的原值导出成快照（可用 backup_id 回滚）
        </el-checkbox>
      </div>

      <div
        v-if="preflight.new_tag_count > 0"
        class="tag-block"
      >
        <p class="tag-block__title">
          将新建 {{ preflight.new_tag_count }} 个标签
          <span class="muted">（系统里还没有这些名字）</span>
        </p>
        <div class="tag-list">
          <el-tag
            v-for="tag in preflight.new_tags.slice(0, 12)"
            :key="`${tag.name}-${tag.tag_type || ''}`"
            size="small"
            type="info"
          >
            {{ tag.name }}
          </el-tag>
          <span
            v-if="preflight.new_tag_count > Math.min(preflight.new_tags.length, 12)"
            class="muted"
          >
            等 {{ preflight.new_tag_count }} 个
          </span>
        </div>
        <div class="tag-type">
          <span class="tag-type__label">没写类型的标签归入</span>
          <el-radio-group
            v-model="newTagType"
            size="small"
          >
            <el-radio-button value="series">
              系列
            </el-radio-button>
            <el-radio-button value="none">
              未分组
            </el-radio-button>
          </el-radio-group>
        </div>
        <p class="muted tag-hint">
          想逐个指定类型，在表格里写成「系列:摩耳」「风格:新中式」；已有同名标签会直接复用，不会重复创建。
        </p>
      </div>

      <div
        v-if="preflight.conflicts.length"
        class="conflict-block"
      >
        <p class="conflict-block__title">
          冲突示例
          <span class="muted">
            共 {{ preflight.existing_count }} 条
            <template v-if="preflight.conflicts_truncated">
              ，这里只显示前 {{ preflight.conflicts.length }} 条
            </template>
          </span>
        </p>
        <el-table
          :data="preflight.conflicts.slice(0, 20)"
          border
          size="small"
          max-height="240"
        >
          <el-table-column
            prop="row"
            label="行号"
            width="72"
            align="center"
            class-name="cell-num"
          />
          <el-table-column
            prop="product_no"
            label="产品编号"
            width="150"
            class-name="cell-code"
          />
          <el-table-column
            prop="product_name"
            label="表内名称"
            min-width="150"
            show-overflow-tooltip
            class-name="cell-meta"
          />
          <el-table-column
            prop="existing_name"
            label="系统内名称"
            min-width="150"
            show-overflow-tooltip
            class-name="cell-meta"
          />
          <el-table-column
            prop="existing_image_count"
            label="现有图片"
            width="90"
            align="center"
            class-name="cell-num"
          />
        </el-table>
      </div>

      <div
        v-if="preflight.invalid.length"
        class="conflict-block"
      >
        <p class="conflict-block__title">
          无法导入的行（任何模式都不会写入）
          <span class="muted">共 {{ preflight.invalid_count }} 条</span>
        </p>
        <ul class="invalid-list">
          <li
            v-for="item in preflight.invalid.slice(0, 10)"
            :key="`${item.row}-${item.product_no}`"
          >
            <span class="cell-code">第 {{ item.row }} 行</span>
            <span class="cell-meta">{{ item.product_no || '（无编号）' }}</span>
            <span class="invalid-reason">{{ item.reason }}</span>
          </li>
        </ul>
        <p
          v-if="preflight.invalid.length > 10"
          class="muted"
        >
          还有 {{ preflight.invalid_count - 10 }} 条，导入后可在结果里看完整明细。
        </p>
      </div>

      <p class="preflight-footnote">
        「空白 = 不改」：覆盖与追加都只处理表格里真的填了值的单元格，
        留空不会把库里已有的名称、面价、状态清掉。
      </p>
    </template>

    <template #footer>
      <el-button
        class="capsule-btn"
        :disabled="confirming"
        @click="emit('cancel')"
      >
        取消
      </el-button>
      <el-button
        type="primary"
        class="capsule-btn capsule-btn-primary"
        :loading="confirming"
        :disabled="!preflight"
        @click="onConfirm"
      >
        {{ confirmLabel }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ImportMode, ImportPreflightPayload } from '@/api'

const props = defineProps<{
  modelValue: boolean
  preflight: ImportPreflightPayload | null
  confirming?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: [payload: { mode: ImportMode; backup: boolean; new_tag_type: string }]
  cancel: []
}>()

// 默认「覆盖」：重传修图的真实意图多半就是用新包覆盖旧数据；但按钮上写明
// 影响数量，避免误点。用户也可以改选跳过 / 追加。
const mode = ref<ImportMode>('overwrite')
const backup = ref(true)
// 没在单元格里写类型的新标签归到哪一类。默认「系列」：供应商产品包里的新标签
// 绝大多数是新系列（如摩耳），而通用标签（热销/新品）通常早就存在、会被复用。
const newTagType = ref<'series' | 'none'>('series')

watch(
  () => props.preflight,
  (value) => {
    if (value) {
      mode.value = value.existing_count > 0 ? 'overwrite' : 'skip'
      backup.value = true
      newTagType.value = value.new_tag_type_default === 'none' ? 'none' : 'series'
    }
  },
)

const conflictWithImages = computed(
  () => props.preflight?.conflicts.filter((row) => row.existing_image_count > 0).length || 0,
)

const confirmLabel = computed(() => {
  const total = props.preflight
  if (!total) return '开始导入'
  if (total.existing_count === 0) return `导入 ${total.new_count} 个新产品`
  if (mode.value === 'overwrite') {
    return `覆盖 ${total.existing_count} 个产品并导入 ${total.new_count} 个新增`
  }
  if (mode.value === 'append') {
    return `追加到 ${total.existing_count} 个产品并导入 ${total.new_count} 个新增`
  }
  return `跳过已存在，只导入 ${total.new_count} 个新增`
})

function onConfirm() {
  emit('confirm', { mode: mode.value, backup: backup.value, new_tag_type: newTagType.value })
}
</script>

<style scoped>
.preflight-alert {
  margin-bottom: 14px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid var(--pim-line-strong);
  border-radius: var(--pim-radius-sm);
  background: var(--pim-surface-soft);
}

.stat__label {
  font-size: 12px;
  color: var(--pim-text-soft);
}

.stat__value {
  font-size: 20px;
  font-weight: 700;
  color: var(--pim-text-strong);
  font-variant-numeric: tabular-nums;
}

.stat__value--new {
  color: var(--pim-success);
}

.stat__value--exists {
  color: var(--pim-warning-ink);
}

.stat__value--invalid {
  color: var(--pim-danger);
}

.mode-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.mode-block__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--pim-text-strong);
}

.mode-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: stretch;
}

.mode-option {
  height: auto;
  margin-right: 0;
  padding: 8px 10px;
  border: 1px solid var(--pim-line-strong);
  border-radius: var(--pim-radius-sm);
  background: var(--pim-surface-strong);
}

.mode-option :deep(.el-radio__label) {
  display: flex;
  flex-direction: column;
  gap: 2px;
  white-space: normal;
  line-height: 1.5;
}

.mode-option__name {
  font-weight: 600;
}

.mode-option__hint {
  font-size: 12px;
  color: var(--pim-text-soft);
}

.mode-backup {
  margin-left: 2px;
}

.tag-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid var(--pim-line-strong);
  border-radius: var(--pim-radius-sm);
  background: var(--pim-surface-soft);
}

.tag-block__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--pim-text-strong);
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag-type {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.tag-type__label {
  font-size: 12.5px;
  color: var(--pim-text-soft);
}

.tag-hint {
  margin: 0;
  line-height: 1.6;
}

.conflict-block {
  margin-bottom: 14px;
}

.conflict-block__title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.invalid-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-left: 0;
  list-style: none;
  font-size: 12.5px;
}

.invalid-list li {
  display: flex;
  gap: 10px;
  align-items: baseline;
  flex-wrap: wrap;
}

.invalid-reason {
  color: var(--pim-danger-ink);
}

.preflight-footnote {
  padding: 10px 12px;
  border-radius: var(--pim-radius-sm);
  background: var(--pim-surface-soft);
  color: var(--pim-text-soft);
  font-size: 12.5px;
  line-height: 1.6;
}

.muted {
  color: var(--pim-text-soft);
  font-size: 12px;
  font-weight: 400;
}

@media (max-width: 768px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
