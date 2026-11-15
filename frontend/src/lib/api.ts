// Code facts about the API: paths, shapes and constants. Prose about them lives in src/copy.

export const API_BASE = 'https://learning.deployedwork.com'
export const GITHUB_URL = 'https://github.com/dominicphillips/frontier-learning-api'
export const DEPLOYEDWORK_URL = 'https://deployedwork.com'
export const CATALOG_URL = 'https://deployedwork.com/learn'

// Server documents: the client router never intercepts these.
export const API_EXPLORER_PATH = '/docs/api'
export const OPENAPI_PATH = '/openapi.json'
export const HEALTH_PATH = '/health'
export const READY_PATH = '/health/ready'

export const PROVIDERS_PATH = '/v1/providers'
export const CATEGORIES_PATH = '/v1/categories'
export const STATUS_PATH = '/v1/status'
export const RESOURCES_PATH = '/v1/resources'

export const LIST_LIMIT_DEFAULT = 20
export const LIST_LIMIT_MAX = 100
export const LIMIT_OPTIONS = [10, 20, 50, 100] as const

// Mirrors src/frontier_learning/catalog.py and the per-provider Kind enums in schema/openapi.json.
export const PROVIDER_IDS = ['openai', 'claude', 'gemini'] as const
export type ProviderId = (typeof PROVIDER_IDS)[number]

export interface ProviderFacts {
  label: string
  sourceUrl: string
  prefix: string
  kinds: readonly string[]
}

export const PROVIDERS: Record<ProviderId, ProviderFacts> = {
  openai: {
    label: 'OpenAI Academy',
    sourceUrl: 'https://academy.openai.com',
    prefix: 'oa_',
    kinds: ['course', 'learning-path', 'article', 'video', 'event', 'collection', 'external'],
  },
  claude: {
    label: 'Claude Academy',
    sourceUrl: 'https://academy.claude.com',
    prefix: 'ca_',
    kinds: ['course', 'collection', 'tutorial', 'use-case'],
  },
  gemini: {
    label: 'Google Skills',
    sourceUrl: 'https://www.skills.google',
    prefix: 'ga_',
    kinds: ['course', 'learning-path', 'lab'],
  },
}

export const AGGREGATE_KINDS = [
  'course',
  'learning-path',
  'article',
  'video',
  'event',
  'collection',
  'external',
  'tutorial',
  'use-case',
  'lab',
] as const

export const AUDIENCES = [
  'general',
  'knowledge-workers',
  'developers',
  'leaders',
  'educators',
  'students',
  'admins',
  'other',
] as const

/** Route family: the aggregate /v1/* routes, or one provider's /v1/providers/{provider}/* routes. */
export type Scope = 'all' | ProviderId
export const SCOPES: readonly Scope[] = ['all', ...PROVIDER_IDS]

export function isProviderId(value: unknown): value is ProviderId {
  return typeof value === 'string' && (PROVIDER_IDS as readonly string[]).includes(value)
}

export function parseScope(value: string | null): Scope {
  return isProviderId(value) ? value : 'all'
}

export function kindsFor(scope: Scope): readonly string[] {
  return scope === 'all' ? AGGREGATE_KINDS : PROVIDERS[scope].kinds
}

const RESOURCE_ID = /^(oa|ca|ga)_[a-f0-9]{24}$/

// The ID prefix names the provider (oa_, ca_, ga_); anything else is not a valid resource ID.
export function providerForId(id: string): ProviderId | null {
  if (!RESOURCE_ID.test(id)) return null
  return PROVIDER_IDS.find((provider) => id.startsWith(PROVIDERS[provider].prefix)) ?? null
}

function scopeRoot(scope: Scope): string {
  return scope === 'all' ? '/v1' : `/v1/providers/${scope}`
}

export type ListParams = {
  provider?: string
  q?: string
  category?: string
  kind?: string
  audience?: string
  cursor?: string
  limit?: number
}

type QueryValue = string | number | null | undefined

export function queryString(params: Record<string, QueryValue>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ''
}

export function resourcesTemplate(scope: Scope): string {
  return `${scopeRoot(scope)}/resources`
}

export function resourceTemplate(scope: Scope): string {
  return `${scopeRoot(scope)}/resources/{id}`
}

export function categoriesTemplate(scope: Scope): string {
  return `${scopeRoot(scope)}/categories`
}

export function statusTemplate(scope: Scope): string {
  return `${scopeRoot(scope)}/status`
}

export function listResourcesPath(scope: Scope, params: ListParams = {}): string {
  return `${resourcesTemplate(scope)}${queryString(params)}`
}

export function resourcePath(id: string, scope: Scope = 'all'): string {
  return `${resourcesTemplate(scope)}/${encodeURIComponent(id)}`
}

/** The provider filter exists on the aggregate route only. */
export function categoriesPath(scope: Scope, provider: ProviderId | '' = ''): string {
  return `${categoriesTemplate(scope)}${scope === 'all' ? queryString({ provider }) : ''}`
}

export function statusPath(scope: Scope): string {
  return statusTemplate(scope)
}

export function curlFor(path: string): string {
  return `curl "${API_BASE}${path}"`
}

export interface RequestResult {
  path: string
  status: number
  statusText: string
  ok: boolean
  ms: number
  contentType: string | null
  text: string
  json: unknown
  isJson: boolean
}

// Same-origin request with a root-relative path. The Vite dev server proxies these to the API.
export async function apiRequest(path: string, signal?: AbortSignal): Promise<RequestResult> {
  const started = performance.now()
  const response = await fetch(path, { signal, headers: { Accept: 'application/json' } })
  const text = await response.text()
  const ms = Math.round(performance.now() - started)
  let json: unknown
  let isJson = false
  if (text) {
    try {
      json = JSON.parse(text)
      isJson = true
    } catch {
      isJson = false
    }
  }
  return {
    path,
    status: response.status,
    statusText: response.statusText,
    ok: response.ok,
    ms,
    contentType: response.headers.get('content-type'),
    text,
    json,
    isJson,
  }
}

export interface ResourceDuration {
  courseMinutes: number | null
  pathMinutes: number | null
  videoSeconds: number | null
}

export interface ResourceDetail {
  audience: string | null
  prerequisites: string[]
  objectives: string[]
  sections: unknown[]
}

export interface Provenance {
  sourceUrls: string[]
  fetchedAt: string | null
  contentHash: string | null
  method: string | null
}

export interface Resource {
  id: string
  /** Present on aggregate /v1/* records only. */
  provider: string | null
  title: string
  url: string
  kind: string
  categoryIds: string[]
  audiences: string[]
  tags: string[]
  summary: string | null
  level: string | null
  duration: ResourceDuration
  detail: ResourceDetail
  provenance: Provenance
}

export interface ResourceList {
  items: Resource[]
  nextCursor: string | null
  total: number | null
  snapshotId: string | null
}

export interface Category {
  /** provider:slug on aggregate routes, the plain slug on provider routes. */
  id: string
  provider: string | null
  label: string
  count: number | null
}

export interface CategoryList {
  items: Category[]
  snapshotId: string | null
}

// Tolerant readers so an unexpected payload degrades to the raw JSON view instead of a crash.
export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function stringOrNull(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

export function numberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

export function toResource(value: unknown): Resource | null {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.title !== 'string') return null
  const duration = isRecord(value.duration) ? value.duration : {}
  const detail = isRecord(value.detail) ? value.detail : {}
  const provenance = isRecord(value.provenance) ? value.provenance : {}
  return {
    id: value.id,
    provider: stringOrNull(value.provider),
    title: value.title,
    url: stringOrNull(value.url) ?? '',
    kind: stringOrNull(value.kind) ?? '',
    categoryIds: stringArray(value.categoryIds),
    audiences: stringArray(value.audiences),
    tags: stringArray(value.tags),
    summary: stringOrNull(value.summary),
    level: stringOrNull(value.level),
    duration: {
      courseMinutes: numberOrNull(duration.courseMinutes),
      pathMinutes: numberOrNull(duration.pathMinutes),
      videoSeconds: numberOrNull(duration.videoSeconds),
    },
    detail: {
      audience: stringOrNull(detail.audience),
      prerequisites: stringArray(detail.prerequisites),
      objectives: stringArray(detail.objectives),
      sections: Array.isArray(detail.sections) ? detail.sections : [],
    },
    provenance: {
      sourceUrls: stringArray(provenance.sourceUrls),
      fetchedAt: stringOrNull(provenance.fetchedAt),
      contentHash: stringOrNull(provenance.contentHash),
      method: stringOrNull(provenance.method),
    },
  }
}

export function toResourceList(value: unknown): ResourceList | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null
  const items = value.items.map(toResource).filter((item): item is Resource => item !== null)
  return {
    items,
    nextCursor: stringOrNull(value.nextCursor),
    total: numberOrNull(value.total),
    snapshotId: stringOrNull(value.snapshotId),
  }
}

export function toCategoryList(value: unknown): CategoryList | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null
  const items: Category[] = []
  for (const item of value.items) {
    if (!isRecord(item) || typeof item.id !== 'string') continue
    items.push({
      id: item.id,
      provider: stringOrNull(item.provider),
      label: stringOrNull(item.label) ?? item.id,
      count: numberOrNull(item.count),
    })
  }
  return { items, snapshotId: stringOrNull(value.snapshotId) }
}

// A section entry may be a plain string or an object with a title; anything else has no label.
export function sectionLabel(section: unknown): string | null {
  if (typeof section === 'string') return section
  if (isRecord(section) && typeof section.title === 'string') return section.title
  return null
}
