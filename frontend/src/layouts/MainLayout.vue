<template>
  <el-container class="main-layout">
    <div
      v-if="mobileMenuOpen"
      class="nav-backdrop"
      @click="mobileMenuOpen = false"
    />
    <el-aside
      class="sidebar"
      :class="{ 'is-open': mobileMenuOpen }"
      width="248px"
    >
      <div class="logo">
        <img
          class="logo-img"
          src="/RiChangPIM-white.png"
          alt="AI-PIM"
        >
      </div>
      <el-menu
        ref="menuRef"
        :default-active="activeMenu"
        :default-openeds="defaultOpenedMenus"
        background-color="transparent"
        text-color="rgba(255, 255, 255, 0.7)"
        active-text-color="#ffffff"
        @select="handleMenuSelect"
      >
        <el-sub-menu index="m-products">
          <template #title>
            <el-icon><Document /></el-icon>
            <span>产品管理</span>
          </template>
          <el-menu-item index="/products">
            产品列表
          </el-menu-item>
          <el-menu-item index="/quality">
            数据质量
          </el-menu-item>
          <el-menu-item index="/categories">
            分类管理
          </el-menu-item>
          <el-menu-item index="/brands">
            品牌管理
          </el-menu-item>
          <el-menu-item index="/suppliers">
            供应商
          </el-menu-item>
          <el-menu-item index="/tags">
            标签管理
          </el-menu-item>
          <el-menu-item index="/media">
            媒体库
          </el-menu-item>
          <el-menu-item index="/scene-images">
            场景图管理
          </el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="m-sales">
          <template #title>
            <el-icon><DocumentCopy /></el-icon>
            <span>销售管理</span>
          </template>
          <el-menu-item index="/proposals">
            方案管理
          </el-menu-item>
          <el-menu-item index="/quotations">
            报价管理
          </el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="m-admin">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/users">
            用户管理
          </el-menu-item>
          <el-menu-item index="/roles">
            角色权限
          </el-menu-item>
          <el-menu-item index="/shares">
            分享管理
          </el-menu-item>
          <el-menu-item index="/logs">
            操作日志
          </el-menu-item>
        </el-sub-menu>
        <el-sub-menu index="m-ai">
          <template #title>
            <el-icon><Cpu /></el-icon>
            <span>AI 功能</span>
          </template>
          <el-menu-item index="/ai-select">
            AI 智能选品
          </el-menu-item>
          <el-menu-item index="/manuals">
            产品知识库
          </el-menu-item>
          <el-menu-item index="/import">
            批量导入
          </el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/version">
          <el-icon><InfoFilled /></el-icon>
          <span>版本</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>
        <div class="header-content">
          <div class="header-heading">
            <button
              class="menu-toggle"
              type="button"
              aria-label="打开导航菜单"
              @click="mobileMenuOpen = true"
            >
              <el-icon><Menu /></el-icon>
            </button>
            <div>
              <span class="eyebrow">WORKSPACE / {{ pageSection }}</span>
              <h1>{{ pageTitle }}</h1>
            </div>
          </div>
          <button
            class="user-chip"
            type="button"
            aria-label="退出"
            title="退出登录"
            @click="handleLogout"
          >
            <span class="avatar">{{ userInitial }}</span>
            <span class="user-copy">
              <strong>{{ authStore.currentUser?.username || '当前用户' }}</strong>
              <small>{{ authStore.userRoleCode || '团队成员' }}</small>
            </span>
          </button>
        </div>
      </el-header>
      <el-main>
        <router-view v-slot="{ Component }">
          <transition
            name="content"
            mode="out-in"
          >
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Cpu, Document, DocumentCopy, InfoFilled, Menu, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const mobileMenuOpen = ref(false)
const menuRef = ref<{ updateActiveIndex?: (index: string) => void } | null>(null)

const activeMenu = computed(() => route.path)

const subMenuMap: Record<string, string> = {
  products: 'm-products',
  quality: 'm-products',
  categories: 'm-products',
  brands: 'm-products',
  suppliers: 'm-products',
  tags: 'm-products',
  media: 'm-products',
  'scene-images': 'm-products',
  proposals: 'm-sales',
  quotations: 'm-sales',
  users: 'm-admin',
  roles: 'm-admin',
  shares: 'm-admin',
  logs: 'm-admin',
  'ai-select': 'm-ai',
  manuals: 'm-ai',
  import: 'm-ai',
}
const defaultOpenedMenus = computed(() => {
  const key = route.path.split('/')[1]
  const parent = subMenuMap[key]
  return parent ? [parent] : []
})

const syncMenuActive = async () => {
  await nextTick()
  menuRef.value?.updateActiveIndex?.(route.path)
}

const handleMenuSelect = async (index: string) => {
  mobileMenuOpen.value = false
  if (!index.startsWith('/')) return

  try {
    await router.push(index)
  } finally {
    await syncMenuActive()
  }
}

const routeLabels: Record<string, [string, string]> = {
  products: ['产品管理', '产品列表'],
  quality: ['产品管理', '数据质量'],
  categories: ['产品管理', '分类管理'],
  brands: ['产品管理', '品牌管理'],
  suppliers: ['产品管理', '供应商'],
  tags: ['产品管理', '标签管理'],
  media: ['产品管理', '媒体库'],
  'scene-images': ['产品管理', '场景图管理'],
  proposals: ['销售管理', '方案管理'],
  quotations: ['销售管理', '报价管理'],
  users: ['系统管理', '用户管理'],
  roles: ['系统管理', '角色权限'],
  shares: ['系统管理', '分享管理'],
  logs: ['系统管理', '操作日志'],
  'ai-select': ['AI 功能', '智能选品'],
  manuals: ['AI 功能', '产品知识库'],
  import: ['AI 功能', '批量导入'],
  version: ['系统信息', '版本'],
}
const currentLabels = computed(() => routeLabels[route.path.split('/')[1]] || ['工作台', 'AI-PIM'])
const pageSection = computed(() => currentLabels.value[0])
const pageTitle = computed(() => route.params.id ? `${currentLabels.value[1]}详情` : currentLabels.value[1])
const userInitial = computed(() => (authStore.currentUser?.username || 'AI').slice(0, 1).toUpperCase())

watch(() => route.fullPath, () => {
  mobileMenuOpen.value = false
  syncMenuActive()
})

const handleLogout = async () => {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.main-layout {
  min-height: 100vh;
  padding: 12px;
  background: transparent;
}

.sidebar {
  position: sticky;
  top: 12px;
  height: calc(100vh - 24px);
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 32px;
  background:
    radial-gradient(circle at 20% 0, rgba(255, 255, 255, 0.12), transparent 18rem),
    rgb(30, 50, 90);
  color: #fff;
  box-shadow: 0 24px 70px rgba(30, 50, 90, 0.2);
  overflow: hidden;
}

.sidebar :deep(.el-menu) {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.sidebar :deep(.el-menu::-webkit-scrollbar) {
  display: none;
}

.logo-img {
  height: 38px;
  width: auto;
  display: block;
}

.logo {
  height: 86px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 0 20px;
  color: #fff;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.logo-mark,
.avatar {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  flex: 0 0 auto;
  border-radius: 50%;
}

.logo-mark {
  background: rgba(255, 255, 255, 0.16);
  font-size: 13px;
  letter-spacing: 0.08em;
}

.sidebar :deep(.el-sub-menu__title),
.sidebar :deep(.el-menu-item) {
  margin: 4px 0;
  border-radius: 14px;
}

.sidebar :deep(.el-menu-item.is-active) {
  background: rgba(255, 255, 255, 0.14);
}

.sidebar :deep(.el-sub-menu__title:hover),
.sidebar :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.09);
}

.el-header {
  height: 86px;
  margin-left: 12px;
  padding: 0 24px;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: 0 14px 45px rgba(30, 50, 90, 0.06);
  backdrop-filter: blur(20px);
  display: flex;
  align-items: center;
}

.header-content {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-heading,
.user-chip {
  display: flex;
  align-items: center;
}

.header-heading {
  gap: 12px;
}

.eyebrow {
  display: block;
  margin-bottom: 4px;
  color: rgba(30, 50, 90, 0.48);
  font-size: 10px;
  letter-spacing: 0.14em;
}

.header-heading h1 {
  color: rgba(30, 50, 90, 0.9);
  font-size: clamp(20px, 2vw, 28px);
  font-weight: 400;
  line-height: 1.05;
  letter-spacing: -0.03em;
}

.menu-toggle,
.user-chip {
  border: 0;
  color: rgba(30, 50, 90, 0.8);
  cursor: pointer;
}

.menu-toggle {
  display: none;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: 50%;
  background: rgba(30, 50, 90, 0.08);
}

.user-chip {
  gap: 10px;
  padding: 6px 10px 6px 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.6);
}

.avatar {
  color: #fff;
  background: rgba(30, 50, 90, 0.82);
}

.user-copy {
  display: grid;
  gap: 2px;
  text-align: left;
}

.user-copy strong {
  color: rgba(30, 50, 90, 0.88);
  font-size: 13px;
  font-weight: 400;
}

.user-copy small {
  color: rgba(30, 50, 90, 0.48);
  font-size: 10px;
  text-transform: uppercase;
}

.el-main {
  padding: 16px 0 0 12px;
  overflow-x: hidden;
}

.content-enter-active,
.content-leave-active {
  transition: opacity 220ms ease, transform 220ms ease;
}

.content-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.content-leave-to {
  opacity: 0;
}

.nav-backdrop {
  display: none;
}

@media (max-width: 1023px) {
  .main-layout {
    padding: 8px;
  }

  .sidebar {
    position: fixed;
    z-index: 2002;
    top: 8px;
    left: 8px;
    height: calc(100vh - 16px);
    transform: translateX(calc(-100% - 20px));
    transition: transform 260ms ease;
  }

  .sidebar.is-open {
    transform: translateX(0);
  }

  .nav-backdrop {
    position: fixed;
    z-index: 2001;
    inset: 0;
    display: block;
    background: rgba(30, 50, 90, 0.24);
    backdrop-filter: blur(5px);
  }

  .menu-toggle {
    display: grid;
  }

  .el-header {
    margin-left: 0;
  }

  .el-main {
    padding-left: 0;
  }
}

@media (max-width: 600px) {
  .el-header {
    height: 72px;
    padding: 0 12px;
    border-radius: 22px;
  }

  .eyebrow,
  .user-copy {
    display: none;
  }

  .header-heading h1 {
    font-size: 20px;
  }

  .user-chip {
    padding: 3px;
  }

  .avatar {
    width: 38px;
    height: 38px;
  }

  .el-main {
    padding-top: 10px;
  }
}
</style>
