import { useEffect, useRef, useState } from 'react'
import { RotateCcwIcon } from 'lucide-react'
import { CodeBlock } from '@/components/code-block'
import { Definitions, PageHeader, Section } from '@/components/doc'
import { RequestPanel } from '@/components/request-panel'
import { ResourceRow } from '@/components/resource-row'
import { ProviderFilter, RouteSelect, fieldLabelClass } from '@/components/route-select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { copy, fmt } from '@/copy'
import { useRequest } from '@/hooks/use-request'
import {
  AUDIENCES,
  LIMIT_OPTIONS,
  LIST_LIMIT_DEFAULT,
  LIST_LIMIT_MAX,
  categoriesPath,
  curlFor,
  isProviderId,
  kindsFor,
  listResourcesPath,
  parseScope,
  queryString,
  resourcesTemplate,
  toCategoryList,
  toResourceList,
  type ListParams,
  type ProviderId,
  type Scope,
} from '@/lib/api'
import { LIST_SHAPE } from '@/lib/examples'
import { navigate } from '@/lib/router'
import { DOCS_ROUTES } from '@/lib/routes'

interface Filters {
  /** Route family: aggregate /v1/resources or /v1/providers/{provider}/resources. */
  scope: Scope
  /** Aggregate provider query parameter; always empty on a provider route. */
  provider: ProviderId | ''
  q: string
  category: string
  kind: string
  audience: string
  limit: number
}

const ANY_CATEGORY = '__any__'
const TEXT_FILTERS = ['q', 'category', 'kind', 'audience'] as const

const DEFAULTS = (scope: Scope): Filters => ({
  scope,
  provider: '',
  q: '',
  category: '',
  kind: '',
  audience: '',
  limit: LIST_LIMIT_DEFAULT,
})

function fromSearch(search: URLSearchParams): Filters {
  const scope = parseScope(search.get('scope'))
  const provider = search.get('provider')
  const limit = Number(search.get('limit'))
  return {
    scope,
    provider: scope === 'all' && isProviderId(provider) ? provider : '',
    q: search.get('q') ?? '',
    category: search.get('category') ?? '',
    kind: search.get('kind') ?? '',
    audience: search.get('audience') ?? '',
    limit: (LIMIT_OPTIONS as readonly number[]).includes(limit) ? limit : LIST_LIMIT_DEFAULT,
  }
}

function toParams(filters: Filters, cursor: string | null = null): ListParams {
  return {
    provider: filters.scope === 'all' ? filters.provider || undefined : undefined,
    q: filters.q.trim() || undefined,
    category: filters.category || undefined,
    kind: filters.kind.trim() || undefined,
    audience: filters.audience.trim() || undefined,
    limit: filters.limit,
    cursor: cursor ?? undefined,
  }
}

function hasFilters(filters: Filters): boolean {
  return filters.scope !== 'all' || filters.provider !== '' || TEXT_FILTERS.some((key) => filters[key].trim() !== '')
}

function isDefault(filters: Filters): boolean {
  return !hasFilters({ ...filters, scope: 'all' }) && filters.limit === LIST_LIMIT_DEFAULT
}

// Aggregate category IDs are provider:slug; provider routes take the plain slug. A category from
// another provider cannot match, so it is cleared rather than silently rewritten.
function convertCategory(category: string, from: Scope, to: Scope): string {
  if (!category || from === to) return category
  if (from === 'all') return to !== 'all' && category.startsWith(`${to}:`) ? category.slice(to.length + 1) : ''
  return to === 'all' ? `${from}:${category}` : ''
}

// The page URL mirrors the applied filters (without the cursor) so a filtered view can be shared.
function pageRoute(filters: Filters): string {
  const params = toParams(filters)
  return `${DOCS_ROUTES.resources}${queryString({
    scope: filters.scope === 'all' ? undefined : filters.scope,
    ...params,
    limit: filters.limit === LIST_LIMIT_DEFAULT ? undefined : filters.limit,
  })}`
}

export function ResourcesPage({ search }: { search: URLSearchParams }) {
  const list = useRequest()
  const { state: categoryState, run: loadCategories } = useRequest()
  const [form, setForm] = useState<Filters>(() => fromSearch(search))
  const [applied, setApplied] = useState<Filters | null>(null)
  const started = useRef(false)

  function execute(filters: Filters, cursor: string | null) {
    setApplied(filters)
    navigate(pageRoute(filters), { replace: true })
    list.run(listResourcesPath(filters.scope, toParams(filters, cursor)))
  }

  // Category options follow the selected route: provider routes list their own plain slugs.
  useEffect(() => {
    loadCategories(categoriesPath(form.scope))
  }, [form.scope, loadCategories])

  useEffect(() => {
    if (started.current) return
    started.current = true
    if (hasFilters(form)) execute(form, null)
    // Only on first mount: a filtered link (for example from a category) runs immediately.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function changeScope(scope: Scope) {
    setForm((current) => ({ ...current, scope, provider: '', category: convertCategory(current.category, current.scope, scope) }))
  }

  function changeProvider(provider: ProviderId | '') {
    setForm((current) => ({
      ...current,
      provider,
      category: provider && current.category && !current.category.startsWith(`${provider}:`) ? '' : current.category,
    }))
  }

  const loading = list.state.phase === 'loading'
  const result = list.state.phase === 'done' ? toResourceList(list.state.result.json) : null
  const categoryList = categoryState.phase === 'done' ? toCategoryList(categoryState.result.json) : null
  const categoriesUnavailable =
    categoryState.phase === 'failed' || (categoryState.phase === 'done' && (categoryList === null || !categoryState.result.ok))
  const categoryOptions = (categoryList?.items ?? []).filter(
    (category) => form.scope !== 'all' || !form.provider || category.provider === form.provider,
  )
  const selectedCategory = categoryOptions.find((category) => category.id === form.category)
  // The draft is what Run sends next; the response pane keeps describing its own completed request.
  const draftPath = listResourcesPath(form.scope, toParams(form))
  const resultScope = applied?.scope ?? form.scope

  return (
    <article className="space-y-10">
      <PageHeader title={copy.resources.title} lede={copy.resources.lede} />

      <Section wide title={copy.resources.tryHeading} lede={copy.resources.tryLede}>
        <RequestPanel path={draftPath} state={list.state} onRun={() => execute(form, null)}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <RouteSelect id="filter-route" value={form.scope} onChange={changeScope} template={resourcesTemplate} />
            </div>
            {form.scope === 'all' ? (
              <div className="sm:col-span-2">
                <ProviderFilter id="filter-provider" value={form.provider} onChange={changeProvider} />
              </div>
            ) : null}
            <div className="min-w-0 space-y-1.5 sm:col-span-2">
              <label htmlFor="filter-q" className={fieldLabelClass}>
                {copy.resources.filters.q}
              </label>
              <Input
                id="filter-q"
                type="search"
                autoComplete="off"
                value={form.q}
                onChange={(event) => setForm({ ...form, q: event.target.value })}
              />
            </div>
            <div className="min-w-0 space-y-1.5">
              <label htmlFor="filter-category" className={fieldLabelClass}>
                {copy.resources.filters.category}
              </label>
              <Select
                value={form.category || ANY_CATEGORY}
                onValueChange={(value) => setForm({ ...form, category: value === ANY_CATEGORY ? '' : value })}
              >
                <SelectTrigger
                  id="filter-category"
                  title={selectedCategory ? `${selectedCategory.label} (${selectedCategory.id})` : form.category || copy.resources.filters.categoryAny}
                  className="w-full"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ANY_CATEGORY}>{copy.resources.filters.categoryAny}</SelectItem>
                  {form.category && !selectedCategory ? (
                    <SelectItem value={form.category} className="font-mono text-[13px]">
                      {form.category}
                    </SelectItem>
                  ) : null}
                  {categoryOptions.map((category) => (
                    <SelectItem key={category.id} value={category.id}>
                      {category.label}
                      {category.provider ? (
                        <>
                          {' '}
                          <span className="font-mono text-[11px] text-muted-foreground">{category.provider}</span>
                        </>
                      ) : null}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {categoriesUnavailable ? (
                <p className="text-xs text-muted-foreground">{copy.resources.filters.categoryUnavailable}</p>
              ) : null}
            </div>
            <div className="min-w-0 space-y-1.5">
              <label htmlFor="filter-limit" className={fieldLabelClass}>
                {copy.resources.filters.limit}
              </label>
              <Select value={String(form.limit)} onValueChange={(value) => setForm({ ...form, limit: Number(value) })}>
                <SelectTrigger id="filter-limit" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LIMIT_OPTIONS.map((option) => (
                    <SelectItem key={option} value={String(option)}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="min-w-0 space-y-1.5">
              <label htmlFor="filter-kind" className={fieldLabelClass}>
                {copy.resources.filters.kind}
              </label>
              <Input
                id="filter-kind"
                list="filter-kind-options"
                autoComplete="off"
                spellCheck={false}
                value={form.kind}
                onChange={(event) => setForm({ ...form, kind: event.target.value })}
              />
              <datalist id="filter-kind-options">
                {kindsFor(form.scope).map((kind) => (
                  <option key={kind} value={kind} />
                ))}
              </datalist>
            </div>
            <div className="min-w-0 space-y-1.5">
              <label htmlFor="filter-audience" className={fieldLabelClass}>
                {copy.resources.filters.audience}
              </label>
              <Input
                id="filter-audience"
                list="filter-audience-options"
                autoComplete="off"
                spellCheck={false}
                value={form.audience}
                onChange={(event) => setForm({ ...form, audience: event.target.value })}
              />
              <datalist id="filter-audience-options">
                {AUDIENCES.map((audience) => (
                  <option key={audience} value={audience} />
                ))}
              </datalist>
            </div>
            {!isDefault(form) ? (
              <div className="flex min-w-0 sm:col-span-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  title={copy.actions.resetFilters}
                  className="max-w-full"
                  onClick={() => setForm(DEFAULTS(form.scope))}
                >
                  <RotateCcwIcon data-icon="inline-start" aria-hidden="true" />
                  <span className="truncate">{copy.actions.resetFilters}</span>
                </Button>
              </div>
            ) : null}
          </div>
        </RequestPanel>

        {loading ? (
          <div className="space-y-2" aria-hidden="true">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : null}

        {result ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{copy.resources.resultsHeading}</h3>
            <p className="text-sm text-muted-foreground">
              {result.total === null
                ? fmt(copy.resources.resultsCount, { count: result.items.length })
                : fmt(copy.resources.resultsSummary, { count: result.items.length, total: result.total })}
              {result.snapshotId ? (
                <>
                  {' · '}
                  {copy.resources.snapshotLabel} <code className="font-mono text-xs break-all">{result.snapshotId}</code>
                </>
              ) : null}
            </p>
            {result.items.length === 0 ? (
              <p className="text-sm">{copy.resources.empty}</p>
            ) : (
              <ul className="divide-y rounded-xl border bg-card">
                {result.items.map((resource) => (
                  <ResourceRow key={resource.id} resource={resource} scope={resultScope} />
                ))}
              </ul>
            )}
            {result.nextCursor && applied ? (
              <Button
                type="button"
                variant="outline"
                title={copy.actions.nextPage}
                className="max-w-full"
                onClick={() => execute(applied, result.nextCursor)}
              >
                <span className="truncate">{copy.actions.nextPage}</span>
              </Button>
            ) : null}
          </div>
        ) : null}
      </Section>

      <Section title={copy.resources.paramsHeading}>
        <Definitions
          rows={[
            { name: 'provider', type: 'string', note: copy.resources.params.provider },
            { name: 'q', type: 'string', note: copy.resources.params.q },
            { name: 'category', type: 'string', note: copy.resources.params.category },
            { name: 'kind', type: 'string', note: copy.resources.params.kind },
            { name: 'audience', type: 'string', note: copy.resources.params.audience },
            { name: 'cursor', type: 'string', note: copy.resources.params.cursor },
            {
              name: 'limit',
              type: 'integer',
              note: fmt(copy.resources.params.limit, { default: LIST_LIMIT_DEFAULT, max: LIST_LIMIT_MAX }),
            },
          ]}
        />
        <CodeBlock label={copy.labels.curl} language="bash" code={curlFor(listResourcesPath('all', { provider: 'claude', limit: 5 }))} />
      </Section>

      <Section title={copy.resources.responseHeading} lede={copy.resources.shapeNote}>
        <Definitions
          rows={[
            { name: 'items', type: 'Resource[]', note: copy.resources.response.items },
            { name: 'nextCursor', type: 'string | null', note: copy.resources.response.nextCursor },
            { name: 'total', type: 'number', note: copy.resources.response.total },
            { name: 'snapshotId', type: 'string', note: copy.resources.response.snapshotId },
          ]}
        />
        <CodeBlock label={copy.labels.shape} language="json" code={LIST_SHAPE} />
      </Section>

      <Section title={copy.resources.scoped.heading} lede={copy.resources.scoped.lede}>
        <Definitions
          rows={[
            { name: 'provider', note: copy.resources.scoped.provider },
            { name: 'categoryIds', type: 'string[]', note: copy.resources.scoped.categoryIds },
            { name: 'kind', type: 'string', note: copy.resources.scoped.kind },
            { name: 'cursor', type: 'string', note: copy.resources.scoped.cursor },
          ]}
        />
        <CodeBlock label={copy.labels.curl} language="bash" code={curlFor(listResourcesPath('gemini', { kind: 'lab', limit: 5 }))} />
      </Section>
    </article>
  )
}
