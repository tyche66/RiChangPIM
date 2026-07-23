import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElInput, ElMessage } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api', () => ({
  proposalApi: { list: vi.fn().mockResolvedValue({ data: { list: [] } }), create: vi.fn() },
  shareApi: { create: vi.fn() },
  productApi: { get: vi.fn(), list: vi.fn() },
}))

import { proposalApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import Proposals from '@/views/Proposals.vue'

const mockCreate = proposalApi.create as ReturnType<typeof vi.fn>
const warningSpy = vi.spyOn(ElMessage, 'warning').mockImplementation(() => {})

describe('Proposals create guard', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockCreate.mockReset()
    warningSpy.mockClear()
  })

  it('blocks submit when no items added', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/proposals', component: Proposals }],
    })
    await router.push('/proposals')
    await router.isReady()

    const pinia = createPinia()
    setActivePinia(pinia)
    const authStore = useAuthStore(pinia)
    authStore.permissions = ['proposal:create']
    authStore.user = null

    const wrapper = mount(Proposals, {
      global: { plugins: [pinia, router, ElementPlus] },
    })
    await flushPromises()

    await wrapper.findAll('button').find((b) => b.text().includes('新增方案'))!.trigger('click')
    await flushPromises()
    const inputs = wrapper.findAllComponents(ElInput)
    await inputs[0].setValue('测试方案')
    await inputs[1].setValue('测试客户')
    const confirmBtn = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.includes('确定')) as HTMLButtonElement | undefined
    expect(confirmBtn).toBeTruthy()
    confirmBtn!.click()
    await flushPromises()

    expect(warningSpy).toHaveBeenCalledWith('请至少添加一项商品')
    expect(mockCreate).not.toHaveBeenCalled()
  })
})
