import { useMemo, useSyncExternalStore } from 'react'
import { isAppPath } from '@/lib/routes'

// Minimal History API router: enough for a handful of documentation routes without a dependency.

const listeners = new Set<() => void>()

function subscribe(listener: () => void) {
  listeners.add(listener)
  window.addEventListener('popstate', listener)
  return () => {
    listeners.delete(listener)
    window.removeEventListener('popstate', listener)
  }
}

function snapshot(): string {
  return `${window.location.pathname}${window.location.search}`
}

// Moves focus to the new page (or the linked section) without animating the scroll.
function focusTarget(hash: string) {
  const id = hash ? decodeURIComponent(hash.slice(1)) : ''
  const target = (id && document.getElementById(id)) || document.getElementById('main')
  if (!target) return
  if (id && target.id === id) {
    if (!target.hasAttribute('tabindex')) target.setAttribute('tabindex', '-1')
    target.scrollIntoView({ block: 'start' })
  }
  target.focus({ preventScroll: true })
}

export function navigate(to: string, options: { replace?: boolean } = {}) {
  const url = new URL(to, window.location.origin)
  // Server documents (Swagger at /docs/api, JSON routes) load as full pages.
  if (url.origin !== window.location.origin || !isAppPath(url.pathname)) {
    window.location.assign(url.href)
    return
  }
  const next = `${url.pathname}${url.search}${url.hash}`
  if (`${url.pathname}${url.search}` === snapshot() && !url.hash) return
  window.history[options.replace ? 'replaceState' : 'pushState'](null, '', next)
  for (const listener of listeners) listener()
  if (!options.replace) {
    window.scrollTo(0, 0)
    requestAnimationFrame(() => focusTarget(url.hash))
  }
}

export interface Location {
  pathname: string
  search: URLSearchParams
}

export function useLocation(): Location {
  const href = useSyncExternalStore(subscribe, snapshot)
  return useMemo(() => {
    const url = new URL(href, window.location.origin)
    const pathname = url.pathname.length > 1 ? url.pathname.replace(/\/+$/, '') : url.pathname
    return { pathname, search: url.searchParams }
  }, [href])
}
