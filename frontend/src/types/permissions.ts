export const PERMISSIONS = [
  'product:view',
  'product:create',
  'product:edit',
  'product:delete',
  'product:import',
  'product:export',
  'product:status',
  'product:clone',
  'category:view',
  'category:create',
  'category:edit',
  'category:delete',
  'brand:view',
  'brand:create',
  'brand:edit',
  'brand:delete',
  'tag:view',
  'tag:create',
  'tag:edit',
  'tag:delete',
  'supplier:view',
  'supplier:create',
  'supplier:edit',
  'supplier:delete',
  'user:view',
  'user:create',
  'user:edit',
  'user:delete',
  'role:view',
  'role:create',
  'role:edit',
  'role:delete',
  'role:assign',
  'proposal:view',
  'proposal:create',
  'proposal:edit',
  'proposal:delete',
  'quotation:view',
  'quotation:create',
  'quotation:edit',
  'quotation:delete',
  'share:view',
  'share:create',
  'share:delete',
  'file:view',
  'file:upload',
  'file:delete',
  'stats:view',
  'ai:use',
] as const

export type PermissionCode = (typeof PERMISSIONS)[number]

export function hasPermission(permissions: string[], perm: PermissionCode | string): boolean {
  return permissions.includes(perm)
}

export function hasAnyPermission(permissions: string[], perms: (PermissionCode | string)[]): boolean {
  return perms.some((p) => permissions.includes(p))
}

export function hasAllPermissions(permissions: string[], perms: (PermissionCode | string)[]): boolean {
  return perms.every((p) => permissions.includes(p))
}

export const RESOURCE_PERMISSIONS: Record<string, PermissionCode[]> = {
  product: ['product:view', 'product:create', 'product:edit', 'product:delete', 'product:import', 'product:export', 'product:status', 'product:clone'],
  category: ['category:view', 'category:create', 'category:edit', 'category:delete'],
  brand: ['brand:view', 'brand:create', 'brand:edit', 'brand:delete'],
  tag: ['tag:view', 'tag:create', 'tag:edit', 'tag:delete'],
  supplier: ['supplier:view', 'supplier:create', 'supplier:edit', 'supplier:delete'],
  user: ['user:view', 'user:create', 'user:edit', 'user:delete'],
  role: ['role:view', 'role:create', 'role:edit', 'role:delete', 'role:assign'],
  proposal: ['proposal:view', 'proposal:create', 'proposal:edit', 'proposal:delete'],
  quotation: ['quotation:view', 'quotation:create', 'quotation:edit', 'quotation:delete'],
  share: ['share:view', 'share:create', 'share:delete'],
  file: ['file:view', 'file:upload', 'file:delete'],
  stats: ['stats:view'],
  ai: ['ai:use'],
}
