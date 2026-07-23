import { describe, it, expect } from 'vitest'
import {
  PERMISSIONS,
  hasPermission,
  hasAnyPermission,
  hasAllPermissions,
  RESOURCE_PERMISSIONS,
} from '@/types/permissions'

describe('PERMISSIONS constant', () => {
  it('contains exactly 57 permission codes', () => {
    expect(PERMISSIONS).toHaveLength(57)
  })

  it('has no duplicate codes', () => {
    const unique = new Set(PERMISSIONS)
    expect(unique.size).toBe(PERMISSIONS.length)
  })

  it('all codes follow resource:action format', () => {
    PERMISSIONS.forEach((p) => {
      expect(p).toMatch(/^[a-z_]+:[a-z]+$/)
    })
  })

  it('includes all expected product permissions', () => {
    const productPerms = PERMISSIONS.filter((p) => p.startsWith('product:'))
    expect(productPerms).toContain('product:view')
    expect(productPerms).toContain('product:create')
    expect(productPerms).toContain('product:edit')
    expect(productPerms).toContain('product:delete')
    expect(productPerms).toContain('product:import')
    expect(productPerms).toContain('product:export')
    expect(productPerms).toContain('product:status')
    expect(productPerms).toContain('product:clone')
  })

  it('includes role:assign permission', () => {
    expect(PERMISSIONS).toContain('role:assign')
  })

  it('includes ai:use permission', () => {
    expect(PERMISSIONS).toContain('ai:use')
  })
})

describe('hasPermission', () => {
  it('returns true when user has the permission', () => {
    expect(hasPermission(['product:view', 'product:edit'], 'product:view')).toBe(true)
  })

  it('returns false when user lacks the permission', () => {
    expect(hasPermission(['product:view'], 'product:edit')).toBe(false)
  })

  it('returns false for empty permissions list', () => {
    expect(hasPermission([], 'product:view')).toBe(false)
  })
})

describe('hasAnyPermission', () => {
  it('returns true if user has at least one of the requested permissions', () => {
    expect(hasAnyPermission(['product:view', 'category:view'], ['product:edit', 'product:view'])).toBe(true)
  })

  it('returns false if user has none of the requested permissions', () => {
    expect(hasAnyPermission(['product:view'], ['category:view', 'brand:view'])).toBe(false)
  })
})

describe('hasAllPermissions', () => {
  it('returns true only if user has every requested permission', () => {
    expect(hasAllPermissions(['product:view', 'product:edit'], ['product:view', 'product:edit'])).toBe(true)
    expect(hasAllPermissions(['product:view'], ['product:view', 'product:edit'])).toBe(false)
  })
})

describe('RESOURCE_PERMISSIONS', () => {
  it('covers all resources defined in the backend', () => {
    const resources = Object.keys(RESOURCE_PERMISSIONS)
    expect(resources).toContain('product')
    expect(resources).toContain('category')
    expect(resources).toContain('brand')
    expect(resources).toContain('tag')
    expect(resources).toContain('supplier')
    expect(resources).toContain('user')
    expect(resources).toContain('role')
    expect(resources).toContain('proposal')
    expect(resources).toContain('quotation')
    expect(resources).toContain('share')
    expect(resources).toContain('file')
    expect(resources).toContain('media')
    expect(resources).toContain('scene_image')
    expect(resources).toContain('stats')
    expect(resources).toContain('ai')
  })

  it('product resource has 8 permissions', () => {
    expect(RESOURCE_PERMISSIONS.product).toHaveLength(8)
  })

  it('role resource has 5 permissions', () => {
    expect(RESOURCE_PERMISSIONS.role).toHaveLength(5)
    expect(RESOURCE_PERMISSIONS.role).toContain('role:assign')
  })
})

describe('Admin role simulation', () => {
  it('admin with all permissions passes every check', () => {
    const adminPerms = [...PERMISSIONS] as string[]
    expect(hasPermission(adminPerms, 'user:delete')).toBe(true)
    expect(hasAnyPermission(adminPerms, ['ai:use', 'nonexistent'])).toBe(true)
    expect(hasAllPermissions(adminPerms, ['product:view', 'role:assign'])).toBe(true)
  })
})

describe('Viewer role simulation', () => {
  it('viewer has only product:view and stats:view', () => {
    const viewerPerms: string[] = ['product:view', 'stats:view']
    expect(hasPermission(viewerPerms, 'product:view')).toBe(true)
    expect(hasPermission(viewerPerms, 'product:create')).toBe(false)
    expect(hasPermission(viewerPerms, 'user:view')).toBe(false)
    expect(hasAnyPermission(viewerPerms, ['product:create', 'stats:view'])).toBe(true)
    expect(hasAllPermissions(viewerPerms, ['product:view', 'product:edit'])).toBe(false)
  })
})

describe('Media permissions', () => {
  it('includes all media permission codes', () => {
    expect(PERMISSIONS).toContain('media:view')
    expect(PERMISSIONS).toContain('media:upload')
    expect(PERMISSIONS).toContain('media:delete')
    expect(PERMISSIONS).toContain('media:replace')
  })

  it('media resource has 4 permissions', () => {
    expect(RESOURCE_PERMISSIONS.media).toHaveLength(4)
    expect(RESOURCE_PERMISSIONS.media).toContain('media:replace')
  })
})

describe('Scene image permissions', () => {
  it('includes all scene_image permission codes', () => {
    expect(PERMISSIONS).toContain('scene_image:view')
    expect(PERMISSIONS).toContain('scene_image:create')
    expect(PERMISSIONS).toContain('scene_image:edit')
    expect(PERMISSIONS).toContain('scene_image:delete')
  })

  it('scene_image resource has 4 permissions', () => {
    expect(RESOURCE_PERMISSIONS.scene_image).toHaveLength(4)
    expect(RESOURCE_PERMISSIONS.scene_image).toContain('scene_image:delete')
  })
})
