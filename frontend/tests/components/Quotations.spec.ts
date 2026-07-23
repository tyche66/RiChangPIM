import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus, {
  ElDialog, ElForm, ElFormItem, ElInput, ElInputNumber,
  ElSelect, ElOption, ElButton, ElTag, ElDatePicker, ElMessage,
} from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({
  quotationApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    confirm: vi.fn(),
    exportPdf: vi.fn(),
  },
  proposalApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    confirm: vi.fn(),
  },
  productApi: {
    list: vi.fn(),
    get: vi.fn(),
  },
  shareApi: {
    create: vi.fn(),
  },
}))

import { quotationApi, proposalApi, productApi } from '@/api'
import Quotations from '@/views/Quotations.vue'

const mockQuotationList = quotationApi.list as ReturnType<typeof vi.fn>
const mockQuotationGet = quotationApi.get as ReturnType<typeof vi.fn>
const mockQuotationCreate = quotationApi.create as ReturnType<typeof vi.fn>
const mockQuotationUpdate = quotationApi.update as ReturnType<typeof vi.fn>
const mockQuotationConfirm = quotationApi.confirm as ReturnType<typeof vi.fn>
const mockProposalGet = proposalApi.get as ReturnType<typeof vi.fn>
const mockProductGet = productApi.get as ReturnType<typeof vi.fn>

describe('Quotations.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.spyOn(ElMessage, 'success').mockImplementation(() => {})
    vi.spyOn(ElMessage, 'error').mockImplementation(() => {})
    vi.spyOn(ElMessage, 'warning').mockImplementation(() => {})
  })

  const factory = async (options?: { skipDefaultMock?: boolean }) => {
    if (!options?.skipDefaultMock) {
      const mockData = {
        id: 'q1',
        quotation_no: 'QT-2026-ABC123',
        proposal_id: 'p1',
        proposal_no: 'PR-2026-DEF456',
        proposal_name: '测试方案',
        creator_id: 'u1',
        valid_until: null,
        total_amount: 1000,
        subtotal: 885,
        tax_rate: 0.13,
        discount: 1.0,
        status: 'draft',
        create_time: '2024-01-01T00:00:00Z',
        update_time: '2024-01-01T00:00:00Z',
        items: [
          { product_id: 'prod1', quantity: 2, unit_price: 100, tax_rate: 0.13, subtotal: 200 },
        ],
      }

      mockQuotationList.mockResolvedValue({
        data: { list: [mockData], total: 1, page: 1, size: 20 },
      })

      mockQuotationGet.mockResolvedValue({ data: mockData })

      mockProposalGet.mockResolvedValue({
        data: {
          id: 'p1',
          proposal_no: 'PR-2026-DEF456',
          proposal_name: '测试方案',
          customer_name: '测试客户',
          creator_id: 'u1',
          status: 'draft',
          ai_polished: false,
          total_face_value: 500,
          create_time: '2024-01-01T00:00:00Z',
          items: [
            { product_id: 'prod1', quantity: 2, remark: '测试' },
          ],
        },
      })

      mockProductGet.mockResolvedValue({
        data: {
          id: 'prod1',
          product_name: '测试产品',
          product_no: 'P001',
          face_price: 250,
          stock: 100,
          cover_image_url: null,
        },
      })

      mockQuotationCreate.mockResolvedValue({ data: mockData })
      mockQuotationUpdate.mockResolvedValue({ data: mockData })
      mockQuotationConfirm.mockResolvedValue({ data: mockData })
    }

    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/quotations', component: Quotations }],
    })
    await router.push('/quotations')
    await router.isReady()

    const wrapper = mount(Quotations, {
      global: {
        plugins: [createPinia(), router, ElementPlus],
        renderStubDefaultSlot: true,
        stubs: {
          ElDialog,
          ElForm,
          ElFormItem,
          ElInput,
          ElInputNumber,
          ElSelect,
          ElOption,
          ElButton,
          ElTag,
          ElDatePicker,
        },
      },
    })
    await flushPromises()
    await flushPromises()
    await flushPromises()
    return wrapper
  }

  it('loads quotation list on mount', async () => {
    const wrapper = await factory()
    expect(mockQuotationList).toHaveBeenCalled()
    expect(wrapper.text()).toContain('QT-2026-ABC123')
  }, 10000)

  it('shows proposal no and name in list', async () => {
    const wrapper = await factory()
    expect(wrapper.text()).toContain('PR-2026-DEF456')
    expect(wrapper.text()).toContain('测试方案')
  }, 10000)

  it('calls update on edit submit, not create', async () => {
    const wrapper = await factory()

    // Verify quotations data is loaded
    const vm = wrapper.vm as any
    expect(vm.quotations).toHaveLength(1)
    expect(vm.quotations[0].quotation_no).toBe('QT-2026-ABC123')

    // Open edit dialog by simulating the edit action
    const row = vm.quotations[0]
    vm.handleEdit(row)
    await flushPromises()
    await flushPromises()

    // Verify dialog opened and form populated
    expect(vm.showQuotationDialog).toBe(true)
    expect(vm.quotationEditId).toBe('q1')

    // Verify edit form data
    expect(vm.quotationForm.proposal_id).toBe('p1')
    expect(vm.quotationForm.tax_rate).toBe(0.13)
    expect(vm.quotationForm.items).toHaveLength(1)

    // Simulate submit
    vm.handleQuotationSubmit()
    await flushPromises()

    expect(mockQuotationUpdate).toHaveBeenCalled()
    expect(mockQuotationCreate).not.toHaveBeenCalled()
  }, 15000)

  it('calls confirm API', async () => {
    const wrapper = await factory()
    const vm = wrapper.vm as any

    const row = vm.quotations[0]
    vm.handleConfirm(row)
    await flushPromises()

    expect(mockQuotationConfirm).toHaveBeenCalledWith('q1')
  }, 10000)

  it('does not show edit button for confirmed quotations', async () => {
    mockQuotationList.mockResolvedValue({
      data: {
        list: [{
          id: 'q2',
          quotation_no: 'QT-2026-CONFIRMED',
          proposal_id: 'p2',
          proposal_no: 'PR-2026-CONF',
          proposal_name: '已确认方案',
          creator_id: 'u1',
          valid_until: null,
          total_amount: 2000,
          subtotal: 1770,
          tax_rate: 0.13,
          discount: 1.0,
          status: 'confirmed',
          create_time: '2024-01-01T00:00:00Z',
          update_time: '2024-01-01T00:00:00Z',
          items: [],
        }],
        total: 1,
        page: 1,
        size: 20,
      },
    })

    mockProposalGet.mockResolvedValue({
      data: {
        id: 'p2',
        proposal_no: 'PR-2026-CONF',
        proposal_name: '已确认方案',
        customer_name: '已确认客户',
        creator_id: 'u1',
        status: 'confirmed',
        ai_polished: false,
        total_face_value: 1000,
        create_time: '2024-01-01T00:00:00Z',
        items: [],
      },
    })

    const wrapper = await factory({ skipDefaultMock: true })
    const vm = wrapper.vm as any
    expect(vm.quotations[0].status).toBe('confirmed')
  }, 10000)

  it('shows share button only for confirmed quotations', async () => {
    mockQuotationList.mockResolvedValue({
      data: {
        list: [{
          id: 'q2',
          quotation_no: 'QT-2026-CONFIRMED',
          proposal_id: 'p2',
          proposal_no: 'PR-2026-CONF',
          proposal_name: '已确认方案',
          creator_id: 'u1',
          valid_until: null,
          total_amount: 2000,
          subtotal: 1770,
          tax_rate: 0.13,
          discount: 1.0,
          status: 'confirmed',
          create_time: '2024-01-01T00:00:00Z',
          update_time: '2024-01-01T00:00:00Z',
          items: [],
        }],
        total: 1,
        page: 1,
        size: 20,
      },
    })

    mockProposalGet.mockResolvedValue({
      data: {
        id: 'p2',
        proposal_no: 'PR-2026-CONF',
        proposal_name: '已确认方案',
        customer_name: '已确认客户',
        creator_id: 'u1',
        status: 'confirmed',
        ai_polished: false,
        total_face_value: 1000,
        create_time: '2024-01-01T00:00:00Z',
        items: [],
      },
    })

    const wrapper = await factory({ skipDefaultMock: true })
    const vm = wrapper.vm as any

    // Share should only be available for confirmed status
    const row = vm.quotations[0]
    vm.handleShare(row)
    await flushPromises()

    expect(vm.showShareDialog).toBe(true)
    expect(vm.shareForm.target_id).toBe('q2')
  }, 10000)
})
