<script setup lang="ts">
/**
 * 顶部品牌栏。整宽显示，不跟随内容列收窄；右侧动作由父级用默认插槽注入。
 *
 * showSubLabel 控制品牌名后面那枚「门户」小字：查询工作台（chat）要把左上角
 * 让位给右上角的「进入后台 / 退出」两个文字入口，所以传 false；登录页和分享
 * 页保持默认 true，不动它们的「门户」字样。
 *
 * 主题开关固定在品牌栏右侧（插槽之前）：深浅两套 logo 资源都在仓库里
 * （RiChangPIM.png 彩色版 / -white 白版），按当前主题切换，与后台侧边栏
 * 用白版 logo 是同一套机制。
 */
import { computed } from 'vue'
import logoColor from '../../../logo/RiChangPIM.png'
import logoWhite from '../../../logo/RiChangPIM-white.png'
import { isDark, toggleTheme } from '@/utils/theme'

withDefaults(defineProps<{ showSubLabel?: boolean }>(), { showSubLabel: true })

const logoUrl = computed(() => (isDark.value ? logoWhite : logoColor))
const themeLabel = computed(() => (isDark.value ? '切换到浅色模式' : '切换到深色模式'))
</script>

<template>
  <header class="site-header">
    <div class="site-header__inner">
      <a class="brand-mark" href="/" :aria-label="showSubLabel ? 'RiChangPIM 门户首页' : 'RiChangPIM 首页'">
        <span class="brand-mark__badge">
          <img :src="logoUrl" alt="" />
        </span>
        <span>RiChangPIM</span>
        <span v-if="showSubLabel" class="brand-mark__sub">门户</span>
      </a>
      <div class="site-header__actions">
        <button
          class="site-header__theme"
          type="button"
          :aria-pressed="isDark"
          :title="themeLabel"
          :aria-label="themeLabel"
          @click="toggleTheme"
        >
          <svg v-if="isDark" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="4.2" />
            <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4" />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
          </svg>
        </button>
        <slot />
      </div>
    </div>
  </header>
</template>
