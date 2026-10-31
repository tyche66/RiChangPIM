import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
  },
  {
    path: '/',
    redirect: '/products',
    component: () => import('@/layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: 'products',
        name: 'Products',
        component: () => import('@/views/Products.vue'),
        meta: { permissions: ['product:view'], permission: 'product:view' },
      },
      {
        path: 'products/:id',
        name: 'ProductDetail',
        component: () => import('@/views/ProductDetail.vue'),
        meta: { permissions: ['product:view'], permission: 'product:view' },
      },
      {
        path: 'categories',
        name: 'Categories',
        component: () => import('@/views/Categories.vue'),
        meta: { permissions: ['category:view'], permission: 'category:view' },
      },
      {
        path: 'brands',
        name: 'Brands',
        component: () => import('@/views/Brands.vue'),
        meta: { permissions: ['brand:view'], permission: 'brand:view' },
      },
      {
        path: 'suppliers',
        name: 'Suppliers',
        component: () => import('@/views/Suppliers.vue'),
        meta: { permissions: ['supplier:view'], permission: 'supplier:view' },
      },
      {
        path: 'tags',
        name: 'Tags',
        component: () => import('@/views/Tags.vue'),
        meta: { permissions: ['tag:view'], permission: 'tag:view' },
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/Users.vue'),
        meta: { permissions: ['user:view'], permission: 'user:view' },
      },
      {
        path: 'roles',
        name: 'Roles',
        component: () => import('@/views/Roles.vue'),
        meta: { permissions: ['role:view'], permission: 'role:view' },
      },
      {
        path: 'proposals',
        name: 'Proposals',
        component: () => import('@/views/Proposals.vue'),
        meta: { permissions: ['proposal:view'], permission: 'proposal:view' },
      },
      {
        path: 'proposals/:id',
        name: 'ProposalDetail',
        component: () => import('@/views/ProposalDetail.vue'),
        meta: { permissions: ['proposal:view'], permission: 'proposal:view' },
      },
      {
        path: 'quotations',
        name: 'Quotations',
        component: () => import('@/views/Quotations.vue'),
        meta: { permissions: ['quotation:view'], permission: 'quotation:view' },
      },
      {
        path: 'shares',
        name: 'ShareManagement',
        component: () => import('@/views/ShareManagement.vue'),
        meta: { permissions: ['share:view'], permission: 'share:view' },
      },
      {
        path: 'ai-select',
        name: 'AISelect',
        component: () => import('@/views/AISelect.vue'),
        meta: { permissions: ['ai:use'], permission: 'ai:use' },
      },
      {
        path: 'ai/config',
        name: 'AIConfigCenter',
        component: () => import('@/views/AIConfigCenter.vue'),
        meta: {
          permissions: ['ai:config'],
          permission: 'ai:config',
          adminOnly: true,
        },
      },
      {
        path: 'knowledge-index',
        name: 'KnowledgeIndexAdmin',
        component: () => import('@/views/KnowledgeIndexAdmin.vue'),
        meta: {
          permissions: ['knowledge:index'],
          permission: 'knowledge:index',
          adminOnly: true,
        },
      },
      {
        path: 'manuals',
        name: 'Manuals',
        component: () => import('@/views/Manuals.vue'),
        meta: { permissions: ['ai:use', 'product:edit'], permissionsMode: 'any', permission: 'ai:use' },
      },
      {
        path: 'import',
        name: 'Import',
        component: () => import('@/views/Import.vue'),
        meta: { permissions: ['product:import'], permission: 'product:import' },
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/Logs.vue'),
        meta: { permissions: ['stats:view'], permission: 'stats:view' },
      },
      {
        path: 'quality',
        name: 'Quality',
        component: () => import('@/views/Quality.vue'),
        meta: { permissions: ['product:view'], permission: 'product:view' },
      },
      {
        path: 'media',
        name: 'MediaLibrary',
        component: () => import('@/views/MediaLibrary.vue'),
        meta: { permissions: ['media:view'], permission: 'media:view' },
      },
      {
        path: 'scene-images',
        name: 'SceneImages',
        component: () => import('@/views/SceneImages.vue'),
        meta: { permissions: ['scene_image:view'], permission: 'scene_image:view' },
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { permissions: ['dashboard:view'], permission: 'dashboard:view' },
      },
      {
        path: 'customers',
        name: 'Customers',
        component: () => import('@/views/Customers.vue'),
        meta: { permissions: ['customer:view'], permission: 'customer:view' },
      },
      {
        path: 'customers/:id',
        name: 'CustomerDetail',
        component: () => import('@/views/CustomerDetail.vue'),
        meta: { permissions: ['customer:view'], permission: 'customer:view' },
      },
      {
        path: 'projects',
        name: 'Projects',
        component: () => import('@/views/Projects.vue'),
        meta: { permissions: ['project:view'], permission: 'project:view' },
      },
      {
        path: 'projects/:id',
        name: 'ProjectDetail',
        component: () => import('@/views/ProjectDetail.vue'),
        meta: { permissions: ['project:view'], permission: 'project:view' },
      },
      {
        path: 'content/workshop',
        name: 'ContentWorkshop',
        component: () => import('@/views/ContentWorkshop.vue'),
        meta: { permissions: ['content:view'], permission: 'content:view' },
      },
      {
        path: 'content/publications',
        name: 'ContentPublications',
        component: () => import('@/views/ContentPublications.vue'),
        meta: { permissions: ['content:view'], permission: 'content:view' },
      },
      {
        path: 'content/topics',
        name: 'ContentTopics',
        component: () => import('@/views/ContentTopics.vue'),
        meta: { permissions: ['content:view'], permission: 'content:view' },
      },
      {
        path: 'content/skills',
        name: 'ContentSkills',
        component: () => import('@/views/ContentSkills.vue'),
        meta: {
          permissions: ['content:manage'],
          permission: 'content:manage',
          adminOnly: true,
        },
      },
      {
        path: 'version',
        name: 'Version',
        component: () => import('@/views/Version.vue'),
        meta: { permissions: ['stats:view'], permission: 'stats:view' },
      },
    ],
  },
  {
    path: '/share/:token',
    name: 'SharePage',
    component: () => import('@/views/SharePage.vue'),
    meta: { public: true },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  // Ensure auth state is initialized on first navigation.
  if (!authStore.isAuthenticated && localStorage.getItem('token')) {
    await authStore.init()
  }

  const isPublic = to.meta.public === true

  if (isPublic) {
    // Public routes (e.g. share pages) are always accessible.
    next()
    return
  }

  if (!authStore.isAuthenticated) {
    if (to.path !== '/login') {
      next({ path: '/login', query: { redirect: to.fullPath } })
    } else {
      next()
    }
    return
  }

  if (to.path === '/login') {
    const redirect = to.query.redirect as string
    next(redirect || '/products')
    return
  }

  // Admin-only routes: the Skills management centre requires an explicit
  // role_code check so a non-admin can never reach it by URL, even if their
  // permission set is stale. This mirrors the backend guard.
  if (to.meta.adminOnly && authStore.userRoleCode !== 'admin') {
    next({ name: 'Products' })
    return
  }

  // Permission check.
  const requiredPerms: string[] = (to.meta.permissions as string[]) || []
  if (requiredPerms.length > 0) {
    const mode = (to.meta.permissionsMode as 'any' | 'all') || 'any'
    const getHasAccess = () => {
      if (authStore.userRoleCode === 'admin') return true
      const userPerms = authStore.permissions
      return mode === 'all'
        ? requiredPerms.every((p) => userPerms.includes(p))
        : requiredPerms.some((p) => userPerms.includes(p))
    }

    let hasAccess = getHasAccess()

    // Existing sessions can hold a token issued before new permissions were added.
    // Refresh once so route decisions use the latest role-permission mapping.
    if (!hasAccess) {
      const refreshed = await authStore.refresh()
      if (refreshed) {
        hasAccess = getHasAccess()
      }
    }

    if (!hasAccess) {
      next({ name: 'Products' })
      return
    }
  }

  next()
})

export default router
