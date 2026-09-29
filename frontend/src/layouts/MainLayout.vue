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
          <el-menu-item index="/quality">
            数据质量
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
            AI 选品
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
          <div class="header-actions">
            <ThemeToggle />
            <button
              class="user-chip"
              type="button"
              aria-label="账户操作"
              title="账户操作"
              @click="accountDialogVisible = true"
            >
              <span class="avatar">{{ userInitial }}</span>
              <span class="user-copy">
                <small class="user-label">当前用户</small>
                <strong>{{ displayName }}</strong>
              </span>
            </button>
          </div>
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

    <el-dialog
      v-model="accountDialogVisible"
      title="账户"
      width="380px"
      align-center
      class="account-dialog"
    >
      <div class="account-identity">
        <span class="avatar avatar--lg">{{ userInitial }}</span>
        <span class="account-copy">
          <small class="account-label">当前用户</small>
          <strong>{{ displayName }}</strong>
          <small>{{ authStore.userRoleCode || '团队成员' }}</small>
        </span>
      </div>
      <p class="account-hint">
        退出登录会清除本机的登录凭据；切换用户会在登录成功后回到当前页面。
      </p>
      <template #footer>
        <div class="account-actions">
          <el-button
            class="account-btn"
            :loading="accountBusy"
            @click="handleSwitchUser"
          >
            切换用户
          </el-button>
          <el-button
            class="account-btn account-btn--strong"
            :loading="accountBusy"
            @click="handleLogout"
          >
            退出登录
          </el-button>
        </div>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Cpu, Document, DocumentCopy, InfoFilled, Menu, Setting } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import ThemeToggle from '@/components/ThemeToggle.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const mobileMenuOpen = ref(false)
const accountDialogVisible = ref(false)
const accountBusy = ref(false)
const menuRef = ref<{ updateActiveIndex?: (index: string) => void } | null>(null)

const activeMenu = computed(() => route.path)

const subMenuMap: Record<string, string> = {
  products: 'm-products',
  categories: 'm-products',
  brands: 'm-products',
  suppliers: 'm-products',
  tags: 'm-products',
  media: 'm-products',
  'scene-images': 'm-products',
  quality: 'm-products',
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
  categories: ['产品管理', '分类管理'],
  brands: ['产品管理', '品牌管理'],
  suppliers: ['产品管理', '供应商'],
  tags: ['产品管理', '标签管理'],
  media: ['产品管理', '媒体库'],
  'scene-images': ['产品管理', '场景图管理'],
  quality: ['产品管理', '数据质量'],
  proposals: ['销售管理', '方案管理'],
  quotations: ['销售管理', '报价管理'],
  users: ['系统管理', '用户管理'],
  roles: ['系统管理', '角色权限'],
  shares: ['系统管理', '分享管理'],
  logs: ['系统管理', '操作日志'],
  'ai-select': ['AI 功能', 'AI 选品'],
  manuals: ['AI 功能', '产品知识库'],
  import: ['AI 功能', '批量导入'],
  version: ['系统信息', '版本'],
}
const currentLabels = computed(() => routeLabels[route.path.split('/')[1]] || ['工作台', 'AI-PIM'])
const pageSection = computed(() => currentLabels.value[0])
const pageTitle = computed(() => route.params.id ? `${currentLabels.value[1]}详情` : currentLabels.value[1])
// 顶栏只显示真实用户名。「当前用户」是标签，不参与占位——不用它冒名顶替真实用户名。
// profileResolved 标记「/auth/me 这一轮已经跑完」：ensureUser() 失败是静默的
// （stores/auth.ts:114-119），跑完还拿不到 profile 就必须把文案从「加载中…」切走，
// 否则会永久显示加载中骗用户。这里给中性文案，不编造名字、也不把 JWT 里的 uuid 摊给用户看。
const profileResolved = ref(false)
const displayName = computed(() => {
  const name = authStore.currentUser?.username
  if (name) return name
  return profileResolved.value ? '未知用户' : '加载中…'
})
const userInitial = computed(() => (authStore.currentUser?.username || 'AI').slice(0, 1).toUpperCase())

watch(() => route.fullPath, () => {
  mobileMenuOpen.value = false
  syncMenuActive()
})

// 顶栏要显示用户名，profile 可能还没被 init() 拉到（例如刷新时 /auth/me 抖动）。
// 无论成功失败都要落 profileResolved，否则失败分支会把「加载中…」钉死在顶栏。
onMounted(async () => {
  try {
    if (!authStore.currentUser) await authStore.ensureUser()
  } finally {
    profileResolved.value = true
  }
})

const handleLogout = async () => {
  accountBusy.value = true
  try {
    await authStore.logout()
  } finally {
    accountBusy.value = false
    accountDialogVisible.value = false
  }
  router.push('/login')
}

/** 切换用户＝退出后带上当前路径，另一个账号登录成功后回到同一页。 */
const handleSwitchUser = async () => {
  const redirect = route.fullPath
  accountBusy.value = true
  try {
    await authStore.logout()
  } finally {
    accountBusy.value = false
    accountDialogVisible.value = false
  }
  router.push({ path: '/login', query: { redirect } })
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
  display: flex;
  align-items: center;
}

.header-content {
  flex: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
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
  /* 用户名长度不可控，给个上限并省略号收尾，免得把标题挤换行。 */
  max-width: 168px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* 标签行：字号/字距对齐同文件的 .eyebrow，视觉上弱于用户名。 */
.user-copy small {
  color: rgba(30, 50, 90, 0.48);
  font-size: 10px;
  letter-spacing: 0.14em;
  white-space: nowrap;
}

.account-identity {
  display: flex;
  align-items: center;
  gap: 14px;
}

.avatar--lg {
  width: 52px;
  height: 52px;
  font-size: 20px;
  font-weight: 500;
}

.account-copy {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.account-copy strong {
  color: rgba(30, 50, 90, 0.92);
  font-size: 17px;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.account-copy small {
  color: rgba(30, 50, 90, 0.5);
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.account-hint {
  margin: 16px 0 0;
  color: rgba(30, 50, 90, 0.56);
  font-size: 12px;
  line-height: 1.7;
}

.account-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.account-btn--strong {
  border-color: rgb(30, 50, 90);
  background: rgb(30, 50, 90);
  color: #fff;
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

  .eyebrow {
    display: none;
  }

  /* 小屏只隐藏「当前用户」标签行，用户名必须留着——不然移动端看不出登录的是谁。 */
  .user-copy small {
    display: none;
  }

  /* 顶栏宽度只剩 375-2*8-2*12=335px，用户名限宽收窄，给标题留出不换行的空间。 */
  .user-copy strong {
    max-width: 76px;
  }

  .header-heading h1 {
    font-size: 20px;
  }

  .user-chip {
    /* 小屏仍要显示用户名，右侧留出内边距，别让文字贴着 chip 边缘。 */
    padding: 3px 10px 3px 3px;
    gap: 8px;
  }

  .avatar {
    width: 38px;
    height: 38px;
  }

  .el-main {
    padding-top: 10px;
  }
}

/* 深色模式覆盖 */
:global(.dark-mode) .el-header {
  border-color: rgba(255, 255, 255, 0.1);
  background: rgba(25, 39, 68, 0.72);
  box-shadow: 0 14px 45px rgba(0, 0, 0, 0.2);
}

:global(.dark-mode) .eyebrow {
  color: rgba(244, 244, 244, 0.48);
}

:global(.dark-mode) .header-heading h1 {
  color: rgba(244, 244, 244, 0.9);
}

:global(.dark-mode) .menu-toggle,
:global(.dark-mode) .user-chip {
  color: rgba(244, 244, 244, 0.8);
}

:global(.dark-mode) .menu-toggle {
  background: rgba(244, 244, 244, 0.08);
}

:global(.dark-mode) .user-chip {
  background: rgba(244, 244, 244, 0.12);
}

:global(.dark-mode) .user-copy strong {
  color: rgba(244, 244, 244, 0.88);
}

:global(.dark-mode) .user-copy small {
  color: rgba(244, 244, 244, 0.48);
}

:global(.dark-mode) .account-copy strong {
  color: rgba(244, 244, 244, 0.92);
}

:global(.dark-mode) .account-copy small {
  color: rgba(244, 244, 244, 0.5);
}

:global(.dark-mode) .account-hint {
  color: rgba(244, 244, 244, 0.56);
}

:global(.dark-mode) .account-btn--strong {
  border-color: rgb(244, 244, 244);
  background: rgb(244, 244, 244);
  color: rgb(25, 39, 68);
}
</style>
