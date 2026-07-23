/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_VERSION?: string
  readonly VITE_BUILD_ID?: string
  readonly VITE_GIT_COMMIT?: string
  readonly VITE_BUILD_TIME?: string
  readonly VITE_PUBLIC_FRONTEND_URL?: string
}
