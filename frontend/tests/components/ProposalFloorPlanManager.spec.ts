import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import type { FloorPlanDraft } from '@/types/sales'

vi.mock('@/api/proposalFloorPlans', () => ({
  proposalFloorPlanApi: {
    list: vi.fn(),
    create: vi.fn(),
    batchCreate: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...(actual as object),
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue('confirm'),
    },
  }
})

import { proposalFloorPlanApi } from '@/api/proposalFloorPlans'
import ProposalFloorPlanManager from '@/components/ProposalFloorPlanManager.vue'

const mockList = vi.mocked(proposalFloorPlanApi.list)
const mockUpdate = vi.mocked(proposalFloorPlanApi.update)
const mockRemove = vi.mocked(proposalFloorPlanApi.remove)

const PLAN = (overrides: Record<string, unknown> = {}) => ({
  id: 'fp-1',
  proposal_id: 'p-1',
  project_id: null,
  attachment_id: 'att-1',
  name: '江韵方案一层平面图',
  sort: 0,
  image_url: '/api/v1/files/att-1/content?token=t',
  ...overrides,
})

function mountManager(props: Record<string, unknown>) {
  return mount(ProposalFloorPlanManager, {
    props,
    global: { plugins: [ElementPlus] },
  })
}

describe('ProposalFloorPlanManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockList.mockResolvedValue({
      code: 200,
      data: { list: [], total: 0, limit: 20 },
    } as never)
  })

  it('已绑定方案时按接口返回渲染缩略图与名称', async () => {
    mockList.mockResolvedValue({
      code: 200,
      data: {
        list: [
          PLAN(),
          PLAN({ id: 'fp-2', attachment_id: 'att-2', name: '二层平面图', sort: 1 }),
        ],
        total: 2,
        limit: 20,
      },
    } as never)

    const wrapper = mountManager({ proposalId: 'p-1' })
    await flushPromises()

    expect(mockList).toHaveBeenCalledWith('p-1')
    const names = wrapper.findAll('.fp-name').map((node) => node.text())
    expect(names).toEqual(['江韵方案一层平面图', '二层平面图'])
    expect(wrapper.findAll('.fp-card')).toHaveLength(2)
  })

  it('改名走 PUT，并把新名字留在界面上', async () => {
    mockList.mockResolvedValue({
      code: 200,
      data: { list: [PLAN()], total: 1, limit: 20 },
    } as never)
    mockUpdate.mockResolvedValue({ code: 200, data: PLAN() } as never)

    const wrapper = mountManager({ proposalId: 'p-1' })
    await flushPromises()

    await wrapper.find('.fp-name').trigger('click')
    const input = wrapper.find('.fp-rename input')
    expect(input.exists()).toBe(true)
    await input.setValue('江韵方案一层平面图（终稿）')
    await input.trigger('keyup.enter')
    await flushPromises()

    expect(mockUpdate).toHaveBeenCalledWith('p-1', 'fp-1', {
      name: '江韵方案一层平面图（终稿）',
    })
    expect(wrapper.find('.fp-name').text()).toBe('江韵方案一层平面图（终稿）')
  })

  it('删除前确认，确认后调 DELETE 并重新拉取列表', async () => {
    mockList.mockResolvedValue({
      code: 200,
      data: { list: [PLAN()], total: 1, limit: 20 },
    } as never)
    mockRemove.mockResolvedValue({} as never)

    const wrapper = mountManager({ proposalId: 'p-1' })
    await flushPromises()

    await wrapper.find('.fp-action--danger').trigger('click')
    await flushPromises()

    expect(mockRemove).toHaveBeenCalledWith('p-1', 'fp-1')
    expect(mockList).toHaveBeenCalledTimes(2)
  })

  it('只读权限下按钮禁用，且不会发写请求', async () => {
    mockList.mockResolvedValue({
      code: 200,
      data: { list: [PLAN()], total: 1, limit: 20 },
    } as never)

    const wrapper = mountManager({ proposalId: 'p-1', disabled: true })
    await flushPromises()

    const buttons = wrapper.findAll('.fp-toolbar button')
    expect(buttons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)

    await wrapper.find('.fp-name').trigger('click')
    expect(wrapper.find('.fp-rename').exists()).toBe(false)
    expect(mockUpdate).not.toHaveBeenCalled()
  })

  it('暂存模式不发请求，删除后回传新的列表', async () => {
    const draft: FloorPlanDraft[] = [
      { attachment_id: 'att-9', name: '一层平面图', image_url: '/x.png' },
    ]
    const wrapper = mountManager({ modelValue: draft })
    await flushPromises()

    expect(mockList).not.toHaveBeenCalled()
    expect(wrapper.find('.fp-name').text()).toBe('一层平面图')

    await wrapper.find('.fp-action--danger').trigger('click')
    await flushPromises()

    expect(mockRemove).not.toHaveBeenCalled()
    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted?.at(-1)?.[0]).toEqual([])
  })

  it('数量到上限时禁用上传与媒体库入口', async () => {
    const drafts: FloorPlanDraft[] = Array.from({ length: 20 }, (_, index) => ({
      attachment_id: `att-${index}`,
      name: `平面图 ${index + 1}`,
      image_url: `/img-${index}.png`,
    }))
    const wrapper = mountManager({ modelValue: drafts })
    await flushPromises()

    const buttons = wrapper.findAll('.fp-toolbar button')
    expect(buttons.every((button) => button.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.text()).toContain('20 / 20 张')
  })
})
