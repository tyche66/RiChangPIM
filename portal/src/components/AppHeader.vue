<script setup lang="ts">
/**
 * 顶部品牌栏。整宽显示，不跟随内容列收窄；右侧动作由父级用默认插槽注入。
 *
 * showSubLabel 控制品牌名后面那枚「门户」小字：查询工作台（chat）要把左上角
 * 让位给右上角的「进入后台 / 退出」两个文字入口，所以传 false；登录页和分享
 * 页保持默认 true，不动它们的「门户」字样。
 */
import logoUrl from '../../../logo/RiChangPIM.png'

withDefaults(defineProps<{ showSubLabel?: boolean }>(), { showSubLabel: true })
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
        <slot />
      </div>
    </div>
  </header>
</template>
