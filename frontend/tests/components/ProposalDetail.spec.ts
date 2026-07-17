import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import {
  ElCard,
  ElButton,
  ElTable,
  ElTag,
  ElEmpty,
  ElAlert,
  ElDescriptions,
  ElDescriptionsItem,
  ElTimeline,
  ElTimelineItem,
} from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api', () => ({
  proposalApi: {
    get: vi.fn(),
    update: vi.fn(),
  },
  aiApi: {
    polishProposal: vi.fn(),
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    permissions: ['proposal:edit', 'quotation:create', 'ai:use'],
    roleCode: 'admin',
  }),
}))

import { proposalApi, aiApi } from '@/api'
import ProposalDetail from '@/views/ProposalDetail.vue'

const mockGet = proposalApi.get as any
const mockPolish = aiApi.polishProposal as any

const factory = async (proposalData: any) => {
  mockGet.mockResolvedValue(proposalData)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/proposal/:id', component: ProposalDetail },
    ],
  })
  router.push('/proposal/42')
  await router.isReady()

  const wrapper = mount(ProposalDetail, {
    global: {
      plugins: [createPinia(), router],
      stubs: {
        ElCard,
        ElButton,
        ElTable,
        ElTag,
        ElEmpty,
        ElAlert,
        ElDescriptions,
        ElDescriptionsItem,
        ElTimeline,
        ElTimelineItem,
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('ProposalDetail.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('renders proposal basic info', async () => {
    const wrapper = await factory({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '夏季方案',
      customer_name: '客户A',
      status: 'draft',
      ai_polished: false,
      items: [],
    })

    expect(wrapper.text()).toContain('P2024001')
    expect(wrapper.text()).toContain('夏季方案')
    expect(wrapper.text()).toContain('客户A')
  })

  it('shows structured polish content when ai_polish_content is valid JSON', async () => {
    const polishContent = JSON.stringify({
      summary: '方案整体性价比高',
      item_reasons: ['产品A适合夏季', '产品B性价比突出'],
      industry_phrases: ['爆款热销', '口碑之选'],
    })

    const wrapper = await factory({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: true,
      ai_polish_content: polishContent,
      ai_polish_at: '2024-01-01T00:00:00Z',
      ai_polish_model: 'gpt-4',
      items: [],
    })

    expect(wrapper.text()).toContain('整体亮点')
    expect(wrapper.text()).toContain('方案整体性价比高')
    expect(wrapper.text()).toContain('单品推荐理由')
    expect(wrapper.text()).toContain('产品A适合夏季')
    expect(wrapper.text()).toContain('行业话术')
    expect(wrapper.text()).toContain('爆款热销')
    // Should NOT show failure banner
    expect(wrapper.text()).not.toContain('润色未能生成有效内容')
  })

  it('shows polish failure state when ai_polish_content is invalid JSON', async () => {
    const wrapper = await factory({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: true,
      ai_polish_content: 'not valid json',
      items: [],
    })

    expect(wrapper.text()).toContain('润色失败')
    expect(wrapper.text()).toContain('AI 润色未能生成有效内容')
    expect(wrapper.text()).toContain('原始数据')
  })

  it('shows polish failure when ai_polish_content is empty', async () => {
    const wrapper = await factory({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: true,
      ai_polish_content: '',
      items: [],
    })

    expect(wrapper.text()).toContain('润色失败')
  })

  it('shows unpolished state when ai_polished is false', async () => {
    const wrapper = await factory({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: false,
      items: [],
    })

    expect(wrapper.text()).toContain('未润色')
    expect(wrapper.text()).not.toContain('润色失败')
    // Polish section should not be shown
    expect(wrapper.text()).not.toContain('AI 润色内容')
  })

  it('button label changes to 重新润色 when polish failed', async () => {
    const wrapper = await factory({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: true,
      ai_polish_content: 'invalid',
      items: [],
    })

    const buttons = wrapper.findAllComponents(ElButton)
    const polishBtn = buttons.find(b => b.text().includes('润色'))
    expect(polishBtn?.text()).toContain('重新润色')
  })

  it('button label is AI 润色 when polish succeeded', async () => {
    const polishContent = JSON.stringify({ summary: 'ok', item_reasons: ['r1'], industry_phrases: [] })
    const wrapper = await factory({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: true,
      ai_polish_content: polishContent,
      items: [],
    })

    const buttons = wrapper.findAllComponents(ElButton)
    const polishBtn = buttons.find(b => b.text().includes('润色'))
    expect(polishBtn?.text()).toContain('AI 润色')
    expect(polishBtn?.text()).not.toContain('重新润色')
  })

  it('calls polishProposal and reloads on re-polish', async () => {
    mockPolish.mockResolvedValue({})
    mockGet.mockResolvedValueOnce({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: true,
      ai_polish_content: 'invalid',
      items: [],
    })
    mockGet.mockResolvedValueOnce({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: true,
      ai_polish_content: JSON.stringify({ summary: 'new', item_reasons: [], industry_phrases: [] }),
      items: [],
    })

    const wrapper = await factory({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: true,
      ai_polish_content: 'invalid',
      items: [],
    })

    const buttons = wrapper.findAllComponents(ElButton)
    const polishBtn = buttons.find(b => b.text().includes('润色'))
    await polishBtn!.trigger('click')
    await flushPromises()

    expect(mockPolish).toHaveBeenCalledWith('42')
    expect(mockGet).toHaveBeenCalled()
  })

  it('loads proposal items into component state', async () => {
    const wrapper = await factory({
      id: '42',
      proposal_no: 'P2024001',
      proposal_name: '方案',
      customer_name: '客户',
      status: 'draft',
      ai_polished: false,
      items: [
        { product_id: 'prod-1', quantity: 10, remark: '加急' },
      ],
    })

    // ElTable is stubbed; verify items are loaded into the component
    const vm = wrapper.vm as any
    expect(vm.items).toHaveLength(1)
    expect(vm.items[0].product_id).toBe('prod-1')
    expect(vm.items[0].quantity).toBe(10)
    expect(vm.items[0].remark).toBe('加急')
  })
})
