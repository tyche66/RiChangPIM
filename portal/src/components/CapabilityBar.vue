<script setup lang="ts">
/**
 * 能力入口条。构图对应 reeoo.com 首屏卡片下方那条分格统计条，
 * 但**不放任何数字**——门户没有可信的统计口径，编造数字比不显示更糟。
 *
 * 交互遵守 AI-Docs/Furnispace-PLP-Design-Skill.md §6.2：只把关键词
 * 预填进查询框，不自动发起查询，最后一步始终由用户按下发送。
 */
const emit = defineEmits<{ pick: [text: string] }>()

type Capability = {
  label: string
  hint: string
  /** lucide 风格的 24×24 单路径图标，避免为了几个图标引入依赖 */
  icon: string
}

const CAPABILITIES: Capability[] = [
  {
    label: '找产品',
    hint: '按型号、场景或材质检索',
    icon: 'M17 17l4 4M11 19a8 8 0 1 1 0-16a8 8 0 0 1 0 16',
  },
  {
    label: '问资料',
    hint: '说明书、图纸与安装文档',
    icon: 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5M9 13h6M9 17h4',
  },
  {
    label: '查质量',
    hint: '检验记录与质量问题',
    icon: 'M12 3l7 3v5c0 4.2-2.9 7.9-7 9c-4.1-1.1-7-4.8-7-9V6zM9 12l2 2l4-4',
  },
  {
    label: '做比较',
    hint: '多个产品参数并排对照',
    icon: 'M4 5h6v14H4zM14 5h6v14h-6z',
  },
]
</script>

<template>
  <nav class="capability-bar" aria-label="常用查询入口">
    <button
      v-for="item in CAPABILITIES"
      :key="item.label"
      type="button"
      class="capability"
      :aria-label="`把「${item.label}」填入查询框`"
      @click="emit('pick', item.label)"
    >
      <span class="capability__icon" aria-hidden="true">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.7"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path :d="item.icon" />
        </svg>
      </span>
      <span class="capability__body">
        <strong>{{ item.label }}</strong>
        <span>{{ item.hint }}</span>
      </span>
      <span class="capability__arrow" aria-hidden="true">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M5 12h14m-7-7l7 7l-7 7" />
        </svg>
      </span>
    </button>
  </nav>
</template>
