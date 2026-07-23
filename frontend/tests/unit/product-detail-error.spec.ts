import { AxiosError } from 'axios'
import { describe, expect, it } from 'vitest'
import { classifyProductDetailError } from '@/utils/productDetailError'

function httpError(status: number) {
  return new AxiosError(
    `HTTP ${status}`,
    undefined,
    undefined,
    undefined,
    { status, statusText: String(status), headers: {}, config: { headers: {} }, data: {} },
  )
}

describe('product detail errors', () => {
  it('maps only 404 to not found', () => {
    expect(classifyProductDetailError(httpError(404))).toBe('not-found')
    expect(classifyProductDetailError(httpError(500))).toBe('server-error')
    expect(classifyProductDetailError(httpError(403))).toBe('forbidden')
    expect(classifyProductDetailError(httpError(401))).toBe('unauthorized')
    expect(classifyProductDetailError(new Error('offline'))).toBe('network-error')
  })
})
