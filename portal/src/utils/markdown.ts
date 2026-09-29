/**
 * Markdown → HTML 渲染。
 *
 * 为什么自己写而不引 marked/markdown-it：
 * 门户只需要标题、粗斜体、列表、表格、引用、分隔线、链接、行内代码和
 * 代码块这几类语法，而答案文本是 AI 生成的**不可信内容**。自渲染可以把
 * 「先转义、再用白名单标签输出」的控制权握在手里——所有输入文本在进入
 * 输出前都经过 escapeHtml，最终 HTML 里出现的标签全部由本文件生成，
 * 外部 HTML/脚本没有注入面。
 *
 * 引用角标：utils/citations 会把 `[chunk:uuid]` 折叠成 `\uE000<序号>\uE001`
 * 私有区占位符，这里在行内解析阶段还原成 `<button class="citation">`，
 * 点击后由 AnswerBody 统一派发给来源弹层。
 */

export type CitationInfo = {
  index: number
  sourceId: string | null
  token: string
}

/* ===== 行内节点 ===== */
type Inline =
  | { type: 'text'; value: string }
  | { type: 'code'; value: string }
  | { type: 'strong' | 'em' | 'del'; children: Inline[] }
  | { type: 'link'; href: string; children: Inline[] }
  | { type: 'citation'; index: number }
  /** 段内软换行 */
  | { type: 'br' }

/* ===== 块级节点 ===== */
type Align = 'left' | 'center' | 'right'
type Block =
  | { type: 'heading'; level: number; children: Inline[] }
  | { type: 'paragraph'; children: Inline[] }
  | { type: 'code'; lang: string; text: string }
  | { type: 'quote'; children: Block[] }
  | { type: 'list'; ordered: boolean; start: number; items: Block[][] }
  | { type: 'table'; headers: Inline[][]; aligns: Align[]; rows: Inline[][][] }
  | { type: 'hr' }

const CITATION_OPEN = '\uE000'
const CITATION_CLOSE = '\uE001'

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** 链接协议白名单：拒绝 javascript: / data: / vbscript: 等。 */
const LINK_PROTOCOLS = ['http:', 'https:', 'mailto:', 'tel:']
function safeHref(raw: string): string | null {
  let href = raw.trim()
  if (!href) return null
  if (href.startsWith('<') && href.endsWith('>')) href = href.slice(1, -1).trim()
  const scheme = /^([a-z][a-z0-9+.\-]*):/i.exec(href)
  if (scheme) return LINK_PROTOCOLS.includes(`${scheme[1].toLowerCase()}:`) ? href : null
  if (/^javascript:/i.test(href)) return null
  return href
}

/* ===== 行内解析 ===== */
function parseInline(src: string): Inline[] {
  const out: Inline[] = []
  let buf = ''
  let pos = 0
  const flush = () => {
    if (buf) {
      out.push({ type: 'text', value: buf })
      buf = ''
    }
  }

  while (pos < src.length) {
    const rest = src.slice(pos)
    const ch = rest[0]

    // 引用角标占位符
    if (ch === CITATION_OPEN) {
      const end = rest.indexOf(CITATION_CLOSE)
      if (end > 0) {
        const index = Number(rest.slice(1, end))
        if (Number.isInteger(index) && index > 0) {
          flush()
          out.push({ type: 'citation', index })
          pos += end + 1
          continue
        }
      }
    }

    // 行内代码（支持 1~3 个反引号）
    if (ch === '`') {
      let run = 1
      while (rest[run] === '`') run += 1
      const fence = '`'.repeat(run)
      let from = run
      let close = -1
      while (from < rest.length) {
        const idx = rest.indexOf(fence, from)
        if (idx < 0) break
        let after = idx + run
        while (rest[after] === '`') after += 1
        if (after - idx === run) {
          close = idx
          break
        }
        from = after
      }
      if (close > run - 1) {
        // CommonMark：代码两端各有一个空格时剥掉
        const code = rest.slice(run, close).replace(/^ (.*) $/, '$1')
        flush()
        out.push({ type: 'code', value: code })
        pos += close + run
        continue
      }
      buf += fence
      pos += run
      continue
    }

    // 粗体
    let m = /^(\*\*|__)(?=\S)([\s\S]*?\S)\1/.exec(rest)
    if (m) {
      flush()
      out.push({ type: 'strong', children: parseInline(m[2]) })
      pos += m[0].length
      continue
    }

    // 删除线
    m = /^~~(?=\S)([\s\S]*?\S)~~/.exec(rest)
    if (m) {
      flush()
      out.push({ type: 'del', children: parseInline(m[2]) })
      pos += m[0].length
      continue
    }

    // 斜体（`_` 不做词内匹配，避免 snake_case 被吃掉）
    m = /^\*(?=\S)([\s\S]*?\S)\*/.exec(rest)
    if (m) {
      flush()
      out.push({ type: 'em', children: parseInline(m[1]) })
      pos += m[0].length
      continue
    }
    m = /^_(?=\S)([\s\S]*?\S)_/.exec(rest)
    if (m && !/[\w\u4e00-\u9fa5]/.test(buf.slice(-1))) {
      flush()
      out.push({ type: 'em', children: parseInline(m[1]) })
      pos += m[0].length
      continue
    }

    // 链接 / 图片
    m = /^(!?)\[([^\]\n]*)\]\(\s*(<[^>\n]*>|[^\s)]*?)(?:\s+"([^"]*)")?\s*\)/.exec(rest)
    if (m) {
      const isImage = m[1] === '!'
      const href = safeHref(m[3])
      if (isImage) {
        // 答案里的图片地址不可信也不稳定，退化成图片说明文字，不发起请求。
        flush()
        if (m[2]) out.push({ type: 'text', value: m[2] })
        pos += m[0].length
        continue
      }
      if (href) {
        flush()
        out.push({ type: 'link', href, children: parseInline(m[2]) })
        pos += m[0].length
        continue
      }
    }

    buf += ch
    pos += 1
  }
  flush()
  return out
}

/* ===== 块级解析 ===== */
const HEADING_RE = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/
const FENCE_RE = /^\s{0,3}(`{3,}|~{3,})\s*([^\s`]*)\s*$/
const QUOTE_RE = /^\s{0,3}>/
const ITEM_RE = /^(\s*)(?:([-*+])|(\d{1,9})[.)])\s+(.*)$/
const TABLE_DELIM_RE = /^\s{0,3}\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/

/** 分隔线：`---` / `***` / `___`（允许字符中间夹空格），且要整行都是它。 */
function isHr(line: string): boolean {
  if (!line.trim()) return false
  const stripped = line.trim().replace(/\s+/g, '')
  return /^([-*_])\1{2,}$/.test(stripped)
}

function listMarker(line: string): { indent: number; ordered: boolean; start: number; contentStart: number } | null {
  const m = ITEM_RE.exec(line)
  if (!m) return null
  const indent = m[1].replace(/\t/g, '  ').length
  const ordered = Boolean(m[3])
  return {
    indent,
    ordered,
    start: ordered ? Number(m[3]) : 1,
    contentStart: m[0].length - m[4].length,
  }
}

/** 表格：当前行含 `|`，下一行是分隔行。 */
function tableAt(lines: string[], index: number): boolean {
  if (!lines[index].includes('|')) return false
  const next = lines[index + 1]
  if (!next || !next.includes('-')) return false
  return TABLE_DELIM_RE.test(next) && next.includes('|') === lines[index].includes('|')
}

function splitRow(line: string): string[] {
  let text = line.trim()
  if (text.startsWith('|')) text = text.slice(1)
  if (text.endsWith('|') && !text.endsWith('\\|')) text = text.slice(0, -1)
  return text.split(/(?<!\\)\|/).map((cell) => cell.replace(/\\\|/g, '|').trim())
}

function alignsOf(delim: string[]): Align[] {
  return delim.map((cell) => {
    const text = cell.trim()
    if (text.startsWith(':') && text.endsWith(':')) return 'center'
    if (text.endsWith(':')) return 'right'
    return 'left'
  })
}

/** 判断一行是否是某个新块的开始（用于终止段落与列表）。 */
function startsBlock(line: string, next: string | undefined): boolean {
  if (!line.trim()) return true
  if (isHr(line) || HEADING_RE.test(line) || FENCE_RE.test(line) || QUOTE_RE.test(line)) return true
  if (listMarker(line)) return true
  if (next && tableAt([line, next], 0)) return true
  return false
}

/** 段落的多行文本：行与行之间插入 <br>。 */
function joinLines(lines: string[]): Inline[] {
  const nodes: Inline[] = []
  lines.forEach((row, index) => {
    if (index > 0) nodes.push({ type: 'br' })
    nodes.push(...parseInline(row))
  })
  return nodes
}

function parseBlocks(lines: string[]): Block[] {
  const blocks: Block[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i += 1
      continue
    }

    // 代码块
    const fence = FENCE_RE.exec(line)
    if (fence) {
      const marker = fence[1]
      const lang = fence[2] || ''
      const body: string[] = []
      i += 1
      while (i < lines.length && !new RegExp(`^\\s{0,3}${marker[0] === '`' ? '`' : '~'}{${marker.length},}\\s*$`).test(lines[i])) {
        body.push(lines[i])
        i += 1
      }
      if (i < lines.length) i += 1 // 吃掉收尾 fence
      blocks.push({ type: 'code', lang, text: body.join('\n') })
      continue
    }

    if (isHr(line)) {
      blocks.push({ type: 'hr' })
      i += 1
      continue
    }

    const heading = HEADING_RE.exec(line)
    if (heading) {
      blocks.push({ type: 'heading', level: heading[1].length, children: parseInline(heading[2]) })
      i += 1
      continue
    }

    if (QUOTE_RE.test(line)) {
      const body: string[] = []
      while (i < lines.length && QUOTE_RE.test(lines[i])) {
        body.push(lines[i].replace(/^\s{0,3}>\s?/, ''))
        i += 1
      }
      blocks.push({ type: 'quote', children: parseBlocks(body) })
      continue
    }

    if (tableAt(lines, i)) {
      const headers = splitRow(lines[i]).map((cell) => parseInline(cell))
      const aligns = alignsOf(splitRow(lines[i + 1]))
      i += 2
      const rows: Inline[][][] = []
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        rows.push(splitRow(lines[i]).map((cell) => parseInline(cell)))
        i += 1
      }
      blocks.push({ type: 'table', headers, aligns, rows })
      continue
    }

    if (listMarker(line)) {
      const first = listMarker(line)!
      const ordered = first.ordered
      const start = first.start
      const baseIndent = first.indent
      const items: string[][] = []
      let current: string[] | null = null
      while (i < lines.length) {
        const row = lines[i]
        if (!row.trim()) {
          // 空行：只有下一行还是列表内容时才吞掉，否则列表结束
          const next = lines[i + 1]
          const nextIsItem = next ? listMarker(next) : null
          if (next && (nextIsItem || /^\s{2,}\S/.test(next))) {
            current?.push('')
            i += 1
            continue
          }
          break
        }
        const marker = listMarker(row)
        if (marker && marker.ordered === ordered && Math.abs(marker.indent - baseIndent) <= 3) {
          current = []
          items.push(current)
          current.push(row.slice(marker.contentStart))
          i += 1
          continue
        }
        if (current && /^\s+/.test(row)) {
          current.push(row.replace(/^\s{0,4}/, ''))
          i += 1
          continue
        }
        break
      }
      blocks.push({ type: 'list', ordered, start, items: items.map((item) => parseBlocks(item)) })
      continue
    }

    // 段落：单换行保留为 <br>，LLM 输出里的 \n 基本就是断行，合并成一段反而难读
    const body: string[] = []
    while (i < lines.length && lines[i].trim() && !startsBlock(lines[i], lines[i + 1])) {
      body.push(lines[i])
      i += 1
    }
    if (!body.length) {
      body.push(lines[i])
      i += 1
    }
    blocks.push({ type: 'paragraph', children: joinLines(body) })
  }

  return blocks
}

/* ===== 渲染 ===== */
function renderInlineList(nodes: Inline[], citations: Map<number, CitationInfo>): string {
  return nodes
    .map((node) => {
      switch (node.type) {
        case 'text':
          return escapeHtml(node.value)
        case 'br':
          return '<br />'
        case 'code':
          return `<code class="md-code-inline">${escapeHtml(node.value)}</code>`
        case 'strong':
          return `<strong>${renderInlineList(node.children, citations)}</strong>`
        case 'em':
          return `<em>${renderInlineList(node.children, citations)}</em>`
        case 'del':
          return `<del>${renderInlineList(node.children, citations)}</del>`
        case 'link':
          return `<a class="md-link" href="${escapeHtml(node.href)}" target="_blank" rel="noopener noreferrer nofollow">${renderInlineList(node.children, citations)}</a>`
        case 'citation': {
          const info = citations.get(node.index)
          const label = String(node.index)
          if (info?.sourceId) {
            return `<button type="button" class="citation" data-source="${escapeHtml(info.sourceId)}" aria-label="查看第 ${label} 条引用来源">${label}</button>`
          }
          const token = info?.token ? `引用标记 ${info.token} 未匹配到来源` : '引用标记未匹配到来源'
          return `<span class="citation citation--unresolved" title="${escapeHtml(token)}">${label}</span>`
        }
        default:
          return ''
      }
    })
    .join('')
}

function renderBlocks(blocks: Block[], citations: Map<number, CitationInfo>): string {
  const html: string[] = []
  for (const block of blocks) {
    switch (block.type) {
      case 'heading': {
        const level = Math.min(Math.max(block.level, 1), 6)
        html.push(`<h${level} class="md-h md-h${level}">${renderInlineList(block.children, citations)}</h${level}>`)
        break
      }
      case 'paragraph':
        html.push(`<p class="md-p">${renderInlineList(block.children, citations)}</p>`)
        break
      case 'code':
        html.push(
          `<pre class="md-pre"><code class="md-code"${block.lang ? ` data-lang="${escapeHtml(block.lang)}"` : ''}>${escapeHtml(block.text)}</code></pre>`,
        )
        break
      case 'quote':
        html.push(`<blockquote class="md-quote">${renderBlocks(block.children, citations)}</blockquote>`)
        break
      case 'list': {
        const tag = block.ordered ? 'ol' : 'ul'
        const startAttr = block.ordered && block.start !== 1 ? ` start="${block.start}"` : ''
        const items = block.items
          .map((item) => `<li class="md-li">${renderBlocks(item, citations)}</li>`)
          .join('')
        html.push(`<${tag} class="md-list"${startAttr}>${items}</${tag}>`)
        break
      }
      case 'table': {
        const th = block.headers
          .map((cell, index) => `<th class="md-th"${block.aligns[index] && block.aligns[index] !== 'left' ? ` data-align="${block.aligns[index]}"` : ''}>${renderInlineList(cell, citations)}</th>`)
          .join('')
        const rows = block.rows
          .map((row) => {
            const cells = row
              .map((cell, index) => {
                const align = block.aligns[index]
                const attr = align && align !== 'left' ? ` data-align="${align}"` : ''
                return `<td class="md-td"${attr}>${renderInlineList(cell, citations)}</td>`
              })
              .join('')
            return `<tr class="md-tr">${cells}</tr>`
          })
          .join('')
        html.push(
          `<div class="md-table-scroll"><table class="md-table"><thead class="md-thead"><tr class="md-tr">${th}</tr></thead><tbody class="md-tbody">${rows}</tbody></table></div>`,
        )
        break
      }
      case 'hr':
        html.push('<hr class="md-hr" />')
        break
      default:
        break
    }
  }
  return html.join('')
}

/** 把带引用占位符的 Markdown 源文本渲染成安全的 HTML。 */
export function renderMarkdown(source: string, citations: CitationInfo[] = []): string {
  if (!source || !source.trim()) return ''
  const map = new Map<number, CitationInfo>()
  for (const info of citations) {
    if (Number.isInteger(info.index) && info.index > 0 && !map.has(info.index)) map.set(info.index, info)
  }
  const normalized = source.replace(/\r\n?/g, '\n')
  return renderBlocks(parseBlocks(normalized.split('\n')), map)
}
