// App routes derived from API identifiers. The documentation app owns /docs; /docs/api is the
// server's Swagger UI and always loads as its own document.
import { queryString, type Scope } from '@/lib/api'

export const DOCS_ROUTES = {
  overview: '/docs',
  resources: '/docs/resources',
  resource: '/docs/resource',
  categories: '/docs/categories',
  status: '/docs/status',
} as const

const scopeParam = (scope: Scope) => (scope === 'all' ? undefined : scope)

export function resourceRoute(id: string, scope: Scope = 'all'): string {
  return `${DOCS_ROUTES.resources}/${encodeURIComponent(id)}${queryString({ scope: scopeParam(scope) })}`
}

/** Category IDs are provider:slug on aggregate routes and plain slugs on provider routes. */
export function categoryRoute(id: string, scope: Scope = 'all'): string {
  return `${DOCS_ROUTES.resources}${queryString({ scope: scopeParam(scope), category: id })}`
}

export function scopedRoute(path: string, scope: Scope): string {
  return `${path}${queryString({ scope: scopeParam(scope) })}`
}

// Paths the client router renders; everything else (including /docs/api) is a full page load.
export function isAppPath(pathname: string): boolean {
  if (pathname === '/docs/api' || pathname.startsWith('/docs/api/')) return false
  return pathname === '/docs' || pathname.startsWith('/docs/')
}
