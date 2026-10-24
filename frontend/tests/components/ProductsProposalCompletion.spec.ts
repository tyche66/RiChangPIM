import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({
  productApi: {
    list: vi.fn().mockResolvedValue({
      data: {
        list: [{
          id: 'p1', product_no: 'P001', product_name: 'Product one', brand_id: 'b1',
          brand_name: 'Brand', supplier_id: 's1', supplier_name: 'Supplier', category_id: 'c1',
          category_name: 'Category', face_price: 88, cost_price: 50, stock_status: 'in_stock',
          status: 'active', completeness_status: 'complete', data_source: 'manual',
          cover_image_url: null, cover_image_id: null, cover_image_filename: null, tag_ids: [],
          create_time: '2026-01-01T00:00:00Z', update_time: '2026-01-01T00:00:00Z',
        }],
        total: 1,
        page: 1,
        size: 20,
      },
    }),
  },
  categoryApi: { list: vi.fn().mockResolvedValue({ data: [] }) },
  brandApi: { list: vi.fn().mockResolvedValue({ data: { list: [] } }) },
  supplierApi: { list: vi.fn().mockResolvedValue({ data: { list: [] } }) },
  tagApi: { list: vi.fn().mockResolvedValue({ data: { list: [] } }) },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn(() => ({
    userPermissions: ['product:view', 'proposal:create'],
    userRoleCode: 'admin',
  })),
}))

import Products from '@/views/Products.vue'

const errorSpy = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})
const warningSpy = vi.spyOn(ElMessage, 'warning').mockImplementation(() => {})
const successSpy = vi.spyOn(ElMessage, 'success').mockImplementation(() => {})

async function mountProducts() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/products', component: Products },
      { path: '/proposals', component: { template: '<div />' } },
    ],
  })
  await router.push('/products')
  await router.isReady()
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = mount(Products, {
    global: {
      plugins: [pinia, router, ElementPlus],
      stubs: { 'el-dialog': true, 'el-image-viewer': true },
      renderStubDefaultSlot: true,
    },
  })
  await flushPromises()
  return { wrapper, router }
}

describe('product selection completion', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    sessionStorage.clear()
    errorSpy.mockClear()
    warningSpy.mockClear()
    successSpy.mockClear()
  })

  it('opens proposal creation when crypto.randomUUID is unavailable', async () => {
    const { wrapper, router } = await mountProducts()
    const vm = wrapper.vm as any
    vm.enterProposalMode()
    vm.onSelectionChange([{
      id: 'p1', productName: 'Product one', productNo: 'P001', facePrice: 88,
    }])
    vi.stubGlobal('crypto', { randomUUID: undefined })

    await vm.finishProposal()
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/proposals')
    const key = Object.keys(sessionStorage).find((item) => item.startsWith('proposal_token_'))
    expect(key).toBeTruthy()
    expect(JSON.parse(sessionStorage.getItem(key!)!).productIds).toEqual(['p1'])
    expect(successSpy).toHaveBeenCalledWith('已进入方案创建')
  })

  it('shows a visible error and retains selection when token storage fails', async () => {
    const { wrapper, router } = await mountProducts()
    const vm = wrapper.vm as any
    vm.enterProposalMode()
    vm.onSelectionChange([{
      id: 'p1', productName: 'Product one', productNo: 'P001', facePrice: 88,
    }])
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('storage disabled', 'SecurityError')
    })

    await vm.finishProposal()

    expect(errorSpy).toHaveBeenCalledWith('无法打开方案创建页面，请重试')
    expect(router.currentRoute.value.path).toBe('/products')
    expect(vm.proposalMode).toBe(true)
    expect(vm.selectedCount).toBe(1)
    setItem.mockRestore()
  })

  it('warns when finishing without a selected product', async () => {
    const { wrapper } = await mountProducts()
    const vm = wrapper.vm as any
    vm.enterProposalMode()

    await vm.finishProposal()

    expect(warningSpy).toHaveBeenCalledWith('请至少选择一项商品')
  })
})
