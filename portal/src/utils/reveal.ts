/**
 * 滚动揭示指令 `v-reveal`（对应 reeoo 首页向下滚动时分区淡入的效果）。
 *
 * 零依赖实现：一个共享的 IntersectionObserver，元素进入视口后加上
 * `is-revealed` 就不再观察。以下两种情况直接显示，不做动效：
 * 1. 用户开启了 prefers-reduced-motion；
 * 2. 环境没有 IntersectionObserver（避免内容永远停在 opacity: 0）。
 */
import type { Directive } from 'vue'

const PENDING_CLASS = 'reveal'
const DONE_CLASS = 'is-revealed'

let observer: IntersectionObserver | null = null

function sharedObserver(): IntersectionObserver {
  if (!observer) {
    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue
          entry.target.classList.add(DONE_CLASS)
          observer?.unobserve(entry.target)
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.04 },
    )
  }
  return observer
}

function prefersReducedMotion(): boolean {
  return Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
}

export const vReveal: Directive<HTMLElement> = {
  mounted(el) {
    if (prefersReducedMotion() || typeof IntersectionObserver === 'undefined') {
      el.classList.add(DONE_CLASS)
      return
    }
    el.classList.add(PENDING_CLASS)
    sharedObserver().observe(el)
  },
  unmounted(el) {
    observer?.unobserve(el)
  },
}
