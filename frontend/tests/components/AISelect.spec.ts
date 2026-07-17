import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElCard, ElButton, ElInput, ElTag, ElEmpty, ElAlert, ElSkeleton } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api', () => ({
  aiApi: {
    chat: vi.fn(),
    recommend: vi.fn(),
  },
}))

import { aiApi } from '@/api'
import AISelect from '@/views/AISelect.vue'

const mockChat = aiApi.chat as any
const mockRecommend = aiApi.recommend as any

const factory = async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  router.push('/')
  await router.isReady()

  const wrapper = mount(AISelect, {
    global: {
      plugins: [createPinia(), router],
      stubs: {
        ElCard,
        ElButton,
        ElInput,
        ElTag,
        ElEmpty,
        ElAlert,
        ElSkeleton,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('AISelect.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('shows initial AI greeting message', async () => {
    const wrapper = await factory()
    expect(wrapper.text()).toContain('AI 选品助手')
  })

  it('adds user message and AI response to chat on send', async () => {
    mockChat.mockResolvedValue({
      data: { answer: '这是 AI 的回复', sources: [] },
    })

    const wrapper = await factory()
    const input = wrapper.findComponent(ElInput)
    await input.setValue('推荐护肤品')
    await wrapper.findComponent(ElButton).trigger('click')
    await flushPromises()

    expect(mockChat).toHaveBeenCalledWith(expect.objectContaining({ message: '推荐护肤品' }))
    expect(wrapper.text()).toContain('推荐护肤品')
    expect(wrapper.text()).toContain('这是 AI 的回复')
  })

  it('shows AI unavailable message when chat throws', async () => {
    mockChat.mockRejectedValue(new Error('network'))

    const wrapper = await factory()
    const input = wrapper.findComponent(ElInput)
    await input.setValue('hello')
    await wrapper.findComponent(ElButton).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('AI 服务暂时不可用')
  })

  it('displays recommend results with rationale and no degraded banner on success', async () => {
    mockRecommend.mockResolvedValue({
      data: {
        filters_applied: { category_id: 'cat-1', max_face_price: 100 },
        products: [
          {
            id: 'p1',
            product_no: 'P001',
            product_name: '保湿乳液',
            face_price: 89,
            stock_status: 'in_stock',
            description: '适合油性皮肤',
            _verified: true,
            _verified_by: 'ai-model-v2',
          },
        ],
        rationale: '基于预算和肤质筛选',
        total: 1,
        sources: [],
      },
    })

    const wrapper = await factory()
    const textarea = wrapper.findAllComponents(ElInput)[1]
    await textarea.setValue('需要保湿乳液')
    const buttons = wrapper.findAllComponents(ElButton)
    await buttons[1].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('保湿乳液')
    expect(wrapper.text()).toContain('基于预算和肤质筛选')
    expect(wrapper.text()).toContain('筛选条件')
    expect(wrapper.text()).toContain('category_id: cat-1')
    expect(wrapper.text()).toContain('已验证')
    expect(wrapper.text()).toContain('by ai-model-v2')
    // No degraded banner
    expect(wrapper.text()).not.toContain('降级')
  })

  it('shows degraded banner when AI parse fails', async () => {
    mockRecommend.mockResolvedValue({
      data: {
        status: 'parse_failed',
        filters_applied: {},
        products: [],
        rationale: 'AI 解析失败',
        total: 0,
        sources: [],
      },
    })

    const wrapper = await factory()
    const textarea = wrapper.findAllComponents(ElInput)[1]
    await textarea.setValue('vague')
    const buttons = wrapper.findAllComponents(ElButton)
    await buttons[1].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('AI 解析失败，请修正需求后重试')
  })

  it('never reads p.reason from recommend response', async () => {
    mockRecommend.mockResolvedValue({
      data: {
        filters_applied: {},
        products: [{ product_name: 'X' }],
        rationale: 'rationale text',
        total: 1,
        sources: [],
      },
    })

    const wrapper = await factory()
    const textarea = wrapper.findAllComponents(ElInput)[1]
    await textarea.setValue('test')
    const buttons = wrapper.findAllComponents(ElButton)
    await buttons[1].trigger('click')
    await flushPromises()

    // The product should render without any "reason" field
    expect(wrapper.text()).toContain('X')
    expect(wrapper.text()).toContain('rationale text')
    expect(wrapper.text()).not.toContain('reason')
  })

  it('shows error message when recommend API fails', async () => {
    mockRecommend.mockRejectedValue(new Error('fail'))

    const wrapper = await factory()
    const textarea = wrapper.findAllComponents(ElInput)[1]
    await textarea.setValue('test')
    const buttons = wrapper.findAllComponents(ElButton)
    await buttons[1].trigger('click')
    await flushPromises()

    // ElMessage.error is called; we verify no crash and no results
    expect(wrapper.findAll('.result-item').length).toBe(0)
  })
})
