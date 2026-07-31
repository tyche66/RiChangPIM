import http from 'node:http'
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const portalRootDir = path.resolve(process.env.PIM_DEMO_PORTAL_ROOT || path.join(__dirname, '..', 'portal', 'dist'))
const adminRootDir = path.resolve(process.env.PIM_DEMO_ADMIN_ROOT || path.join(__dirname, '..', 'frontend', 'dist'))
const listenHost = process.env.PIM_DEMO_HOST || '0.0.0.0'
const listenPort = Number(process.env.PIM_DEMO_PORT || 5173)
const backendTarget = new URL(process.env.PIM_DEMO_BACKEND || 'http://127.0.0.1:8000')
const demoHealthPath = '/__demo/health'

const mimeTypes = new Map([
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'application/javascript; charset=utf-8'],
  ['.mjs', 'application/javascript; charset=utf-8'],
  ['.css', 'text/css; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.svg', 'image/svg+xml'],
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.gif', 'image/gif'],
  ['.webp', 'image/webp'],
  ['.ico', 'image/x-icon'],
  ['.woff', 'font/woff'],
  ['.woff2', 'font/woff2'],
])

function contentTypeFor(filePath) {
  return mimeTypes.get(path.extname(filePath).toLowerCase()) || 'application/octet-stream'
}

function send(res, status, headers, body) {
  res.writeHead(status, headers)
  res.end(body)
}

function sendJson(res, status, payload) {
  send(res, status, { 'content-type': 'application/json; charset=utf-8' }, JSON.stringify(payload))
}

function safeResolve(urlPath, baseDir) {
  const decoded = decodeURIComponent(urlPath.split('?')[0] || '/')
  const relative = decoded.replace(/^\/+/, '')
  const resolved = path.resolve(baseDir, relative)
  if (!resolved.startsWith(baseDir)) return null
  return resolved
}

function proxyToBackend(req, res) {
  const upstream = new URL(req.url || '/', backendTarget)
  const headers = { ...req.headers }
  headers.host = backendTarget.host
  headers['x-forwarded-host'] = req.headers.host || ''
  headers['x-forwarded-proto'] = 'https'
  headers['x-forwarded-for'] = req.socket.remoteAddress || ''

  const proxyReq = http.request(
    {
      protocol: upstream.protocol,
      hostname: upstream.hostname,
      port: upstream.port,
      method: req.method,
      path: `${upstream.pathname}${upstream.search}`,
      headers,
    },
    (proxyRes) => {
      const responseHeaders = { ...proxyRes.headers }
      if (responseHeaders.location) {
        responseHeaders.location = String(responseHeaders.location).replace(backendTarget.origin, '')
      }
      res.writeHead(proxyRes.statusCode || 502, responseHeaders)
      proxyRes.pipe(res)
    }
  )

  proxyReq.on('error', (error) => {
    send(res, 502, { 'content-type': 'application/json; charset=utf-8' }, JSON.stringify({ error: error.message }))
  })

  req.pipe(proxyReq)
}

function resolveExistingFile(urlPath, baseDir) {
  const resolvedPath = safeResolve(urlPath, baseDir)
  if (!resolvedPath || !existsSync(resolvedPath)) return null
  if (statSync(resolvedPath).isDirectory()) {
    const indexPath = path.join(resolvedPath, 'index.html')
    return existsSync(indexPath) ? indexPath : null
  }
  return resolvedPath
}

function cacheHeadersFor(filePath) {
  // dist 里带内容哈希的资源可以长缓存；index.html 必须每次回源，
  // 否则改完前端刷新还是旧壳子。
  if (/\/assets\/.+\.[0-9a-zA-Z_-]{8,}\.(js|css|woff2?|png|jpe?g|svg|webp)$/.test(filePath)) {
    return { 'cache-control': 'public, max-age=31536000, immutable' }
  }
  if (filePath.endsWith('.html')) {
    return { 'cache-control': 'no-cache' }
  }
  return { 'cache-control': 'public, max-age=3600' }
}

function serveFile(req, res, filePath) {
  const headers = { 'content-type': contentTypeFor(filePath), ...cacheHeadersFor(filePath) }
  try {
    headers['content-length'] = String(statSync(filePath).size)
  } catch {
    // 拿不到大小就退回 chunked，不值得为此 500。
  }
  res.writeHead(200, headers)
  if (req.method === 'HEAD') {
    res.end()
    return
  }
  createReadStream(filePath).pipe(res)
}

/**
 * 后台静态资源。
 *
 * 这里曾经在响应时改写 admin 包（把 /assets/ 前缀、history base 和
 * window.location.href="/login" 都替换成 /admin/…）。那是后台按 base '/' 构建
 * 时代的补丁：它只能救 5173 这一条链路，:888 的 nginx 依旧白屏，而且每个 .js
 * 请求都要 readFileSync 整包 + 4 次 replaceAll。
 * 现在 scripts/build_frontends.sh 用 VITE_BASE_PATH=/admin/ 构建后台，产物里
 * 本来就是 /admin/assets/，改写全部失效也不再需要——原样发即可（见启动时的
 * base 自检，构建方式回退时会打印告警）。
 */
function serveAdminStatic(req, res, urlPath) {
  const adminUrl = urlPath.replace(/^\/admin/, '') || '/'
  const filePath = resolveExistingFile(adminUrl, adminRootDir)

  if (filePath) {
    return serveFile(req, res, filePath)
  }

  const indexPath = path.join(adminRootDir, 'index.html')
  if (!existsSync(indexPath)) {
    return send(res, 404, { 'content-type': 'text/plain; charset=utf-8' }, 'admin index.html not found')
  }

  return serveFile(req, res, indexPath)
}

function serveSharedStatic(req, res, urlPath) {
  const portalFilePath = resolveExistingFile(urlPath, portalRootDir)
  if (portalFilePath) {
    return serveFile(req, res, portalFilePath)
  }

  const adminFilePath = resolveExistingFile(urlPath, adminRootDir)
  if (adminFilePath) {
    return serveFile(req, res, adminFilePath)
  }

  return send(res, 404, { 'content-type': 'text/plain; charset=utf-8' }, 'Not found')
}

function serveStatic(req, res, baseDir, fallback = 'index.html') {
  const requestPath = (req.url || '/').split('?')[0] || '/'
  const resolvedPath = safeResolve(requestPath, baseDir)
  if (!resolvedPath) {
    return send(res, 400, { 'content-type': 'text/plain; charset=utf-8' }, 'Bad request')
  }

  let filePath = resolvedPath
  if (existsSync(filePath) && statSync(filePath).isDirectory()) {
    filePath = path.join(filePath, 'index.html')
  }

  if (!existsSync(filePath)) {
    filePath = path.join(baseDir, fallback)
  }

  if (!existsSync(filePath)) {
    return send(res, 404, { 'content-type': 'text/plain; charset=utf-8' }, 'index.html not found')
  }

  serveFile(req, res, filePath)
}

/**
 * 启动自检：后台产物必须是按 base '/admin/' 构建的。
 * 这个 demo server 不再在响应里改写 admin 包，所以一旦有人用 `npm run build`
 * （没有 VITE_BASE_PATH）覆盖了 frontend/dist，/admin/ 会去请求 /assets/…，
 * 被门户接住 → 白屏。宁可启动时喊一声，也不要让人对着白屏猜。
 */
function checkAdminBase() {
  const indexPath = path.join(adminRootDir, 'index.html')
  if (!existsSync(indexPath)) {
    console.warn(`WARN: ${indexPath} 不存在，/admin/ 会 404。先跑 bash scripts/build_frontends.sh`)
    return
  }
  const html = readFileSync(indexPath, 'utf8')
  if (!html.includes('/admin/assets/')) {
    console.warn('WARN: frontend/dist 不是按 base /admin/ 构建的（index.html 里没有 /admin/assets/）。')
    console.warn('      /admin/ 会去请求 /assets/… 并被门户接住 → 白屏。')
    console.warn('      修法：bash scripts/build_frontends.sh（它会 export VITE_BASE_PATH=/admin/）')
  }
}

const server = http.createServer((req, res) => {
  const urlPath = req.url || '/'
  if (urlPath === demoHealthPath) {
    return sendJson(res, 200, {
      ok: true,
      portalRootDir,
      adminRootDir,
      backendTarget: backendTarget.origin,
    })
  }

  if (urlPath.startsWith('/api/') || urlPath === '/health/' || urlPath.startsWith('/health/') || urlPath === '/docs' || urlPath.startsWith('/docs/') || urlPath === '/openapi.json') {
    return proxyToBackend(req, res)
  }

  if (urlPath === '/admin') {
    // 不带尾斜杠时 301 到 /admin/，否则相对资源会解析到站点根（门户）上去。
    return send(res, 301, { location: '/admin/', 'content-type': 'text/plain; charset=utf-8' }, '')
  }

  if (urlPath.startsWith('/admin?') || urlPath.startsWith('/admin#')) {
    return send(res, 301, { location: `/admin/${urlPath.slice('/admin'.length)}`, 'content-type': 'text/plain; charset=utf-8' }, '')
  }

  if (urlPath.startsWith('/admin/')) {
    return serveAdminStatic(req, res, urlPath)
  }

  // /share/{token} 以及不带 token 的 /share 都由门户 SPA 承载
  // （portal/src/views/SharePage.vue）：serveStatic 找不到同名文件就回退到门户
  // index.html，交给门户路由匹配 /share/:token。
  // 这里写成显式分支而不是靠最后的兜底，是为了不依赖「token 里没有点号」这个假设
  // ——下面那条带扩展名的判断会把 a.b 形状的路径当静态文件去找。
  if (urlPath === '/share' || urlPath.startsWith('/share/') || urlPath.startsWith('/share?')) {
    return serveStatic(req, res, portalRootDir)
  }

  if (urlPath === '/favicon.ico') {
    return serveStatic({ ...req, url: '/RiChangPIM.png' }, res, adminRootDir)
  }

  if (urlPath.startsWith('/assets/') || /\.[a-zA-Z0-9]+$/.test(urlPath)) {
    return serveSharedStatic(req, res, urlPath)
  }

  return serveStatic(req, res, portalRootDir)
})

server.listen(listenPort, listenHost, () => {
  console.log(`PIM demo server listening on http://${listenHost}:${listenPort}`)
  console.log(`Serving portal ${portalRootDir}`)
  console.log(`Serving admin ${adminRootDir}`)
  console.log(`Proxying API to ${backendTarget.origin}`)
  checkAdminBase()
})
