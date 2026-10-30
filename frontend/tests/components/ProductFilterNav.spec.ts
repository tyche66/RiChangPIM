import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import type { ProductFilterOption } from '@/api'

const SERIES_LEVEL2: ProductFilterOption[] = [
  { value: 'cat-desk', label: '办公桌', count: 12 },
  { value: 'cat-chair', label: '办公椅', count: 5 },
]
const SERIES_LEVEL3: ProductFilterOption[] = [
  { value: 'tag-metropolis', label: '大都会', count: 6 },
  { value: 'tag-varner', label: '瓦尔纳', count: 3 },
]
const BRAND_LEVEL2: ProductFilterOption[] = [{ value: 'brand-1', label: '品牌甲', count: 9 }]
const BRAND_LEVEL3: ProductFilterOption[] = [{ value: 'cat-desk', label: '办公桌', count: 9 }]
const SPEC_LEVEL3: ProductFilterOption[] = [
  { value: '1800', label: '1800', count: 4 },
  { value: '2200', label: '2200', count: 2 },
]

const filterOptions = vi.fn(
  async (params: { dimension: string; parent_id?: string }) => {
    let items: ProductFilterOption[] = []
    if (params.dimension === 'series') {
      items = params.parent_id ? SERIES_LEVEL3 : SERIES_LEVEL2
    } else if (params.dimension === 'brand') {
      items = params.parent_id ? BRAND_LEVEL3 : BRAND_LEVEL2
    } else if (params.dimension === 'category') {
      items = params.parent_id ? SPEC_LEVEL3 : SERIES_LEVEL2
    } else if (params.dimension === 'status') {
      items = [
        { value: 'active', label: '上架', count: 10 },
        { value: 'draft', label: '草稿', count: 2 },
      ]
    }
    return { code: 200, data: { dimension: params.dimension, items } }
  },
)

vi.mock('@/api', () => ({
  productApi: {
    filterOptions: (params: { dimension: string; parent_id?: string }) =>
      filterOptions(params),
  },
}))

import ProductFilterNav from '@/components/ProductFilterNav.vue'

function mountNav() {
  const wrapper = mount(ProductFilterNav)
  mounted.push(wrapper)
  return wrapper
}

const mounted: Array<ReturnType<typeof mountNav>> = []

function chips(wrapper: ReturnType<typeof mountNav>): string[] {
  return wrapper.findAll('.filter-nav__chips .filter-chip').map((chip) => chip.text())
}

function tabByLabel(wrapper: ReturnType<typeof mountNav>, label: string) {
  const tab = wrapper.findAll('.filter-nav__tab').find((item) => item.text() === label)
  if (!tab) throw new Error(`tab not found: ${label}`)
  return tab
}

beforeEach(() => {
  filterOptions.mockClear()
})

afterEach(() => {
  while (mounted.length) mounted.pop()?.unmount()
})

describe('ProductFilterNav', () => {
  it('默认选中「系列」并加载二级分类', async () => {
    const wrapper = mountNav()
    await flushPromises()

    expect(wrapper.find('.filter-nav__tab.is-active').text()).toBe('系列')
    expect(filterOptions).toHaveBeenCalledWith({ dimension: 'series' })
    expect(chips(wrapper)).toEqual(['全部', '办公桌 12', '办公椅 5'])
  })

  it('切换一级标签会清空下级并通知父页面', async () => {
    const wrapper = mountNav()
    await flushPromises()

    await tabByLabel(wrapper, '品牌').trigger('click')
    await flushPromises()

    expect(filterOptions).toHaveBeenLastCalledWith({ dimension: 'brand' })
    expect(chips(wrapper)).toEqual(['全部', '品牌甲 9'])
    expect(wrapper.emitted('change')?.at(-1)).toEqual([
      { dimension: 'brand', level2: '', level3: '' },
    ])
  })

  it('选中二级后加载三级，选中三级回传具体值', async () => {
    const wrapper = mountNav()
    await flushPromises()

    const desk = wrapper.findAll('.filter-nav__chips .filter-chip').find((chip) => chip.text().startsWith('办公桌'))
    await desk?.trigger('click')
    await flushPromises()

    expect(filterOptions).toHaveBeenLastCalledWith({ dimension: 'series', parent_id: 'cat-desk' })
    const rows = wrapper.findAll('.filter-nav__row')
    expect(rows.length).toBe(2)
    expect(rows[1].text()).toContain('大都会')

    const third = wrapper.findAll('.filter-nav__chips--compact .filter-chip').find((chip) => chip.text().startsWith('大都会'))
    await third?.trigger('click')
    await flushPromises()

    expect(wrapper.emitted('change')?.at(-1)).toEqual([
      { dimension: 'series', level2: 'cat-desk', level3: 'tag-metropolis' },
    ])
  })

  it('品类维度的三级是规格长度，与系列的系列名互不串数据', async () => {
    const wrapper = mountNav()
    await flushPromises()

    await tabByLabel(wrapper, '品类').trigger('click')
    await flushPromises()
    await wrapper.findAll('.filter-nav__chips .filter-chip')[1].trigger('click')
    await flushPromises()

    const thirdLabels = wrapper
      .findAll('.filter-nav__chips--compact .filter-chip')
      .map((chip) => chip.text())
    expect(thirdLabels).toEqual(['全部', '1800 4', '2200 2'])
    expect(wrapper.find('.filter-nav__row--sub').text()).toContain('长度(mm)')

    await wrapper.findAll('.filter-nav__chips--compact .filter-chip')[1].trigger('click')
    await flushPromises()
    expect(wrapper.emitted('change')?.at(-1)).toEqual([
      { dimension: 'category', level2: 'cat-desk', level3: '1800' },
    ])
  })

  it('状态维度没有三级菜单', async () => {
    const wrapper = mountNav()
    await flushPromises()

    await tabByLabel(wrapper, '状态').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('.filter-nav__row--sub').length).toBe(0)
    expect(chips(wrapper)).toEqual(['全部', '上架 10', '草稿 2'])
  })

  it('reset() 回到「系列 + 全部」并通知父页面', async () => {
    const wrapper = mountNav()
    await flushPromises()
    await tabByLabel(wrapper, '品牌').trigger('click')
    await flushPromises()

    ;(wrapper.vm as unknown as { reset: () => void }).reset()
    await flushPromises()

    expect(wrapper.find('.filter-nav__tab.is-active').text()).toBe('系列')
    expect(wrapper.emitted('change')?.at(-1)).toEqual([
      { dimension: 'series', level2: '', level3: '' },
    ])
  })

  it('指示条跟随选中标签移动', async () => {
    const wrapper = mountNav()
    await flushPromises()
    await nextTick()

    const indicator = wrapper.find('.filter-nav__indicator')
    expect(indicator.exists()).toBe(true)
    expect(indicator.attributes('style')).toContain('translate')
  })
})
