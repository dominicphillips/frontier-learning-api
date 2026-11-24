import { useEffect, useRef, useState } from 'react'
import { ExternalLinkIcon, RotateCcwIcon } from 'lucide-react'
import { CodeBlock } from '@/components/code-block'
import { Definitions, PageHeader, Section } from '@/components/doc'
import { Link } from '@/components/link'
import { RequestPanel } from '@/components/request-panel'
import { ProviderFilter, RouteSelect, fieldLabelClass } from '@/components/route-select'
import { Badge } from '@/components/ui/badge'
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
  curlFor,
  isProviderId,
  learningPathTemplate,
  learningPathsTemplate,
  listLearningPathsPath,
  parseScope,
  queryString,
  toLearningPathList,
  type LearningPath,
  type LearningPathListParams,
  type ProviderId,
  type Scope,
} from '@/lib/api'
import { durationEntries } from '@/lib/duration'
import { LEARNING_PATH_LIST_SHAPE } from '@/lib/examples'
import { safeHttpUrl } from '@/lib/format'
import { navigate } from '@/lib/router'
import { DOCS_ROUTES, resourceRoute } from '@/lib/routes'

interface Filters {
  scope: Scope
  provider: ProviderId | ''
  q: string
  contains: string
  audience: string
  limit: number
}

const DEFAULTS = (scope: Scope): Filters => ({
  scope,
  provider: '',
  q: '',
  contains: '',
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
    contains: search.get('contains') ?? '',
    audience: search.get('audience') ?? '',
    limit: (LIMIT_OPTIONS as readonly number[]).includes(limit) ? limit : LIST_LIMIT_DEFAULT,
  }
}

function toParams(filters: Filters, cursor: string | null = null): LearningPathListParams {
  return {
    provider: filters.scope === 'all' ? filters.provider || undefined : undefined,
    q: filters.q.trim() || undefined,
    contains: filters.contains.trim() || undefined,
    audience: filters.audience.trim() || undefined,
    limit: filters.limit,
    cursor: cursor ?? undefined,
  }
}

function hasFilters(filters: Filters): boolean {
  return (
    filters.scope !== 'all' ||
    filters.provider !== '' ||
    filters.q.trim() !== '' ||
    filters.contains.trim() !== '' ||
    filters.audience.trim() !== ''
  )
}

function isDefault(filters: Filters): boolean {
  return !hasFilters({ ...filters, scope: 'all' }) && filters.limit === LIST_LIMIT_DEFAULT
}

function pageRoute(filters: Filters): string {
  const params = toParams(filters)
  return `${DOCS_ROUTES.learningPaths}${queryString({
    scope: filters.scope === 'all' ? undefined : filters.scope,
    ...params,
    limit: filters.limit === LIST_LIMIT_DEFAULT ? undefined : filters.limit,
  })}`
}

function PathCard({ path, scope }: { path: LearningPath; scope: Scope }) {
  const lp = copy.learningPaths
  const durations = durationEntries(path.duration)
  const stepLabel = fmt(path.stepCount === 1 ? lp.stepCountOne : lp.stepCount, { count: path.stepCount })

  return (
    <li className="space-y-4 rounded-xl border bg-card p-4 sm:p-5">
      <div className="space-y-2">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Link to={resourceRoute(path.id, scope)} className="text-base font-semibold tracking-tight underline-offset-4 hover:underline [overflow-wrap:anywhere]">
            {path.title}
          </Link>
          <code className="font-mono text-xs text-muted-foreground">{path.id}</code>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {path.provider ? (
            <Badge variant="default" className="font-mono">
              {path.provider}
            </Badge>
          ) : null}
          <Badge variant="secondary">{stepLabel}</Badge>
          {path.level ? <Badge variant="outline">{path.level}</Badge> : null}
          {durations.map((entry) => (
            <Badge key={entry.key} variant="outline">
              {entry.value}
            </Badge>
          ))}
        </div>
        {path.summary ? <p className="text-sm leading-6 text-muted-foreground [overflow-wrap:anywhere]">{path.summary}</p> : null}
      </div>

      {path.steps.length > 0 ? (
        <ol className="space-y-2 border-l-2 border-border pl-4">
          {path.steps.map((step) => {
            const stepDurations = step.duration ? durationEntries(step.duration) : []
            const href = safeHttpUrl(step.url)
            return (
              <li key={`${step.position}-${step.url}`} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-sm">
                <div className="min-w-0 space-y-0.5">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <span className="font-mono text-xs tabular-nums text-muted-foreground">{step.position}.</span>
                    {step.resourceId ? (
                      <Link to={resourceRoute(step.resourceId, scope)} className="font-medium underline-offset-4 hover:underline [overflow-wrap:anywhere]">
                        {step.title}
                      </Link>
                    ) : href ? (
                      <a href={href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium underline-offset-4 hover:underline [overflow-wrap:anywhere]">
                        <span>{step.title}</span>
                        <ExternalLinkIcon className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
                      </a>
                    ) : (
                      <span className="font-medium [overflow-wrap:anywhere]">{step.title}</span>
                    )}
                  </div>
                  <p className="pl-5 text-xs text-muted-foreground">
                    {[
                      step.kind,
                      ...stepDurations.map((entry) => entry.value),
                      step.level,
                      step.resourceId ? null : lp.externalStep,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                </div>
                {step.resourceId ? <code className="font-mono text-xs text-muted-foreground">{step.resourceId}</code> : null}
              </li>
            )
          })}
        </ol>
      ) : null}
    </li>
  )
}

export function LearningPathsPage({ search }: { search: URLSearchParams }) {
  const list = useRequest()
  const [form, setForm] = useState<Filters>(() => fromSearch(search))
  const [applied, setApplied] = useState<Filters | null>(null)
  const started = useRef(false)
  const lp = copy.learningPaths

  function execute(filters: Filters, cursor: string | null) {
    setApplied(filters)
    navigate(pageRoute(filters), { replace: true })
    list.run(listLearningPathsPath(filters.scope, toParams(filters, cursor)))
  }

  useEffect(() => {
    if (started.current) return
    started.current = true
    if (hasFilters(form)) execute(form, null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loading = list.state.phase === 'loading'
  const result = list.state.phase === 'done' && list.state.result.ok ? toLearningPathList(list.state.result.json) : null
  const draftPath = listLearningPathsPath(form.scope, toParams(form))
  const resultScope = applied?.scope ?? form.scope

  return (
    <article className="space-y-10">
      <PageHeader title={lp.title} lede={lp.lede} />

      <Section wide title={lp.tryHeading} lede={lp.tryLede}>
        <RequestPanel path={draftPath} state={list.state} onRun={() => execute(form, null)}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <RouteSelect
                id="lp-route"
                value={form.scope}
                onChange={(scope) => setForm((current) => ({ ...current, scope, provider: '' }))}
                template={learningPathsTemplate}
              />
            </div>
            {form.scope === 'all' ? (
              <div className="sm:col-span-2">
                <ProviderFilter
                  id="lp-provider"
                  value={form.provider}
                  onChange={(provider) => setForm((current) => ({ ...current, provider }))}
                />
              </div>
            ) : null}
            <div className="min-w-0 space-y-1.5">
              <label htmlFor="lp-q" className={fieldLabelClass}>
                {lp.filters.q}
              </label>
              <Input
                id="lp-q"
                type="search"
                autoComplete="off"
                value={form.q}
                onChange={(event) => setForm({ ...form, q: event.target.value })}
              />
            </div>
            <div className="min-w-0 space-y-1.5">
              <label htmlFor="lp-contains" className={fieldLabelClass}>
                {lp.filters.contains}
              </label>
              <Input
                id="lp-contains"
                autoComplete="off"
                spellCheck={false}
                placeholder={lp.filters.containsHint}
                className="font-mono text-[13px]"
                value={form.contains}
                onChange={(event) => setForm({ ...form, contains: event.target.value })}
              />
            </div>
            <div className="min-w-0 space-y-1.5">
              <label htmlFor="lp-audience" className={fieldLabelClass}>
                {lp.filters.audience}
              </label>
              <Input
                id="lp-audience"
                list="lp-audience-options"
                autoComplete="off"
                spellCheck={false}
                value={form.audience}
                onChange={(event) => setForm({ ...form, audience: event.target.value })}
              />
              <datalist id="lp-audience-options">
                {AUDIENCES.map((audience) => (
                  <option key={audience} value={audience} />
                ))}
              </datalist>
            </div>
            <div className="min-w-0 space-y-1.5">
              <label htmlFor="lp-limit" className={fieldLabelClass}>
                {lp.filters.limit}
              </label>
              <Select value={String(form.limit)} onValueChange={(value) => setForm({ ...form, limit: Number(value) })}>
                <SelectTrigger id="lp-limit" className="w-full">
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
          <div className="space-y-3" aria-hidden="true">
            <Skeleton className="h-28 w-full" />
            <Skeleton className="h-28 w-full" />
          </div>
        ) : null}

        {result ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{lp.resultsHeading}</h3>
            <p className="text-sm text-muted-foreground">
              {result.total === null
                ? fmt(lp.resultsCount, { count: result.items.length })
                : fmt(lp.resultsSummary, { count: result.items.length, total: result.total })}
              {result.snapshotId ? (
                <>
                  {' · '}
                  {copy.resources.snapshotLabel} <code className="font-mono text-xs break-all">{result.snapshotId}</code>
                </>
              ) : null}
            </p>
            {result.items.length === 0 ? (
              <p className="text-sm">{lp.empty}</p>
            ) : (
              <ul className="space-y-3">
                {result.items.map((item) => (
                  <PathCard key={item.id} path={item} scope={resultScope} />
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

      <Section title={lp.paramsHeading}>
        <Definitions
          rows={[
            { name: 'provider', type: 'string', note: lp.params.provider },
            { name: 'q', type: 'string', note: lp.params.q },
            { name: 'contains', type: 'string', note: lp.params.contains },
            { name: 'audience', type: 'string', note: lp.params.audience },
            { name: 'cursor', type: 'string', note: lp.params.cursor },
            {
              name: 'limit',
              type: 'integer',
              note: fmt(lp.params.limit, { default: LIST_LIMIT_DEFAULT, max: LIST_LIMIT_MAX }),
            },
          ]}
        />
        <CodeBlock label={copy.labels.curl} language="bash" code={curlFor(listLearningPathsPath('all', { provider: 'gemini', limit: 5 }))} />
      </Section>

      <Section title={lp.responseHeading} lede={lp.shapeNote}>
        <Definitions
          rows={[
            { name: 'items', type: 'LearningPath[]', note: lp.response.items },
            { name: 'items[].stepCount', type: 'integer', note: lp.response.stepCount },
            { name: 'items[].steps', type: 'LearningPathStep[]', note: lp.response.steps },
            { name: 'items[].steps[].resourceId', type: 'string | null', note: lp.response.stepResourceId },
            { name: 'nextCursor', type: 'string | null', note: lp.response.nextCursor },
            { name: 'total', type: 'number', note: lp.response.total },
            { name: 'snapshotId', type: 'string', note: lp.response.snapshotId },
          ]}
        />
        <CodeBlock label={copy.labels.shape} language="json" code={LEARNING_PATH_LIST_SHAPE} />
      </Section>

      <Section title={lp.singleHeading} lede={lp.singleLede}>
        <CodeBlock label={copy.labels.curl} language="bash" code={curlFor(learningPathTemplate('all'))} />
      </Section>
    </article>
  )
}
