import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessage } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

const { createMock, listMock } = vi.hoisted(() => ({
  createMock: vi.fn(),
  listMock: vi.fn().mockResolvedValue({ data: { list: [], total: 0 } }),
}))

vi.mock('@/api', () => ({
  proposalApi: { list: listMock, create: createMock },
  projectSpaceApi: { list: vi.fn().mockResolvedValue({ data: [] }) },
  shareApi: { create: vi.fn() },
  productApi: { get: vi.fn(), list: vi.fn() },
}))
vi.mock('@/api/customer', () => ({ customerApi: { list: vi.fn() } }))
vi.mock('@/api/project', () => ({ projectApi: { list: vi.fn().mockResolvedValue({ data: { list: [] } }) } }))

import Proposals from '@/views/Proposals.vue'
import { useAuthStore } from '@/stores/auth'

const successSpy = vi.spyOn(ElMessage, 'success').mockImplementation(() => {})
const errorSpy = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})

async function mountPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/proposals', component: Proposals }],
  })
  await router.push('/proposals')
  await router.isReady()

  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore(pinia)
  auth.permissions = ['proposal:create']
  auth.user = { id: 'user-1' } as never

  const wrapper = mount(Proposals, { global: { plugins: [pinia, router, ElementPlus] } })
  await flushPromises()
  return wrapper
}

describe('proposal submit flow', () => {
  beforeEach(() => {
    createMock.mockReset()
    listMock.mockClear()
    successSpy.mockClear()
    errorSpy.mockClear()
  })

  it('submits selected product and project-space fields, closes and refreshes on success', async () => {
    createMock.mockResolvedValue({ data: { id: 'proposal-1' } })
    const wrapper = await mountPage()
    const vm = wrapper.vm as unknown as {
      showCreateDialog: boolean
      createForm: {
        proposal_name: string
        customer_name: string
        customer_id: string | null
        project_id: string | null
        items: Array<Record<string, unknown>>
      }
      handleCreateSubmit: () => Promise<void>
      createLoading: boolean
    }
    vm.showCreateDialog = true
    vm.createForm.proposal_name = 'Living room'
    vm.createForm.customer_name = 'Test customer'
    vm.createForm.customer_id = 'customer-1'
    vm.createForm.project_id = 'project-1'
    vm.createForm.items = [{
      product_id: 'product-1',
      quantity: 2,
      remark: 'note',
      project_space_id: 'space-1',
      floor_label: '3F',
      space_label: 'Living room',
      material_desc: 'wood veneer',
    }]
    await flushPromises()

    await vm.handleCreateSubmit()

    expect(createMock).toHaveBeenCalledWith({
      proposal_name: 'Living room',
      customer_name: 'Test customer',
      customer_id: 'customer-1',
      project_id: 'project-1',
      creator_id: 'user-1',
      items: [{
        product_id: 'product-1',
        quantity: 2,
        remark: 'note',
        project_space_id: 'space-1',
        floor_label: '3F',
        space_label: 'Living room',
        material_desc: 'wood veneer',
      }],
    }, { suppressErrorMessage: true })
    expect(successSpy).toHaveBeenCalled()
    expect(vm.showCreateDialog).toBe(false)
    expect(vm.createForm.items).toEqual([])
    expect(vm.createLoading).toBe(false)
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('shows the server validation reason and remains open and retryable on failure', async () => {
    createMock.mockRejectedValue({
      response: { status: 422, data: { detail: { code: 42201, msg: 'Invalid project space' } } },
    })
    const wrapper = await mountPage()
    const vm = wrapper.vm as unknown as {
      showCreateDialog: boolean
      createForm: { proposal_name: string; items: Array<Record<string, unknown>> }
      handleCreateSubmit: () => Promise<void>
      createLoading: boolean
    }
    vm.showCreateDialog = true
    vm.createForm.proposal_name = 'Living room'
    vm.createForm.items = [{ product_id: 'product-1', quantity: 1 }]
    await flushPromises()

    await vm.handleCreateSubmit()

    expect(errorSpy).toHaveBeenCalledWith('创建失败：Invalid project space')
    expect(vm.showCreateDialog).toBe(true)
    expect(vm.createLoading).toBe(false)
    expect(listMock).toHaveBeenCalledTimes(1)
  })
})
