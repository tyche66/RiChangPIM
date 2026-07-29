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

function serveFile(req, res, filePath) {
  res.writeHead(200, { 'content-type': contentTypeFor(filePath) })
  if (req.method === 'HEAD') {
    res.end()
    return
  }
  createReadStream(filePath).pipe(res)
}

function serveText(req, res, status, filePath, body) {
  res.writeHead(status, { 'content-type': contentTypeFor(filePath) })
  if (req.method === 'HEAD') {
    res.end()
    return
  }
  res.end(body)
}

function rewriteAdminHtml(html) {
  return html
    .replaceAll('href="/assets/', 'href="/admin/assets/')
    .replaceAll('src="/assets/', 'src="/admin/assets/')
    .replaceAll('href="/RiChangPIM.png"', 'href="/admin/RiChangPIM.png"')
}

function rewriteAdminJavaScript(source) {
  return source
    .replace('history:K("/")', 'history:K("/admin/")')
    .replaceAll('window.location.href="/login"', 'window.location.href="/admin/login"')
    .replaceAll('return"/"+e', 'return"/admin/"+e')
}

function serveAdminStatic(req, res, urlPath) {
  const adminUrl = urlPath.replace(/^\/admin/, '') || '/'
  const filePath = resolveExistingFile(adminUrl, adminRootDir)

  if (filePath) {
    if (filePath.endsWith('.html')) {
      const html = rewriteAdminHtml(readFileSync(filePath, 'utf8'))
      return serveText(req, res, 200, filePath, html)
    }

    if (filePath.endsWith('.js')) {
      const js = rewriteAdminJavaScript(readFileSync(filePath, 'utf8'))
      return serveText(req, res, 200, filePath, js)
    }

    return serveFile(req, res, filePath)
  }

  const indexPath = path.join(adminRootDir, 'index.html')
  if (!existsSync(indexPath)) {
    return send(res, 404, { 'content-type': 'text/plain; charset=utf-8' }, 'admin index.html not found')
  }

  const html = rewriteAdminHtml(readFileSync(indexPath, 'utf8'))
  return serveText(req, res, 200, indexPath, html)
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

  if (urlPath.startsWith('/admin/')) {
    return serveAdminStatic(req, res, urlPath)
  }

  if (urlPath.startsWith('/share/')) {
    return serveStatic({ ...req, url: '/' }, res, adminRootDir)
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
})
