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
        meta: { permissions: ['product:view'] },
      },
      {
        path: 'products/:id',
        name: 'ProductDetail',
        component: () => import('@/views/ProductDetail.vue'),
        meta: { permissions: ['product:view'] },
      },
      {
        path: 'categories',
        name: 'Categories',
        component: () => import('@/views/Categories.vue'),
        meta: { permissions: ['category:view'] },
      },
      {
        path: 'brands',
        name: 'Brands',
        component: () => import('@/views/Brands.vue'),
        meta: { permissions: ['brand:view'] },
      },
      {
        path: 'suppliers',
        name: 'Suppliers',
        component: () => import('@/views/Suppliers.vue'),
        meta: { permissions: ['supplier:view'] },
      },
      {
        path: 'tags',
        name: 'Tags',
        component: () => import('@/views/Tags.vue'),
        meta: { permissions: ['tag:view'] },
      },
      {
        path: 'users',
        name: 'Users',
        component: () => import('@/views/Users.vue'),
        meta: { permissions: ['user:view'] },
      },
      {
        path: 'roles',
        name: 'Roles',
        component: () => import('@/views/Roles.vue'),
        meta: { permissions: ['role:view'] },
      },
      {
        path: 'proposals',
        name: 'Proposals',
        component: () => import('@/views/Proposals.vue'),
        meta: { permissions: ['proposal:view'] },
      },
      {
        path: 'proposals/:id',
        name: 'ProposalDetail',
        component: () => import('@/views/ProposalDetail.vue'),
        meta: { permissions: ['proposal:view'] },
      },
      {
        path: 'quotations',
        name: 'Quotations',
        component: () => import('@/views/Quotations.vue'),
        meta: { permissions: ['quotation:view'] },
      },
      {
        path: 'shares',
        name: 'ShareManagement',
        component: () => import('@/views/ShareManagement.vue'),
        meta: { permissions: ['share:view'] },
      },
      {
        path: 'ai-select',
        name: 'AISelect',
        component: () => import('@/views/AISelect.vue'),
        meta: { permissions: ['ai:use'] },
      },
      {
        path: 'manuals',
        name: 'Manuals',
        component: () => import('@/views/Manuals.vue'),
        meta: { permissions: ['ai:use', 'product:edit'], permissionsMode: 'any' },
      },
      {
        path: 'import',
        name: 'Import',
        component: () => import('@/views/Import.vue'),
        meta: { permissions: ['product:import'] },
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/Logs.vue'),
        meta: { permissions: ['stats:view'] },
      },
      {
        path: 'quality',
        name: 'Quality',
        component: () => import('@/views/Quality.vue'),
        meta: { permissions: ['product:view'] },
      },
      {
        path: 'media',
        name: 'MediaLibrary',
        component: () => import('@/views/MediaLibrary.vue'),
        meta: { permissions: ['media:view'] },
      },
      {
        path: 'scene-images',
        name: 'SceneImages',
        component: () => import('@/views/SceneImages.vue'),
        meta: { permissions: ['scene_image:view'] },
      },
      {
        path: 'version',
        name: 'Version',
        component: () => import('@/views/Version.vue'),
        meta: { permissions: ['stats:view'] },
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
  history: createWebHistory(),
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
