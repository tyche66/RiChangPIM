import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElButton, ElInput, ElSelect, ElTag, ElMessage } from 'element-plus'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/api', () => ({
  fileApi: {
    upload: vi.fn(),
    delete: vi.fn(),
    download: vi.fn(),
    preview: vi.fn(),
  },
  manualApi: {
    create: vi.fn(),
    list: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
    parse: vi.fn(),
    ocr: vi.fn(),
    index: vi.fn(),
    answer: vi.fn(),
  },
}))

const successSpy = vi.spyOn(ElMessage, 'success').mockImplementation(() => {})
const errorSpy = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})
const warningSpy = vi.spyOn(ElMessage, 'warning').mockImplementation(() => {})

import { fileApi, manualApi } from '@/api'
import Manuals from '@/views/Manuals.vue'

const mockList = manualApi.list as any
const mockCreate = manualApi.create as any
const mockParse = manualApi.parse as any
const mockIndex = manualApi.index as any
const mockAnswer = manualApi.answer as any
const mockUpload = fileApi.upload as any

const mockManuals = [
  {
    id: '1',
    product_id: 'PROD-001',
    attachment_id: 'att-1',
    doc_type: 'manual',
    parse_status: 'parsed' as const,
    index_status: 'indexed' as const,
    parser_name: 'pdf-parser',
    parser_version: '1.0',
    parse_error: null,
    index_error: null,
    create_time: '2024-01-01T00:00:00Z',
    update_time: '2024-01-01T00:00:00Z',
  },
  {
    id: '2',
    product_id: 'PROD-002',
    attachment_id: 'att-2',
    doc_type: 'spec',
    parse_status: 'failed' as const,
    index_status: 'pending' as const,
    parse_error: 'Invalid PDF structure',
    index_error: null,
    parser_name: null,
    parser_version: null,
    create_time: '2024-01-02T00:00:00Z',
    update_time: '2024-01-02T00:00:00Z',
  },
  {
    id: '3',
    product_id: 'PROD-003',
    attachment_id: 'att-3',
    doc_type: 'datasheet',
    parse_status: 'parsed' as const,
    index_status: 'failed' as const,
    parse_error: null,
    index_error: 'Vector DB timeout',
    parser_name: 'docx-parser',
    parser_version: '2.1',
    create_time: '2024-01-03T00:00:00Z',
    update_time: '2024-01-03T00:00:00Z',
  },
]

function btnByText(wrapper: any, text: string) {
  return wrapper.findAllComponents(ElButton).find((b: any) => b.text().trim() === text)
}

function rowButtons(wrapper: any, rowIndex: number) {
  const rows = wrapper.findAll('.el-table__row')
  return rows[rowIndex]?.findAllComponents(ElButton) ?? []
}

const factory = async () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div />' } }],
  })
  router.push('/')
  await router.isReady()

  const pinia = createPinia()
  setActivePinia(pinia)
  const authStore = useAuthStore(pinia)
  authStore.permissions = ['product:edit', 'ai:use']
  authStore.roleCode = 'admin'

  const wrapper = mount(Manuals, {
    global: {
      plugins: [pinia, router, ElementPlus],
    },
  })
  await flushPromises()
  return wrapper
}

describe('Manuals.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    successSpy.mockClear()
    errorSpy.mockClear()
    warningSpy.mockClear()
  })

  describe('initial list', () => {
    it('loads and displays manuals on mount', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      const wrapper = await factory()

      expect(mockList).toHaveBeenCalledWith({ page: 1, size: 50 })
      expect(wrapper.text()).toContain('PROD-001')
      expect(wrapper.text()).toContain('PROD-002')
      expect(wrapper.text()).toContain('PROD-003')
      expect(wrapper.text()).toContain('manual')
      expect(wrapper.text()).toContain('spec')
      expect(wrapper.text()).toContain('datasheet')
    })

    it('shows empty state when no manuals', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      const wrapper = await factory()
      expect(wrapper.text()).toContain('暂无说明书')
    })

    it('displays parse and index status tags', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      const wrapper = await factory()

      expect(wrapper.text()).toContain('parsed')
      expect(wrapper.text()).toContain('indexed')
      expect(wrapper.text()).toContain('failed')
      expect(wrapper.text()).toContain('pending')
    })

    it('shows failure reasons from parse_error and index_error', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      const wrapper = await factory()

      expect(wrapper.text()).toContain('Invalid PDF structure')
      expect(wrapper.text()).toContain('Vector DB timeout')
    })

    it('shows parser name and version', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      const wrapper = await factory()

      expect(wrapper.text()).toContain('pdf-parser')
      expect(wrapper.text()).toContain('docx-parser')
      expect(wrapper.text()).toContain('2.1')
    })

    it('renders dash when no parser info', async () => {
      mockList.mockResolvedValue({
        data: {
          list: [{
            ...mockManuals[1],
            parser_name: null,
            parser_version: null,
          }],
          total: 1,
        },
      })
      const wrapper = await factory()
      expect(wrapper.text()).toContain('-')
    })
  })

  describe('upload/create', () => {
    it('shows warning when product ID and file are missing', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      const wrapper = await factory()

      await btnByText(wrapper, '上传并创建')!.trigger('click')
      await flushPromises()

      expect(warningSpy).toHaveBeenCalledWith('请填写产品 ID 并选择 PDF/DOCX 文件')
    })

    it('uploads file, creates manual, and reloads list on success', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      mockUpload.mockResolvedValue({ data: { attachment_id: 'att-new' } })
      mockCreate.mockResolvedValue({ data: { id: 'new-1' } })

      const wrapper = await factory()

      const inputs = wrapper.findAllComponents(ElInput)
      await inputs[0].setValue('PROD-NEW')

      const select = wrapper.findComponent(ElSelect)
      await select.setValue('spec')

      const file = new File(['dummy pdf content'], 'manual.pdf', { type: 'application/pdf' })
      const fileInput = wrapper.find('input[type="file"]')
      Object.defineProperty(fileInput.element, 'files', { value: [file], writable: false })
      await fileInput.trigger('change')
      await flushPromises()

      expect(wrapper.text()).toContain('manual.pdf')

      await btnByText(wrapper, '上传并创建')!.trigger('click')
      await flushPromises()

      expect(mockUpload).toHaveBeenCalled()
      const formData = mockUpload.mock.calls[0][0] as FormData
      expect(formData).toBeInstanceOf(FormData)

      expect(mockCreate).toHaveBeenCalledWith({
        product_id: 'PROD-NEW',
        attachment_id: 'att-new',
        doc_type: 'spec',
      })
      expect(successSpy).toHaveBeenCalledWith('说明书已创建，请触发解析')
      expect(mockList).toHaveBeenCalledTimes(2)
    })

    it('shows error when file upload or create fails', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      mockUpload.mockResolvedValue({ data: { attachment_id: 'att-new' } })
      mockCreate.mockRejectedValue(new Error('server error'))

      const wrapper = await factory()

      const inputs = wrapper.findAllComponents(ElInput)
      await inputs[0].setValue('PROD-NEW')

      const file = new File(['dummy'], 'manual.pdf', { type: 'application/pdf' })
      const fileInput = wrapper.find('input[type="file"]')
      Object.defineProperty(fileInput.element, 'files', { value: [file] })
      await fileInput.trigger('change')

      await btnByText(wrapper, '上传并创建')!.trigger('click')
      await flushPromises()

      expect(errorSpy).toHaveBeenCalledWith('说明书创建失败')
    })

    it('resets uploading state after create finishes', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      mockUpload.mockResolvedValue({ data: { attachment_id: 'att-new' } })
      mockCreate.mockResolvedValue({ data: {} })

      const wrapper = await factory()

      await wrapper.findAllComponents(ElInput)[0].setValue('P1')
      const file = new File(['x'], 'f.pdf', { type: 'application/pdf' })
      Object.defineProperty(wrapper.find('input[type="file"]').element, 'files', { value: [file] })
      await wrapper.find('input[type="file"]').trigger('change')

      const uploadBtn = btnByText(wrapper, '上传并创建')!
      await uploadBtn.trigger('click')
      await flushPromises()

      expect(uploadBtn.props('loading')).toBe(false)
    })
  })

  describe('parse/index failure semantics', () => {
    it('calls parse and reloads list on success', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      mockParse.mockResolvedValue({ data: {} })
      const wrapper = await factory()

      const parseBtn = rowButtons(wrapper, 0).find((b: any) => b.text().trim() === '解析')
      await parseBtn!.trigger('click')
      await flushPromises()

      expect(mockParse).toHaveBeenCalledWith('1')
      expect(successSpy).toHaveBeenCalledWith('解析完成')
      expect(mockList).toHaveBeenCalledTimes(2)
    })

    it('shows error and reloads on parse failure', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      mockParse.mockRejectedValue(new Error('parse error'))
      const wrapper = await factory()

      const parseBtn = rowButtons(wrapper, 0).find((b: any) => b.text().trim() === '解析')
      await parseBtn!.trigger('click')
      await flushPromises()

      expect(mockParse).toHaveBeenCalledWith('1')
      expect(errorSpy).toHaveBeenCalledWith('解析失败，请查看失败原因')
      expect(mockList).toHaveBeenCalledTimes(2)
    })

    it('resets busyId after parse completes so button is no longer loading', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      mockParse.mockResolvedValue({ data: {} })
      const wrapper = await factory()

      const parseBtn = rowButtons(wrapper, 0).find((b: any) => b.text().trim() === '解析')!
      await parseBtn.trigger('click')
      await flushPromises()

      expect(parseBtn.props('loading')).toBe(false)
    })

    it('calls index and reloads list on success', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      mockIndex.mockResolvedValue({ data: {} })
      const wrapper = await factory()

      const indexBtn = rowButtons(wrapper, 0).find((b: any) => b.props('type') === 'primary')
      await indexBtn!.trigger('click')
      await flushPromises()

      expect(mockIndex).toHaveBeenCalledWith('1')
      expect(successSpy).toHaveBeenCalledWith('索引完成')
      expect(mockList).toHaveBeenCalledTimes(2)
    })

    it('shows error and reloads on index failure', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      mockIndex.mockRejectedValue(new Error('index error'))
      const wrapper = await factory()

      const indexBtn = rowButtons(wrapper, 0).find((b: any) => b.props('type') === 'primary')
      await indexBtn!.trigger('click')
      await flushPromises()

      expect(mockIndex).toHaveBeenCalledWith('1')
      expect(errorSpy).toHaveBeenCalledWith('索引失败，请查看失败原因')
      expect(mockList).toHaveBeenCalledTimes(2)
    })

    it('uses same busyId guard so only one action per row is loading at a time', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      mockParse.mockImplementation(() => new Promise(() => {}))
      const wrapper = await factory()

      const parseBtn = rowButtons(wrapper, 0).find((b: any) => b.text().trim() === '解析')!
      await parseBtn.trigger('click')

      const indexBtn = rowButtons(wrapper, 0).find((b: any) => b.props('type') === 'primary')!
      expect(indexBtn.props('loading')).toBe(true)
    })
  })

  describe('RAG sources and insufficient state', () => {
    it('displays answer with sources and metadata', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      mockAnswer.mockResolvedValue({
        data: {
          answer: 'This product supports 220V.',
          sources: [
            {
              chunk_id: 'ch1',
              product_manual_id: '1',
              product_id: 'PROD-001',
              chunk_index: 0,
              chunk_text: 'The device operates at 220V 50Hz.',
              score: 0.92,
            },
          ],
          bounded: true,
          insufficient_sources: false,
        },
      })
      const wrapper = await factory()

      const inputs = wrapper.findAllComponents(ElInput)
      await inputs[2].setValue('What voltage?')

      await btnByText(wrapper, '提问')!.trigger('click')
      await flushPromises()

      expect(mockAnswer).toHaveBeenCalledWith(expect.objectContaining({
        query: 'What voltage?',
        product_id: undefined,
        top_k: 6,
        min_score: 0.65,
      }))
      expect(wrapper.text()).toContain('回答')
      expect(wrapper.text()).toContain('This product supports 220V.')
      expect(wrapper.text()).toContain('Sources')
      expect(wrapper.text()).toContain('score 0.92')
      expect(wrapper.text()).toContain('产品 PROD-001')
      expect(wrapper.text()).toContain('chunk #0')
      expect(wrapper.text()).toContain('The device operates at 220V 50Hz.')
    })

    it('truncates long source text to 180 characters', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      const longText = 'x'.repeat(200)
      mockAnswer.mockResolvedValue({
        data: {
          answer: 'OK',
          sources: [{
            chunk_id: 'ch1',
            product_manual_id: '1',
            product_id: 'P1',
            chunk_index: 0,
            chunk_text: longText,
            score: 0.9,
          }],
          bounded: true,
          insufficient_sources: false,
        },
      })
      const wrapper = await factory()

      await wrapper.findAllComponents(ElInput)[2].setValue('q')
      await btnByText(wrapper, '提问')!.trigger('click')
      await flushPromises()

      expect(wrapper.text()).toContain('x'.repeat(180) + '...')
      expect(wrapper.text()).not.toContain(longText)
    })

    it('shows insufficient state when insufficient_sources is true', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      mockAnswer.mockResolvedValue({
        data: {
          answer: 'I am not sure.',
          sources: [],
          bounded: false,
          insufficient_sources: true,
        },
      })
      const wrapper = await factory()

      await wrapper.findAllComponents(ElInput)[2].setValue('uncertain')
      await btnByText(wrapper, '提问')!.trigger('click')
      await flushPromises()

      const heading = wrapper.find('.answer-box h3')
      expect(heading.text()).toBe('资料不足以确认')
      expect(wrapper.text()).toContain('I am not sure.')
    })

    it('shows insufficient state when sources are empty even if insufficient_sources is false', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      mockAnswer.mockResolvedValue({
        data: {
          answer: '',
          sources: [],
          bounded: false,
          insufficient_sources: false,
        },
      })
      const wrapper = await factory()

      await wrapper.findAllComponents(ElInput)[2].setValue('empty')
      await btnByText(wrapper, '提问')!.trigger('click')
      await flushPromises()

      expect(wrapper.text()).toContain('资料不足以确认')
    })

    it('shows AI service error message on answer failure', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      mockAnswer.mockRejectedValue(new Error('AI down'))
      const wrapper = await factory()

      await wrapper.findAllComponents(ElInput)[2].setValue('any')
      await btnByText(wrapper, '提问')!.trigger('click')
      await flushPromises()

      expect(wrapper.text()).toContain('AI 服务未配置或暂时不可用')
    })

    it('does not submit when query is empty or whitespace', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      const wrapper = await factory()

      await wrapper.findAllComponents(ElInput)[2].setValue('   ')
      await btnByText(wrapper, '提问')!.trigger('click')
      await flushPromises()

      expect(mockAnswer).not.toHaveBeenCalled()
    })

    it('submits RAG query on Enter key', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      mockAnswer.mockResolvedValue({
        data: { answer: 'Yes.', sources: [], bounded: true, insufficient_sources: false },
      })
      const wrapper = await factory()

      const queryInput = wrapper.findAllComponents(ElInput)[2]
      await queryInput.setValue('Hello')
      await queryInput.find('input').trigger('keydown', { key: 'Enter' })
      await flushPromises()

      expect(mockAnswer).toHaveBeenCalled()
    })

    it('passes product_id filter when provided', async () => {
      mockList.mockResolvedValue({ data: { list: [], total: 0 } })
      mockAnswer.mockResolvedValue({
        data: { answer: 'OK', sources: [], bounded: true, insufficient_sources: false },
      })
      const wrapper = await factory()

      const inputs = wrapper.findAllComponents(ElInput)
      await inputs[1].setValue('PROD-FILTER')
      await inputs[2].setValue('question')
      await btnByText(wrapper, '提问')!.trigger('click')
      await flushPromises()

      expect(mockAnswer).toHaveBeenCalledWith(expect.objectContaining({
        query: 'question',
        product_id: 'PROD-FILTER',
      }))
    })
  })

  describe('refresh', () => {
    it('reloads manuals when refresh button is clicked', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      const wrapper = await factory()

      mockList.mockResolvedValue({
        data: {
          list: [...mockManuals, {
            id: '4',
            product_id: 'PROD-004',
            attachment_id: 'att-4',
            doc_type: 'certificate',
            parse_status: 'pending',
            index_status: 'pending',
            parser_name: null,
            parser_version: null,
            parse_error: null,
            index_error: null,
            create_time: '2024-01-04T00:00:00Z',
            update_time: '2024-01-04T00:00:00Z',
          }],
          total: 4,
        },
      })

      await btnByText(wrapper, '刷新状态')!.trigger('click')
      await flushPromises()

      expect(mockList).toHaveBeenCalledTimes(2)
      expect(wrapper.text()).toContain('PROD-004')
    })
  })

  describe('statusType', () => {
    it('returns success for parsed and indexed', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      const wrapper = await factory()
      const tags = wrapper.findAllComponents(ElTag)
      const statuses = tags.map((t: any) => t.props('type'))
      expect(statuses).toContain('success')
    })

    it('returns warning for processing', async () => {
      mockList.mockResolvedValue({
        data: {
          list: [{
            ...mockManuals[0],
            parse_status: 'processing',
            index_status: 'processing',
          }],
          total: 1,
        },
      })
      const wrapper = await factory()
      const tags = wrapper.findAllComponents(ElTag)
      const types = tags.map((t: any) => t.props('type'))
      expect(types).toContain('warning')
    })

    it('returns danger for failed', async () => {
      mockList.mockResolvedValue({ data: { list: mockManuals, total: 3 } })
      const wrapper = await factory()
      const tags = wrapper.findAllComponents(ElTag)
      const types = tags.map((t: any) => t.props('type'))
      expect(types).toContain('danger')
    })
  })
})
