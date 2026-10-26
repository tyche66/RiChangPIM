import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/api', () => ({
  default: mocks,
}))

import { contentApi } from '@/api/content'

describe('content model API contract', () => {
  beforeEach(() => {
    mocks.get.mockReset()
    mocks.post.mockReset()
    mocks.get.mockResolvedValue({
      code: 200,
      data: {
        models: ['step-5-preview', 'sensenova-6.8-flash-lite'],
        default_model: 'step-5-preview',
      },
    })
    mocks.post.mockResolvedValue({ code: 200, data: {} })
  })

  it('loads the server allowlist from GET /content/models', async () => {
    const res = await contentApi.listModels()

    expect(mocks.get).toHaveBeenCalledWith('/content/models', {
      suppressErrorMessage: true,
    })
    expect(res.data.models).toEqual([
      'step-5-preview',
      'sensenova-6.8-flash-lite',
    ])
    expect(res.data.default_model).toBe('step-5-preview')
    expect(JSON.stringify(res.data)).not.toContain('key')
  })

  it('sends an explicitly selected model with content generation', async () => {
    await contentApi.generate({
      title: '测试批次',
      topic: '会议区选型',
      platform: 'xhs',
      model_name: 'sensenova-6.8-flash-lite',
    })

    // 第三个参数是内容生成的 305s 超时配置，一并锁定防止回归。
    expect(mocks.post).toHaveBeenCalledWith(
      '/content/batches',
      expect.objectContaining({ model_name: 'sensenova-6.8-flash-lite' }),
      { timeout: 305000 },
    )
  })

  it('sends an explicitly selected model with topic runs', async () => {
    await contentApi.createTopicRun({
      topic: '会议区选型',
      model_name: 'sensenova-6.8-flash-lite',
    })

    expect(mocks.post).toHaveBeenCalledWith(
      '/content/topics/runs',
      expect.objectContaining({ model_name: 'sensenova-6.8-flash-lite' }),
      { timeout: 305000 },
    )
  })

  it('keeps the model optional so auto mode can omit it', async () => {
    await contentApi.generate({
      title: '测试批次',
      topic: '会议区选型',
      platform: 'xhs',
    })

    expect(mocks.post).toHaveBeenCalledWith(
      '/content/batches',
      expect.not.objectContaining({ model_name: expect.anything() }),
      { timeout: 305000 },
    )
  })
})
