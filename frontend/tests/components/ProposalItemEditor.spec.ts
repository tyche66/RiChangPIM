import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { ElSelect } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({
  productApi: {
    list: vi.fn(),
    get: vi.fn(),
  },
  proposalApi: {
    list: vi.fn().mockResolvedValue({ data: { list: [] } }),
    get: vi.fn(),
    create: vi.fn(),
  },
  shareApi: { create: vi.fn() },
}))

import { productApi } from '@/api'
import ProposalItemEditor from '@/components/ProposalItemEditor.vue'

const mockList = productApi.list as ReturnType<typeof vi.fn>
const mockGet = productApi.get as ReturnType<typeof vi.fn>

describe('ProposalItemEditor.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const factory = async () => {
    mockList.mockResolvedValue({
      data: {
        list: [
          { id: 'p1', product_name: '洁面泡沫', product_no: 'P001', face_price: 88, stock_status: 'in_stock', status: 'active', cover_image_url: 'https://example.com/cover.jpg' },
          { id: 'p2', product_name: '爽肤水', product_no: 'P002', face_price: 120, stock_status: 'in_stock', status: 'active', cover_image_url: null },
        ],
      },
    })
    mockGet.mockResolvedValue({
      data: { product_name: '洁面泡沫', product_no: 'P001', face_price: 88, stock: 100, cover_image_url: 'https://example.com/cover.jpg' },
    })

    return mount(ProposalItemEditor, {
      global: {
        plugins: [createPinia(), ElementPlus],
        renderStubDefaultSlot: true,
      },
    })
  }

  it('renders search input and add button', async () => {
    const wrapper = await factory()
    expect(wrapper.getComponent(ElSelect).props('placeholder')).toBe('搜索商品名称 / 编号')
    expect(wrapper.text()).toContain('添加商品')
  })

  it('renders empty state when no items', async () => {
    const wrapper = await factory()
    expect(wrapper.text()).toContain('暂未添加商品')
  })

  it('renders existing enriched items without per-item requests', async () => {
    const wrapper = mount(ProposalItemEditor, {
      props: {
        modelValue: [{
          product_id: 'p3',
          product_name: '已有商品',
          product_no: 'P003',
          face_price: 200,
          quantity: 2,
          remark: '测试',
        }],
      },
      global: {
        plugins: [createPinia(), ElementPlus],
        renderStubDefaultSlot: true,
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('已有商品')
    expect(wrapper.text()).toContain('P003')
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('updates quantity via setItemField', async () => {
    mockGet.mockResolvedValue({
      data: { product_name: '测试产品', product_no: 'P001', face_price: 100, stock: 50, cover_image_url: null },
    })

    const wrapper = mount(ProposalItemEditor, {
      props: {
        modelValue: [{ product_id: 'p1', quantity: 2, remark: '测试' }],
      },
      global: {
        plugins: [createPinia(), ElementPlus],
        renderStubDefaultSlot: true,
      },
    })
    await flushPromises()

    // Access the component's internal updateItemField via vm
    const vm = wrapper.vm as any
    vm.updateItemField(0, 'quantity', 5)
    await flushPromises()

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted![emitted!.length - 1][0][0].quantity).toBe(5)
  })

  it('updates remark via setItemField', async () => {
    mockGet.mockResolvedValue({
      data: { product_name: '测试产品', product_no: 'P001', face_price: 100, stock: 50, cover_image_url: null },
    })

    const wrapper = mount(ProposalItemEditor, {
      props: {
        modelValue: [{ product_id: 'p1', quantity: 2, remark: '' }],
      },
      global: {
        plugins: [createPinia(), ElementPlus],
        renderStubDefaultSlot: true,
      },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    vm.updateItemField(0, 'remark', '加急')
    await flushPromises()

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted![emitted!.length - 1][0][0].remark).toBe('加急')
  })

  it('removes item via removeItem', async () => {
    mockGet.mockResolvedValue({
      data: { product_name: '测试产品', product_no: 'P001', face_price: 100, stock: 50, cover_image_url: null },
    })

    const wrapper = mount(ProposalItemEditor, {
      props: {
        modelValue: [
          { product_id: 'p1', quantity: 2, remark: '' },
          { product_id: 'p2', quantity: 3, remark: '' },
        ],
      },
      global: {
        plugins: [createPinia(), ElementPlus],
        renderStubDefaultSlot: true,
      },
    })
    await flushPromises()

    const vm = wrapper.vm as any
    vm.removeItem(0)
    await flushPromises()

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted![emitted!.length - 1][0]).toHaveLength(1)
    expect(emitted![emitted!.length - 1][0][0].product_id).toBe('p2')
  })
})
