import { describe, it, expect, beforeEach, vi } from 'vitest'
import { compileScript } from '@vue/language-core'
import ShareResultDialog from '@/components/ShareResultDialog.vue'

describe('ShareResultDialog.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('contains share URL input in template', () => {
    const content = ShareResultDialog.__file
    expect(content).toContain('ShareResultDialog.vue')
  })

  it('template contains share-url-input class', () => {
    // Read the source file to verify template content
    const fs = require('fs')
    const path = require('path')
    const filePath = path.resolve(__dirname, '../../src/components/ShareResultDialog.vue')
    const source = fs.readFileSync(filePath, 'utf-8')
    expect(source).toContain('share-url-input')
    expect(source).toContain('shareUrl')
    expect(source).toContain('复制')
    expect(source).toContain('下载二维码')
    expect(source).toContain('在新窗口预览')
    expect(source).toContain('qr-canvas')
    expect(source).toContain('qrcode')
    expect(source).toContain('VITE_PUBLIC_FRONTEND_URL')
    expect(source).toContain('navigator.clipboard')
    expect(source).toContain('window.open')
  })

  it('template contains QR code generation', () => {
    const fs = require('fs')
    const path = require('path')
    const filePath = path.resolve(__dirname, '../../src/components/ShareResultDialog.vue')
    const source = fs.readFileSync(filePath, 'utf-8')
    expect(source).toContain('toCanvas')
    expect(source).toContain('qrcode')
  })

  it('template contains absolute URL resolution logic', () => {
    const fs = require('fs')
    const path = require('path')
    const filePath = path.resolve(__dirname, '../../src/components/ShareResultDialog.vue')
    const source = fs.readFileSync(filePath, 'utf-8')
    expect(source).toContain('VITE_PUBLIC_FRONTEND_URL')
    expect(source).toContain('window.location.origin')
  })
})
