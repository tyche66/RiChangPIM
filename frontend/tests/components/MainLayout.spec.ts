import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({
  authApi: {
    login: vi.fn(),
    logout: vi.fn().mockResolvedValue({}),
    getCurrentUser: vi.fn().mockResolvedValue({}),
    refresh: vi.fn(),
  },
}))

import { useAuthStore } from '@/stores/auth'
import MainLayout from '@/layouts/MainLayout.vue'

const ADMIN = {
  id: 'u1',
  username: 'admin',
  email: null,
  phone: null,
  status: 'active',
  role_id: 'r1',
  last_login_time: null,
  create_time: '2026-07-01T00:00:00',
}

async function mountLayout() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const authStore = useAuthStore(pinia)
  authStore.user = ADMIN
  authStore.roleCode = 'admin'

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/products', component: { render: () => null } },
      { path: '/login', component: { render: () => null } },
    ],
  })
  await router.push('/products')
  await router.isReady()

  const wrapper = mount(MainLayout, {
    global: {
      plugins: [pinia, router, ElementPlus],
      // el-menu 的子菜单/popper 在 jsdom 里既慢又无关本用例，整块 stub 掉；
      // 被断言的顶栏 chip 和账户弹窗仍用真实 Element Plus 组件。
      stubs: { ElMenu: true, ElSubMenu: true, ElMenuItem: true },
    },
  })
  await flushPromises()
  // el-dialog 的 append-to-body 默认是 false，弹窗渲染在组件树里而不是 document.body，
  // 所以按钮统一从 wrapper 里找。
  const button = (label: string) => wrapper.findAll('button').find((b) => b.text().includes(label))
  return { wrapper, authStore, router, button }
}

describe('MainLayout 顶栏账户区', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('顶栏同时显示「当前用户」标签和用户名', async () => {
    const { wrapper } = await mountLayout()
    const chip = wrapper.get('button[aria-label="账户操作"]')
    expect(chip.text()).toContain('当前用户')
    expect(chip.text()).toContain('admin')
  })

  it('点 chip 只打开弹窗，不会直接退出登录', async () => {
    const { wrapper, authStore, router, button } = await mountLayout()
    const logoutSpy = vi.spyOn(authStore, 'logout').mockResolvedValue(undefined)

    // 没点之前弹窗根本不存在，确认下面的按钮是这一次点击带出来的。
    expect(button('退出登录')).toBeUndefined()

    await wrapper.get('button[aria-label="账户操作"]').trigger('click')
    await flushPromises()

    // T08 的真正断言：点一下顶栏不等于退出登录。
    expect(logoutSpy).not.toHaveBeenCalled()
    expect(wrapper.find('.el-dialog').isVisible()).toBe(true)
    expect(button('退出登录')).toBeTruthy()
    expect(button('切换用户')).toBeTruthy()
    expect(router.currentRoute.value.path).toBe('/products')
  })

  it('弹窗里点「退出登录」才真的退出并回登录页', async () => {
    const { wrapper, authStore, router, button } = await mountLayout()
    const logoutSpy = vi.spyOn(authStore, 'logout').mockResolvedValue(undefined)

    await wrapper.get('button[aria-label="账户操作"]').trigger('click')
    await flushPromises()
    await button('退出登录')!.trigger('click')
    await flushPromises()

    expect(logoutSpy).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('「切换用户」带上当前路径，登录后能回到原页面', async () => {
    const { wrapper, authStore, router, button } = await mountLayout()
    const logoutSpy = vi.spyOn(authStore, 'logout').mockResolvedValue(undefined)

    await wrapper.get('button[aria-label="账户操作"]').trigger('click')
    await flushPromises()
    await button('切换用户')!.trigger('click')
    await flushPromises()

    expect(logoutSpy).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/products')
  })

  it('/auth/me 拉不到用户时文案落到「未知用户」，不会永久停在加载中', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore(pinia)
    // 模拟真实失败路径：ensureUser() 静默返回 null，user 一直是空。
    vi.spyOn(authStore, 'ensureUser').mockResolvedValue(null)

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/products', component: { render: () => null } },
        { path: '/login', component: { render: () => null } },
      ],
    })
    await router.push('/products')
    await router.isReady()

    const wrapper = mount(MainLayout, {
      global: {
        plugins: [pinia, router, ElementPlus],
        stubs: { ElMenu: true, ElSubMenu: true, ElMenuItem: true },
      },
    })
    await flushPromises()

    const chip = wrapper.get('button[aria-label="账户操作"]')
    expect(chip.text()).toContain('未知用户')
    expect(chip.text()).not.toContain('加载中')
  })
})
