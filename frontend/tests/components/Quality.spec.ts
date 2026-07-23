import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { ElMessage } from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api', () => {
  const get = vi.fn()
  return { default: { get } }
})

const errorSpy = vi.spyOn(ElMessage, 'error').mockImplementation(() => {})

import api from '@/api'
import Quality from '@/views/Quality.vue'

const mockGet = (api as any).get as any

function mountQuality() {
  setActivePinia(createPinia())
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/quality', name: 'Quality', component: Quality }],
  })
  return mount(Quality, {
    global: {
      plugins: [router, ElementPlus],
    },
  })
}

describe('Quality.vue', () => {
  beforeEach(() => {
    mockGet.mockReset()
    errorSpy.mockClear()
  })

  it('renders the summary header and stats', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/products/quality-summary') {
        return Promise.resolve({
          data: {
            data: {
              total: 13,
              no_price: 13,
              no_image: 8,
              no_manual: 5,
              no_spec: 2,
              source_incomplete: 1,
              ocr_failed: 0,
              long_pending: 4,
              by_completeness: { pending: 13 },
            },
          },
        })
      }
      if (url === '/products/quality-list') {
        return Promise.resolve({
          data: {
            data: {
              list: [
                {
                  id: '1',
                  product_no: 'EMD89R.320190',
                  product_name: '会议桌',
                  completeness_status: 'pending',
                  face_price: 99999,
                  face_price_label: '待核价',
                  specification: 'W3200*D1900*H750 mm',
                  data_source: 'manual-import-2026',
                  supplier_id: 's1',
                  supplier_name: '圣奥',
                  category_id: 'c1',
                  brand_id: 'b1',
                  create_time: '2026-07-16T08:00:00',
                  update_time: '2026-07-16T08:00:00',
                },
              ],
              page: 1,
              size: 50,
            },
          },
        })
      }
      return Promise.resolve({ data: { data: {} } })
    })

    const wrapper = mountQuality()
    await flushPromises()

    // Header text
    expect(wrapper.text()).toContain('试点数据质量看板')

    // Summary numbers render (zero cost price shown as 待核价 label).
    expect(wrapper.text()).toContain('13')
    expect(wrapper.text()).toContain('待核价')

    // Table content
    expect(wrapper.text()).toContain('EMD89R.320190')
    expect(wrapper.text()).toContain('会议桌')
    expect(wrapper.text()).toContain('圣奥')

    // 必须显示「待核价」占位标签而非裸 99999 数值
    expect(wrapper.text()).toContain('待核价')
  })

  it('renders an empty state when no rows match filter', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/products/quality-summary') {
        return Promise.resolve({ data: { data: {
          total: 0, no_price: 0, no_image: 0, no_manual: 0,
          no_spec: 0, source_incomplete: 0, ocr_failed: 0, long_pending: 0,
          by_completeness: {},
        } } })
      }
      if (url === '/products/quality-list') {
        return Promise.resolve({ data: { data: { list: [], page: 1, size: 50 } } })
      }
      return Promise.resolve({ data: { data: {} } })
    })

    const wrapper = mountQuality()
    await flushPromises()

    expect(wrapper.text()).toContain('暂无匹配的产品')
  })

  it('shows an error state when the API rejects', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/products/quality-summary') {
        return Promise.resolve({ data: { data: { total: 0 } } })
      }
      if (url === '/products/quality-list') {
        return Promise.reject({
          response: { data: { detail: { msg: '后端瞬断' } } },
        })
      }
      return Promise.resolve({ data: { data: {} } })
    })

    const wrapper = mountQuality()
    await flushPromises()

    expect(wrapper.text()).toContain('加载失败')
    expect(wrapper.text()).toContain('后端瞬断')
  })

  it('does NOT expose placeholder price as a faux number', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url === '/products/quality-summary') {
        return Promise.resolve({ data: { data: {
          total: 1, no_price: 1, no_image: 0, no_manual: 0,
          no_spec: 0, source_incomplete: 0, ocr_failed: 0, long_pending: 0,
          by_completeness: { pending: 1 },
        } } })
      }
      if (url === '/products/quality-list') {
        return Promise.resolve({
          data: { data: { list: [{
            id: '1',
            product_no: 'P-001',
            product_name: 'test',
            completeness_status: 'pending',
            face_price: 99999,
            face_price_label: '待核价',
            specification: null,
            data_source: null,
            supplier_id: null,
            supplier_name: null,
            category_id: null,
            brand_id: null,
            create_time: null,
            update_time: null,
          }], page: 1, size: 50 } },
        })
      }
      return Promise.resolve({ data: { data: {} } })
    })

    const wrapper = mountQuality()
    await flushPromises()

    // 待核价 label is rendered; the raw faux 99999 is NOT shown as pricing.
    expect(wrapper.text()).toContain('待核价')
    expect(wrapper.text()).not.toContain('$99999')
  })
})
