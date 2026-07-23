import { describe, expect, it } from 'vitest'
import { compareBuilds } from '@/config/version'

describe('version consistency', () => {
  it('prioritizes matching build IDs', () => {
    expect(compareBuilds(
      { version: '1.0.0', buildId: 'build-1', gitCommit: 'aaa' },
      { backend_version: '2.0.0', build_id: 'build-1', git_commit: 'bbb' },
    )).toBe('match')
  })

  it('reports differing build IDs', () => {
    expect(compareBuilds(
      { version: '1.0.0', buildId: 'build-1' },
      { backend_version: '1.0.0', build_id: 'build-2' },
    )).toBe('mismatch')
  })

  it('falls back to version and does not treat development metadata as known', () => {
    expect(compareBuilds(
      { version: '1.0.0', buildId: 'dev-local', gitCommit: 'unknown' },
      { backend_version: '1.0.0', build_id: 'dev-local', git_commit: 'unknown' },
    )).toBe('match')
    expect(compareBuilds(
      { version: 'dev', buildId: 'dev-local', gitCommit: 'unknown' },
      { backend_version: 'dev', build_id: 'dev-local', git_commit: 'unknown' },
    )).toBe('unknown')
  })
})
