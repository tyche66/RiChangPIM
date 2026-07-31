import { defineConfig, devices } from '@playwright/test'

// 5173 是 vite 默认端口，本机很容易被别的服务占住（实测 scripts/pim-demo-server.mjs
// 就在 5173 上发着 portal 的构建产物）。而 reuseExistingServer 会静默复用那个服务：
// e2e 不会报「端口被占」，而是对着**错误的应用**跑，然后整套全红且失败原因看不出来。
// 留一个 E2E_PORT 逃生口，就能在不动占位进程的前提下换端口跑验收。
// --strictPort 必须带上：否则 vite 被占端口时会自己跳到下一个端口，
// 而 playwright 仍在等 url 上的那个端口，退化成一样的「对着错误应用跑」。
const E2E_PORT = Number(process.env.E2E_PORT || 5173)
const E2E_BASE_URL = `http://localhost:${E2E_PORT}`

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: E2E_BASE_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  webServer: {
    command: `npm run dev -- --port ${E2E_PORT} --strictPort`,
    url: E2E_BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
  ],
})
