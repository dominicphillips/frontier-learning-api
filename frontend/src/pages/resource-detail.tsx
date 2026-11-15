import { useEffect, useState } from 'react'
import { ExternalLinkIcon } from 'lucide-react'
import { CodeBlock } from '@/components/code-block'
import { CopyButton } from '@/components/copy-button'
import { Definitions, Field, PageHeader, Section } from '@/components/doc'
import { Link } from '@/components/link'
import { RequestPanel } from '@/components/request-panel'
import { RouteSelect, fieldLabelClass } from '@/components/route-select'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { copy } from '@/copy'
import { useRequest } from '@/hooks/use-request'
import {
  parseScope,
  providerForId,
  resourcePath,
  resourceTemplate,
  sectionLabel,
  toResource,
  type Resource,
  type Scope,
} from '@/lib/api'
import { durationEntries } from '@/lib/duration'
import { RESOURCE_SHAPE } from '@/lib/examples'
import { formatDateTime, safeHttpUrl, shortHash } from '@/lib/format'
import { navigate } from '@/lib/router'
import { categoryRoute, resourceRoute } from '@/lib/routes'

const linkClass = 'underline-offset-4 hover:underline'

function ExternalUrl({ url }: { url: string }) {
  const href = safeHttpUrl(url)
  if (!href) return <span className="font-mono text-[13px] break-all">{url}</span>
  return (
    <a href={href} target="_blank" rel="noreferrer" className={`font-mono text-[13px] break-all ${linkClass}`}>
      {url}
    </a>
  )
}

function ResourceView({ resource, scope }: { resource: Resource; scope: Scope }) {
  const view = copy.resource.view
  const durations = durationEntries(resource.duration)
  const sections = resource.detail.sections.map(sectionLabel).filter((label): label is string => label !== null)
  const unknown = <span className="text-muted-foreground">{view.unknown}</span>
  const officialUrl = safeHttpUrl(resource.url)
  // Aggregate records name their provider; provider-route records carry it in the ID prefix.
  const provider = resource.provider ?? (scope === 'all' ? providerForId(resource.id) : scope)

  return (
    <div className="space-y-6 rounded-xl border bg-card p-4 sm:p-5">
      <div className="space-y-2">
        <h3 className="text-xl font-semibold tracking-tight [overflow-wrap:anywhere]">{resource.title}</h3>
        <div className="flex flex-wrap gap-1.5">
          {provider ? (
            <Badge variant="default" className="font-mono">
              {provider}
            </Badge>
          ) : null}
          {resource.kind ? <Badge variant="secondary">{resource.kind}</Badge> : null}
          {resource.level ? <Badge variant="outline">{resource.level}</Badge> : null}
          {resource.audiences.map((audience) => (
            <Badge key={audience} variant="outline">
              {audience}
            </Badge>
          ))}
        </div>
        {resource.summary ? <p className="text-sm leading-6 text-body [overflow-wrap:anywhere]">{resource.summary}</p> : null}
      </div>

      <div className="space-y-2 rounded-lg bg-muted/60 p-3">
        <p className="text-xs font-medium text-muted-foreground">{view.officialUrl}</p>
        {resource.url ? (
          <>
            <ExternalUrl url={resource.url} />
            <div className="flex flex-wrap gap-3 pt-1">
              {officialUrl ? (
                <Button asChild size="sm" className="max-w-full">
                  <a href={officialUrl} target="_blank" rel="noreferrer" title={copy.actions.openOfficial}>
                    <ExternalLinkIcon data-icon="inline-start" aria-hidden="true" />
                    <span className="truncate">{copy.actions.openOfficial}</span>
                  </a>
                </Button>
              ) : null}
              <CopyButton text={resource.url} />
            </div>
          </>
        ) : (
          <p className="text-sm">{unknown}</p>
        )}
      </div>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2">
        <Field label={view.id}>
          <code className="font-mono text-[13px]">{resource.id}</code>
        </Field>
        <Field label={view.provider}>{provider ? <code className="font-mono text-[13px]">{provider}</code> : unknown}</Field>
        <Field label={view.kind}>{resource.kind || unknown}</Field>
        <Field label={view.level}>{resource.level ?? unknown}</Field>
        <Field label={view.categories}>
          {resource.categoryIds.length ? (
            <span className="flex flex-wrap gap-x-2 gap-y-1">
              {resource.categoryIds.map((id) => (
                <Link key={id} to={categoryRoute(id, scope)} className={`font-mono text-[13px] ${linkClass}`}>
                  {id}
                </Link>
              ))}
            </span>
          ) : (
            unknown
          )}
        </Field>
        {durations.length ? (
          durations.map((entry) => (
            <Field key={entry.key} label={entry.label}>
              {entry.value}
            </Field>
          ))
        ) : (
          <Field label={view.duration}>{unknown}</Field>
        )}
        <Field label={view.tags}>
          {resource.tags.length ? (
            <span className="flex flex-wrap gap-1">
              {resource.tags.map((tag) => (
                <Badge key={tag} variant="outline">
                  {tag}
                </Badge>
              ))}
            </span>
          ) : (
            unknown
          )}
        </Field>
        {resource.detail.audience ? <Field label={view.detailAudience}>{resource.detail.audience}</Field> : null}
      </dl>

      {resource.detail.prerequisites.length ? (
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium text-muted-foreground">{view.prerequisites}</h4>
          <ul className="list-disc space-y-1 pl-5 text-sm leading-6 [overflow-wrap:anywhere]">
            {resource.detail.prerequisites.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {resource.detail.objectives.length ? (
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium text-muted-foreground">{view.objectives}</h4>
          <ul className="list-disc space-y-1 pl-5 text-sm leading-6 [overflow-wrap:anywhere]">
            {resource.detail.objectives.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {sections.length ? (
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium text-muted-foreground">{view.sections}</h4>
          <ol className="list-decimal space-y-1 pl-5 text-sm leading-6 [overflow-wrap:anywhere]">
            {sections.map((item, index) => (
              <li key={`${index}-${item}`}>{item}</li>
            ))}
          </ol>
        </div>
      ) : null}

      <div className="space-y-2 border-t pt-4">
        <h4 className="text-xs font-medium text-muted-foreground">{view.provenance}</h4>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
          <Field label={view.fetchedAt}>{resource.provenance.fetchedAt ? formatDateTime(resource.provenance.fetchedAt) : unknown}</Field>
          <Field label={view.method}>{resource.provenance.method ?? unknown}</Field>
          <Field label={view.contentHash}>
            {resource.provenance.contentHash ? (
              <code className="font-mono text-[13px]" title={resource.provenance.contentHash}>
                {shortHash(resource.provenance.contentHash)}
              </code>
            ) : (
              unknown
            )}
          </Field>
          <Field label={view.sourceUrls}>
            {resource.provenance.sourceUrls.length ? (
              <ul className="space-y-0.5">
                {resource.provenance.sourceUrls.map((url) => (
                  <li key={url}>
                    <ExternalUrl url={url} />
                  </li>
                ))}
              </ul>
            ) : (
              unknown
            )}
          </Field>
        </dl>
      </div>
    </div>
  )
}

export function ResourceDetailPage({ id, search }: { id?: string; search: URLSearchParams }) {
  const { state, run } = useRequest()
  const routeScope = parseScope(search.get('scope'))
  const [draft, setDraft] = useState(id ?? '')
  const [scope, setScope] = useState<Scope>(routeScope)
  const [draftFor, setDraftFor] = useState(`${id ?? ''} ${routeScope}`)

  // A new id or route in the URL replaces the draft (state adjusted during render, no effect needed).
  const routeKey = `${id ?? ''} ${routeScope}`
  if (draftFor !== routeKey) {
    setDraftFor(routeKey)
    setDraft(id ?? '')
    setScope(routeScope)
  }

  useEffect(() => {
    if (id) run(resourcePath(id, routeScope))
  }, [id, routeScope, run])

  const next = draft.trim()

  // The same ID and route run again in place; anything else becomes its own shareable route.
  function runDraft() {
    if (!next) return
    if (next === id && scope === routeScope) run(resourcePath(id, routeScope))
    else navigate(resourceRoute(next, scope))
  }

  const fields = copy.resource.fields
  const resource = state.phase === 'done' && state.result.ok ? toResource(state.result.json) : null

  return (
    <article className="space-y-10">
      <PageHeader title={copy.resource.title} lede={copy.resource.lede} />

      <Section wide title={copy.resource.tryHeading} lede={copy.resource.idHint}>
        <RequestPanel path={next ? resourcePath(next, scope) : resourceTemplate(scope)} state={state} onRun={runDraft} showRun={next !== ''}>
          <div className="grid grid-cols-1 gap-4">
            <RouteSelect id="resource-route" value={scope} onChange={setScope} template={resourceTemplate} />
            <div className="min-w-0 space-y-1.5">
              <label htmlFor="resource-id" className={fieldLabelClass}>
                {copy.resource.idLabel}
              </label>
              <Input
                id="resource-id"
                autoComplete="off"
                spellCheck={false}
                className="font-mono text-[13px]"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
              />
            </div>
          </div>
        </RequestPanel>

        {state.phase === 'loading' ? <Skeleton className="h-40 w-full" aria-hidden="true" /> : null}
        {resource ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{copy.resource.viewHeading}</h3>
            <ResourceView resource={resource} scope={routeScope} />
          </div>
        ) : null}
      </Section>

      <Section title={copy.resource.fieldsHeading} lede={copy.resource.shapeNote}>
        <Definitions
          rows={[
            { name: 'id', type: 'string', note: fields.id },
            { name: 'provider', type: 'string', note: fields.provider },
            { name: 'title', type: 'string', note: fields.title },
            { name: 'url', type: 'string', note: fields.url },
            { name: 'kind', type: 'string', note: fields.kind },
            { name: 'categoryIds', type: 'string[]', note: fields.categoryIds },
            { name: 'audiences', type: 'string[]', note: fields.audiences },
            { name: 'tags', type: 'string[]', note: fields.tags },
            { name: 'summary', type: 'string | null', note: fields.summary },
            { name: 'level', type: 'string | null', note: fields.level },
            { name: 'duration', type: 'object', note: fields.duration },
            { name: 'detail', type: 'object', note: fields.detail },
            { name: 'media', type: 'object[]', note: fields.media },
            { name: 'artwork', type: 'object | null', note: fields.artwork },
            { name: 'provenance', type: 'object', note: fields.provenance },
          ]}
        />
        <CodeBlock label={copy.labels.shape} language="json" code={RESOURCE_SHAPE} />
      </Section>
    </article>
  )
}
