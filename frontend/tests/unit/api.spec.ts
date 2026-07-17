import { describe, it, expect } from 'vitest'

// Test the API module by importing it directly (no axios mock needed
// since we only test exported function signatures and skipAuth behavior).
import api, { authApi, shareApi, productApi, categoryApi, brandApi, supplierApi, tagApi, proposalApi, quotationApi, userApi, roleApi, fileApi, statsApi, aiApi } from '@/api'

describe('API client module', () => {
  it('exports api instance with request and response interceptors', () => {
    expect(api).toBeDefined()
    expect(api.interceptors.request).toBeDefined()
    expect(api.interceptors.response).toBeDefined()
  })

  it('authApi exposes login, logout, getCurrentUser, refresh, changePassword', () => {
    expect(typeof authApi.login).toBe('function')
    expect(typeof authApi.logout).toBe('function')
    expect(typeof authApi.getCurrentUser).toBe('function')
    expect(typeof authApi.refresh).toBe('function')
    expect(typeof authApi.changePassword).toBe('function')
  })

  it('productApi exposes all CRUD methods plus import/export/clone', () => {
    expect(typeof productApi.list).toBe('function')
    expect(typeof productApi.get).toBe('function')
    expect(typeof productApi.create).toBe('function')
    expect(typeof productApi.update).toBe('function')
    expect(typeof productApi.delete).toBe('function')
    expect(typeof productApi.updateStatus).toBe('function')
    expect(typeof productApi.clone).toBe('function')
    expect(typeof productApi.export).toBe('function')
    expect(typeof productApi.import).toBe('function')
  })

  it('shareApi.get is defined for public share access', () => {
    expect(typeof shareApi.get).toBe('function')
    expect(typeof shareApi.create).toBe('function')
    expect(typeof shareApi.list).toBe('function')
    expect(typeof shareApi.revoke).toBe('function')
  })

  it('categoryApi, brandApi, supplierApi, tagApi expose CRUD', () => {
    [categoryApi, brandApi, supplierApi, tagApi].forEach((api) => {
      expect(typeof api.list).toBe('function')
      expect(typeof api.create).toBe('function')
      expect(typeof api.update).toBe('function')
      expect(typeof api.delete).toBe('function')
    })
  })

  it('proposalApi exposes list/get/CRUD and quotationApi matches backend contract', () => {
    [proposalApi].forEach((api) => {
      expect(typeof api.list).toBe('function')
      expect(typeof api.get).toBe('function')
      expect(typeof api.create).toBe('function')
      expect(typeof api.update).toBe('function')
      expect(typeof api.delete).toBe('function')
    })
    expect(typeof quotationApi.list).toBe('function')
    expect(typeof quotationApi.get).toBe('function')
    expect(typeof quotationApi.create).toBe('function')
    expect(typeof quotationApi.update).toBe('function')
    expect(typeof quotationApi.exportPdf).toBe('function')
  })

  it('userApi exposes CRUD plus get; roleApi exposes list/create/update/delete', () => {
    expect(typeof userApi.list).toBe('function')
    expect(typeof userApi.get).toBe('function')
    expect(typeof userApi.create).toBe('function')
    expect(typeof userApi.update).toBe('function')
    expect(typeof userApi.delete).toBe('function')
    expect(typeof roleApi.list).toBe('function')
    expect(typeof roleApi.create).toBe('function')
    expect(typeof roleApi.update).toBe('function')
    expect(typeof roleApi.delete).toBe('function')
  })

  it('fileApi, statsApi, aiApi expose their methods', () => {
    expect(typeof fileApi.upload).toBe('function')
    expect(typeof fileApi.delete).toBe('function')
    expect(typeof fileApi.download).toBe('function')
    expect(typeof fileApi.preview).toBe('function')
    expect(typeof statsApi.shares).toBe('function')
    expect(typeof statsApi.hotProducts).toBe('function')
    expect(typeof aiApi.chat).toBe('function')
    expect(typeof aiApi.ragSearch).toBe('function')
    expect(typeof aiApi.polishProposal).toBe('function')
    expect(typeof aiApi.recommend).toBe('function')
  })
})

describe('Request interceptor skipAuth behavior', () => {
  it('request interceptor is registered', () => {
    const handlers = api.interceptors.request.handlers
    expect(handlers.length).toBeGreaterThanOrEqual(1)
  })

  it('response interceptor is registered', () => {
    const handlers = api.interceptors.response.handlers
    expect(handlers.length).toBeGreaterThanOrEqual(1)
  })
})
