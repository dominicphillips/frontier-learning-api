import { useEffect, useRef, useState } from 'react'
import { CodeBlock } from '@/components/code-block'
import { Link } from '@/components/link'
import { Definitions, PageHeader, Section, TableSheet } from '@/components/doc'
import { RequestPanel } from '@/components/request-panel'
import { ProviderFilter, RouteSelect } from '@/components/route-select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { copy } from '@/copy'
import { useRequest } from '@/hooks/use-request'
import {
  categoriesPath,
  categoriesTemplate,
  isProviderId,
  parseScope,
  queryString,
  toCategoryList,
  type ProviderId,
  type Scope,
} from '@/lib/api'
import { CATEGORIES_SHAPE } from '@/lib/examples'
import { navigate } from '@/lib/router'
import { DOCS_ROUTES, categoryRoute } from '@/lib/routes'

interface Draft {
  scope: Scope
  provider: ProviderId | ''
}

function fromSearch(search: URLSearchParams): Draft {
  const scope = parseScope(search.get('scope'))
  const provider = search.get('provider')
  return { scope, provider: scope === 'all' && isProviderId(provider) ? provider : '' }
}

function pageRoute(draft: Draft): string {
  return `${DOCS_ROUTES.categories}${queryString({
    scope: draft.scope === 'all' ? undefined : draft.scope,
    provider: draft.provider || undefined,
  })}`
}

export function CategoriesPage({ search }: { search: URLSearchParams }) {
  const { state, run } = useRequest()
  const [draft, setDraft] = useState<Draft>(() => fromSearch(search))
  const [appliedScope, setAppliedScope] = useState<Scope>(draft.scope)
  const started = useRef(false)
  const path = categoriesPath(draft.scope, draft.provider)

  function execute(next: Draft) {
    setAppliedScope(next.scope)
    navigate(pageRoute(next), { replace: true })
    run(categoriesPath(next.scope, next.provider))
  }

  useEffect(() => {
    if (started.current) return
    started.current = true
    // A shared link that names a route or provider runs immediately, like a filtered resource link.
    if (draft.scope !== 'all' || draft.provider) execute(draft)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const result = state.phase === 'done' && state.result.ok ? toCategoryList(state.result.json) : null
  const aggregate = result?.items.some((category) => category.provider !== null) ?? false
  const response = copy.categories.response

  return (
    <article className="space-y-10">
      <PageHeader title={copy.categories.title} lede={copy.categories.lede} />

      <Section wide title={copy.categories.tryHeading}>
        <RequestPanel path={path} state={state} onRun={() => execute(draft)}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className={draft.scope === 'all' ? undefined : 'sm:col-span-2'}>
              <RouteSelect
                id="categories-route"
                value={draft.scope}
                onChange={(scope) => setDraft({ scope, provider: '' })}
                template={categoriesTemplate}
              />
            </div>
            {draft.scope === 'all' ? (
              <ProviderFilter id="categories-provider" value={draft.provider} onChange={(provider) => setDraft({ ...draft, provider })} />
            ) : null}
          </div>
        </RequestPanel>
        {state.phase === 'loading' ? <Skeleton className="h-32 w-full" aria-hidden="true" /> : null}
        {result ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{copy.categories.resultsHeading}</h3>
            {result.items.length === 0 ? (
              <p className="text-sm">{copy.categories.empty}</p>
            ) : (
              <TableSheet>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{copy.categories.columns.label}</TableHead>
                      {aggregate ? <TableHead>{copy.categories.columns.provider}</TableHead> : null}
                      <TableHead>{copy.categories.columns.id}</TableHead>
                      <TableHead className="text-right">{copy.categories.columns.count}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.items.map((category) => (
                      <TableRow key={category.id}>
                        <TableCell className="whitespace-normal [overflow-wrap:anywhere]">
                          <Link to={categoryRoute(category.id, appliedScope)} className="font-medium underline-offset-4 hover:underline">
                            {category.label}
                          </Link>
                        </TableCell>
                        {aggregate ? (
                          <TableCell className="font-mono text-[13px] text-muted-foreground">{category.provider ?? ''}</TableCell>
                        ) : null}
                        <TableCell className="font-mono text-[13px] whitespace-normal text-muted-foreground [overflow-wrap:anywhere]">
                          {category.id}
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{category.count ?? ''}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableSheet>
            )}
          </div>
        ) : null}
      </Section>

      <Section title={copy.categories.responseHeading} lede={copy.categories.shapeNote}>
        <Definitions
          rows={[
            { name: 'items', type: 'Category[]', note: response.items },
            { name: 'items[].id', type: 'string', note: response.id },
            { name: 'items[].provider', type: 'string', note: response.provider },
            { name: 'items[].slug', type: 'string', note: response.slug },
            { name: 'items[].label', type: 'string', note: response.label },
            { name: 'items[].count', type: 'number', note: response.count },
            { name: 'snapshotId', type: 'string', note: response.snapshotId },
          ]}
        />
        <CodeBlock label={copy.labels.shape} language="json" code={CATEGORIES_SHAPE} />
      </Section>
    </article>
  )
}
