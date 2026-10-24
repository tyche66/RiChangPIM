import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Track B：Skills 管理中心入口仅管理员可见。
// 这里锁定 MainLayout 模板的 gating 表达式与 router 的 adminOnly 约定。
// 真正的安全边界在后端 app/api/v1/content_skills.py::_require_admin（401/403 测试
// 见 backend/tests/unit/test_content_skills_admin.py）；本文件只固化前端可见性契约。

const root = resolve(__dirname, '../..')
const layout = readFileSync(resolve(root, 'src/layouts/MainLayout.vue'), 'utf-8')
const router = readFileSync(resolve(root, 'src/router.ts'), 'utf-8')
const permissions = readFileSync(resolve(root, 'src/types/permissions.ts'), 'utf-8')

describe('Skills management entry is admin-only in the layout', () => {
  it('the Skills menu item is gated by isAdmin', () => {
    // 抓取 index="/content/skills" 那个 menu-item 的 v-if
    const block = layout.slice(
      layout.indexOf('index="/content/skills"') - 260,
      layout.indexOf('index="/content/skills"'),
    )
    expect(block).toContain('v-if="isAdmin"')
  })

  it('the topic entry is gated by content:view, not admin', () => {
    const block = layout.slice(
      layout.indexOf('index="/content/topics"') - 260,
      layout.indexOf('index="/content/topics"'),
    )
    expect(block).toContain("hasPerm('content:view')")
    expect(block).not.toContain('isAdmin')
  })

  it('isAdmin is derived from authStore.userRoleCode', () => {
    expect(layout).toMatch(/const isAdmin = computed\(\(\) => authStore\.userRoleCode === 'admin'\)/)
  })

  it('showCrmMenu includes isAdmin so admins always see the group', () => {
    const block = layout.slice(
      layout.indexOf('const showCrmMenu'),
      layout.indexOf('const showCrmMenu') + 260,
    )
    expect(block).toContain('isAdmin.value')
  })
})

describe('router guards the Skills centre by role, not just permission', () => {
  it('the skills route declares adminOnly', () => {
    const block = router.slice(
      router.indexOf("path: 'content/skills'"),
      router.indexOf("path: 'content/skills'") + 320,
    )
    expect(block).toContain('adminOnly: true')
  })

  it('the beforeEach guard rejects adminOnly routes for non-admin', () => {
    expect(router).toContain("to.meta.adminOnly && authStore.userRoleCode !== 'admin'")
  })

  it('the topics route has no adminOnly flag', () => {
    const block = router.slice(
      router.indexOf("path: 'content/topics'"),
      router.indexOf("path: 'content/topics'") + 320,
    )
    expect(block).not.toContain('adminOnly')
  })
})

describe('content:manage permission is part of the frontend contract', () => {
  it('is declared in PERMISSIONS', () => {
    expect(permissions).toContain("'content:manage'")
  })

  it('is listed under the content resource', () => {
    const block = permissions.slice(
      permissions.indexOf('content: ['),
      permissions.indexOf('content: [') + 240,
    )
    expect(block).toContain("'content:manage'")
  })

  it('has a display name', () => {
    expect(permissions).toContain("'content:manage': '内容Skill管理'")
  })
})
