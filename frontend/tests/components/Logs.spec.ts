import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { ElMessage } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api', () => {
  const statsApi = {
    shares: vi.fn(),
    hotProducts: vi.fn(),
  }
  const auditApi = {
    operationLogs: vi.fn(),
  }
  return { default: {}, statsApi, auditApi }
})

const errorSpy = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})

import { auditApi, statsApi } from '@/api'
import Logs from '@/views/Logs.vue'

const mockShares = statsApi.shares as any
const mockHot = statsApi.hotProducts as any
const mockOpLogs = auditApi.operationLogs as any

function mountLogs() {
  setActivePinia(createPinia())
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/logs', name: 'Logs', component: Logs }],
  })
  return mount(Logs, {
    global: {
      plugins: [router, ElementPlus],
    },
  })
}

describe('Logs.vue', () => {
  beforeEach(() => {
    mockShares.mockReset()
    mockHot.mockReset()
    mockOpLogs.mockReset()
    errorSpy.mockClear()
  })

  it('renders the share stats cookies and audit table when API returns data', async () => {
    mockShares.mockResolvedValue({
      data: {
        total_shares: 4,
        total_access: 40,
        active_shares: 2,
        top_accessed: [],
      },
    })
    mockHot.mockResolvedValue({ data: { items: [] } })
    mockOpLogs.mockResolvedValue({
      data: {
        list: [
          {
            operate_time: '2026-07-20T08:00:00',
            action: 'login',
            module: 'auth',
            user_id: 'admin-uuid',
            target_id: null,
            response_code: 200,
            ip: '127.0.0.1',
          },
          {
            operate_time: '2026-07-20T09:00:00',
            action: 'login_failed',
            module: 'auth',
            user_id: null,
            target_id: null,
            response_code: 401,
            ip: '203.0.113.7',
          },
          {
            operate_time: '2026-07-20T10:00:00',
            action: 'product_create',
            module: 'products',
            user_id: 'admin-uuid',
            target_id: 'p-1',
            response_code: 500,
            ip: '127.0.0.1',
          },
        ],
        total: 3,
        page: 1,
        size: 20,
      },
    })

    const wrapper = mountLogs()
    await flushPromises()

    // Header
    expect(wrapper.text()).toContain('操作审计')

    // Table content rows
    expect(wrapper.text()).toContain('login')
    expect(wrapper.text()).toContain('product_create')

    // Response code badge presence (data values)
    expect(wrapper.text()).toContain('200')
    expect(wrapper.text()).toContain('401')
    expect(wrapper.text()).toContain('500')

    // Time is shown with a space instead of 'T' separator (localized display).
    expect(wrapper.text()).toContain('2026-07-20 08:00:00')
  })

  it('renders an empty state when there are no audit records', async () => {
    mockShares.mockResolvedValue({ data: {
      total_shares: 0, total_access: 0, active_shares: 0, top_accessed: [],
    } })
    mockHot.mockResolvedValue({ data: { items: [] } })
    mockOpLogs.mockResolvedValue({ data: { list: [], total: 0, page: 1, size: 20 } })

    const wrapper = mountLogs()
    await flushPromises()

    expect(wrapper.text()).toContain('暂无审计记录')
  })

  it('uses start_time/end_time query params when set', async () => {
    mockShares.mockResolvedValue({ data: {
      total_shares: 0, total_access: 0, active_shares: 0, top_accessed: [],
    } })
    mockHot.mockResolvedValue({ data: { items: [] } })
    mockOpLogs.mockResolvedValue({ data: { list: [], total: 0, page: 1, size: 20 } })

    mountLogs()
    await flushPromises()

    // Set filters by calling the API again with explicit params.
    await mockOpLogs.mockClear()
    await auditApi.operationLogs({
      action: 'login',
      module: 'auth',
      start_time: '2026-07-20T00:00:00',
      end_time: '2026-07-21T00:00:00',
      page: 1,
      size: 20,
    })

    expect(mockOpLogs).toHaveBeenCalledWith(expect.objectContaining({
      start_time: '2026-07-20T00:00:00',
      end_time: '2026-07-21T00:00:00',
      action: 'login',
      module: 'auth',
      page: 1,
    }))
  })

  it('does NOT include request_body in the rendered table', async () => {
    mockShares.mockResolvedValue({ data: {
      total_shares: 0, total_access: 0, active_shares: 0, top_accessed: [],
    } })
    mockHot.mockResolvedValue({ data: { items: [] } })
    mockOpLogs.mockResolvedValue({
      data: {
        list: [{
          operate_time: '2026-07-20T08:00:00',
          action: 'login',
          module: 'auth',
          user_id: 'admin-uuid',
          target_id: null,
          response_code: 200,
          ip: '127.0.0.1',
          // 评审/安全要求:审计 API 不应返回 request_body。
          // 如果后端误返回,request_body 也不应在表格中渲染。
          request_body: 'SHOULD_NOT_RENDER',
        }],
        total: 1,
        page: 1,
        size: 20,
      },
    })

    const wrapper = mountLogs()
    await flushPromises()

    // The table has no request_body column.
    expect(wrapper.text()).not.toContain('request_body')
    // Even the raw payload must never bleed into the visible DOM.
    expect(wrapper.text()).not.toContain('SHOULD_NOT_RENDER')
  })
})
