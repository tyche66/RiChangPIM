import packageInfo from '../../package.json'

const configuredVersion = import.meta.env.VITE_APP_VERSION

export const frontendBuild = {
  version: configuredVersion || packageInfo.version || 'dev',
  buildId: import.meta.env.VITE_BUILD_ID || 'dev-local',
  gitCommit: import.meta.env.VITE_GIT_COMMIT || 'unknown',
  buildTime: import.meta.env.VITE_BUILD_TIME || 'unknown',
}

export type VersionStatus = 'match' | 'mismatch' | 'unknown'

const missing = (value?: string) => !value || ['unknown', 'dev', 'dev-local'].includes(value.toLowerCase())

export function compareBuilds(
  frontend: { version?: string; buildId?: string; gitCommit?: string },
  backend: { backend_version?: string; build_id?: string; git_commit?: string },
): VersionStatus {
  if (!missing(frontend.buildId) && !missing(backend.build_id)) {
    return frontend.buildId === backend.build_id ? 'match' : 'mismatch'
  }
  if (!missing(frontend.gitCommit) && !missing(backend.git_commit)) {
    return frontend.gitCommit === backend.git_commit ? 'match' : 'mismatch'
  }
  if (!missing(frontend.version) && !missing(backend.backend_version)) {
    return frontend.version === backend.backend_version ? 'match' : 'mismatch'
  }
  return 'unknown'
}
