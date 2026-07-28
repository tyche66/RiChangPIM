import http from 'node:http'
import { createReadStream, existsSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const portalRootDir = path.resolve(process.env.PIM_DEMO_PORTAL_ROOT || path.join(__dirname, '..', 'portal', 'dist'))
const adminRootDir = path.resolve(process.env.PIM_DEMO_ADMIN_ROOT || path.join(__dirname, '..', 'frontend', 'dist'))
const listenHost = process.env.PIM_DEMO_HOST || '0.0.0.0'
const listenPort = Number(process.env.PIM_DEMO_PORT || 5173)
const backendTarget = new URL(process.env.PIM_DEMO_BACKEND || 'http://127.0.0.1:8000')

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

  res.writeHead(200, { 'content-type': contentTypeFor(filePath) })
  if (req.method === 'HEAD') {
    res.end()
    return
  }
  createReadStream(filePath).pipe(res)
}

const server = http.createServer((req, res) => {
  const urlPath = req.url || '/'
  if (urlPath.startsWith('/api/') || urlPath === '/health/' || urlPath.startsWith('/health/') || urlPath === '/docs' || urlPath.startsWith('/docs/') || urlPath === '/openapi.json') {
    return proxyToBackend(req, res)
  }

  if (urlPath.startsWith('/admin/')) {
    return serveStatic({ ...req, url: urlPath.replace(/^\/admin/, '') || '/' }, res, adminRootDir)
  }

  if (urlPath.startsWith('/share/')) {
    return serveStatic({ ...req, url: '/' }, res, adminRootDir)
  }

  if (urlPath === '/favicon.ico') {
    return serveStatic({ ...req, url: '/RiChangPIM.png' }, res, adminRootDir)
  }

  return serveStatic(req, res, portalRootDir)
})

server.listen(listenPort, listenHost, () => {
  console.log(`PIM demo server listening on http://${listenHost}:${listenPort}`)
  console.log(`Serving portal ${portalRootDir}`)
  console.log(`Serving admin ${adminRootDir}`)
  console.log(`Proxying API to ${backendTarget.origin}`)
})
