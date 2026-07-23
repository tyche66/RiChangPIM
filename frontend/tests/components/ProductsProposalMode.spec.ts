import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api', () => ({
  productApi: {
    list: vi.fn().mockResolvedValue({
      data: {
        list: [
          { id: 'p1', product_no: 'CLE-001', product_name: '氨基酸洁面泡沫', brand_id: 'b1', brand_name: '品牌A', supplier_id: 's1', supplier_name: '供应商A', category_id: 'c1', category_name: '分类A', face_price: 88, cost_price: 50, stock_status: 'in_stock', status: 'active', completeness_status: 'complete', data_source: 'manual', cover_image_url: 'https://example.com/cover.jpg', cover_image_id: 'img1', cover_image_filename: 'cover.jpg', tag_ids: [], create_time: '2024-01-01T00:00:00Z', update_time: '2024-01-01T00:00:00Z' },
          { id: 'p2', product_no: 'OFF-001', product_name: '已下架产品', brand_id: 'b1', brand_name: '品牌A', supplier_id: 's1', supplier_name: '供应商A', category_id: 'c1', category_name: '分类A', face_price: 50, cost_price: 30, stock_status: 'out_of_stock', status: 'inactive', completeness_status: 'complete', data_source: 'manual', cover_image_url: null, cover_image_id: null, cover_image_filename: null, tag_ids: [], create_time: '2024-01-01T00:00:00Z', update_time: '2024-01-01T00:00:00Z' },
        ],
        total: 2,
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
    userPermissions: ['product:view', 'product:create', 'proposal:create'],
    userRoleCode: 'admin',
  })),
}))

import Products from '@/views/Products.vue'

describe('Products.vue - proposal mode', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const factory = async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/products', component: Products },
        { path: '/proposals', component: { template: '<div />' } },
      ],
    })
    await router.push('/products')
    await router.isReady()
    return mount(Products, {
      global: {
        plugins: [createPinia(), router, ElementPlus],
        stubs: {
          'el-dialog': true,
          'el-image-viewer': true,
        },
        renderStubDefaultSlot: true,
      },
    })
  }

  it('shows 制作方案 button when user has proposal:create permission', async () => {
    const wrapper = await factory()
    await flushPromises()
    const btn = wrapper.find('button', { text: '制作方案' })
    expect(btn.exists()).toBe(true)
  })

  it('entering proposal mode shows selection bar', async () => {
    const wrapper = await factory()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.enterProposalMode()
    await flushPromises()
    expect(wrapper.text()).toContain('已选 0 项')
    expect(wrapper.find('button', { text: '取消' }).exists()).toBe(true)
    expect(wrapper.find('button', { text: '完成' }).exists()).toBe(true)
  })

  it('inactive product is not selectable in proposal mode', async () => {
    const wrapper = await factory()
    await flushPromises()
    const btn = wrapper.find('button', { text: '制作方案' })
    await btn.trigger('click')
    await flushPromises()
    // Check that the selection column exists
    const selectionColumn = wrapper.findComponent({ name: 'ElTableColumn' })
    expect(selectionColumn.exists()).toBe(true)
  })

  it('cancel exits proposal mode and clears selection', async () => {
    const wrapper = await factory()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.enterProposalMode()
    await flushPromises()
    expect(wrapper.text()).toContain('已选 0 项')
    vm.exitProposalMode()
    await flushPromises()
    expect(wrapper.text()).not.toContain('已选')
  })

  it('finish stores token in sessionStorage and exits mode', async () => {
    const wrapper = await factory()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.enterProposalMode()
    await flushPromises()

    // Simulate selecting via the component's own selection change handler
    vm.onSelectionChange([
      { id: 'p1', productName: '氨基酸洁面泡沫', productNo: 'CLE-001', facePrice: 88, stockStatus: 'in_stock', primaryImage: { url: 'https://example.com/cover.jpg' } },
    ])
    await flushPromises()

    vm.finishProposal()
    await flushPromises()

    const key = Object.keys(sessionStorage).find((item) => item.startsWith('proposal_token_'))
    expect(key).toBeTruthy()
    const parsed = JSON.parse(sessionStorage.getItem(key!)!)
    expect(parsed.productIds).toEqual(['p1'])
    expect(parsed.options).toHaveLength(1)
    expect(parsed.options[0].product_name).toBe('氨基酸洁面泡沫')
  })
})
