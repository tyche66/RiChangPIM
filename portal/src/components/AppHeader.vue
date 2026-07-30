<script setup lang="ts">
/**
 * 顶部品牌栏。整宽显示，不跟随内容列收窄；右侧动作由父级用默认插槽注入。
 */
import logoUrl from '../../../logo/RiChangPIM.png'
</script>

<template>
  <header class="site-header">
    <div class="site-header__inner">
      <a class="brand-mark" href="/" aria-label="RiChangPIM 门户首页">
        <span class="brand-mark__badge">
          <img :src="logoUrl" alt="" />
        </span>
        <span>RiChangPIM</span>
        <span class="brand-mark__sub">门户</span>
      </a>
      <div class="site-header__actions">
        <slot />
      </div>
    </div>
  </header>
</template>
