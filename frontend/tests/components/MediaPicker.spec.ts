import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

vi.mock('@/api/media', () => ({
  mediaApi: { list: vi.fn() },
  formatSize: (n: number) => `${n}B`,
}))

import { mediaApi } from '@/api/media'
import MediaPicker from '@/components/MediaPicker.vue'

const mockList = mediaApi.list as ReturnType<typeof vi.fn>

describe('MediaPicker', () => {
  beforeEach(() => {
    mockList.mockReset()
  })

  it('emits multiple selected items when multiple mode is enabled', async () => {
    mockList.mockResolvedValue([
      { id: 'm1', name: 'one.png', type: 'image', mimeType: 'image/png', size: 10, url: '/1', uploadedAt: '2024-01-01' },
      { id: 'm2', name: 'two.png', type: 'image', mimeType: 'image/png', size: 20, url: '/2', uploadedAt: '2024-01-01' },
    ])

    const wrapper = mount(MediaPicker, {
      props: { modelValue: true, multiple: true },
      attachTo: document.body,
      global: {
        plugins: [ElementPlus],
        stubs: {
          ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
        },
      },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as { selectedIds: string[]; confirm: () => void }
    vm.items = [
      { id: 'm1', name: 'one.png', type: 'image', mimeType: 'image/png', size: 10, url: '/1', uploadedAt: '2024-01-01' },
      { id: 'm2', name: 'two.png', type: 'image', mimeType: 'image/png', size: 20, url: '/2', uploadedAt: '2024-01-01' },
    ]
    vm.selectedIds = ['m1', 'm2']
    vm.confirm()

    expect((wrapper.emitted('select')?.[0]?.[0] as any[]).length).toBe(2)
  })

  it('emits a single item in single-select mode', async () => {
    mockList.mockResolvedValue([
      { id: 'm1', name: 'one.png', type: 'image', mimeType: 'image/png', size: 10, url: '/1', uploadedAt: '2024-01-01' },
    ])

    const wrapper = mount(MediaPicker, {
      props: { modelValue: true },
      attachTo: document.body,
      global: {
        plugins: [ElementPlus],
        stubs: {
          ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
        },
      },
    })
    await flushPromises()
    const vm = wrapper.vm as unknown as { selectedIds: string[]; confirm: () => void }
    vm.items = [
      { id: 'm1', name: 'one.png', type: 'image', mimeType: 'image/png', size: 10, url: '/1', uploadedAt: '2024-01-01' },
    ]
    vm.selectedIds = ['m1']
    vm.confirm()

    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ id: 'm1' })
  })
})
