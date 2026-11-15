import { useEffect, useRef, useState } from 'react'
import { CodeBlock } from '@/components/code-block'
import { Bullets, Definitions, PageHeader, Section, TableSheet } from '@/components/doc'
import { RequestPanel } from '@/components/request-panel'
import { RouteSelect } from '@/components/route-select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { copy } from '@/copy'
import { useRequest } from '@/hooks/use-request'
import { PROVIDERS_PATH, curlFor, isRecord, numberOrNull, parseScope, statusPath, statusTemplate, stringOrNull, type Scope } from '@/lib/api'
import { PROVIDERS_SHAPE } from '@/lib/examples'
import { formatDateTime, shortHash } from '@/lib/format'
import { navigate } from '@/lib/router'
import { DOCS_ROUTES, scopedRoute } from '@/lib/routes'

type Primitive = string | number | boolean | null

// Top-level scalar fields of the live payload; nested values get their own tables or stay in the JSON.
function scalarEntries(value: unknown): [string, Primitive][] {
  if (!isRecord(value)) return []
  const entries: [string, Primitive][] = []
  for (const [key, item] of Object.entries(value)) {
    if (item === null || typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean') {
      entries.push([key, item])
    }
  }
  return entries
}

interface ProviderRow {
  id: string
  state: string | null
  resourceCount: number | null
  lastSuccessAt: string | null
  snapshotId: string | null
}

function providerRows(value: unknown): ProviderRow[] {
  if (!isRecord(value) || !isRecord(value.providers)) return []
  return Object.entries(value.providers).map(([id, item]) => {
    const status = isRecord(item) ? item : {}
    return {
      id,
      state: stringOrNull(status.state),
      resourceCount: numberOrNull(status.resourceCount),
      lastSuccessAt: stringOrNull(status.lastSuccessAt),
      snapshotId: stringOrNull(status.snapshotId),
    }
  })
}

interface CoverageRow {
  categoryId: string
  state: string | null
  discovered: number | null
  collected: number | null
}

function coverageRows(value: unknown): CoverageRow[] {
  if (!isRecord(value) || !Array.isArray(value.coverage)) return []
  return value.coverage.filter(isRecord).map((item) => ({
    categoryId: stringOrNull(item.categoryId) ?? '',
    state: stringOrNull(item.state),
    discovered: numberOrNull(item.discovered),
    collected: numberOrNull(item.collected),
  }))
}

const monoCell = 'font-mono text-[13px] whitespace-normal [overflow-wrap:anywhere]'

export function StatusPage({ search }: { search: URLSearchParams }) {
  const { state, run } = useRequest()
  const [scope, setScope] = useState<Scope>(() => parseScope(search.get('scope')))
  const started = useRef(false)
  const json = state.phase === 'done' ? state.result.json : null
  const entries = scalarEntries(json)
  const providers = providerRows(json)
  const coverage = coverageRows(json)
  const providerList = copy.status.providerList

  function execute(next: Scope) {
    navigate(scopedRoute(DOCS_ROUTES.status, next), { replace: true })
    run(statusPath(next))
  }

  useEffect(() => {
    if (started.current) return
    started.current = true
    if (scope !== 'all') execute(scope)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <article className="space-y-10">
      <PageHeader title={copy.status.title} lede={copy.status.lede} />

      <Section wide title={copy.status.tryHeading}>
        <RequestPanel path={statusPath(scope)} state={state} onRun={() => execute(scope)}>
          <RouteSelect id="status-route" value={scope} onChange={setScope} template={statusTemplate} />
        </RequestPanel>
        {entries.length ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{copy.status.resultsHeading}</h3>
            <TableSheet>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{copy.status.columns.field}</TableHead>
                    <TableHead>{copy.status.columns.value}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entries.map(([key, value]) => (
                    <TableRow key={key}>
                      <TableCell className="font-mono text-[13px]">{key}</TableCell>
                      <TableCell className="font-mono text-[13px] whitespace-normal break-all">{String(value)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableSheet>
          </div>
        ) : null}
        {providers.length ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{copy.status.providersHeading}</h3>
            <TableSheet>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{copy.status.columns.provider}</TableHead>
                    <TableHead className="font-mono">state</TableHead>
                    <TableHead className="text-right font-mono">resourceCount</TableHead>
                    <TableHead className="font-mono">lastSuccessAt</TableHead>
                    <TableHead className="font-mono">snapshotId</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {providers.map((row) => (
                    <TableRow key={row.id}>
                      <TableCell className="font-mono text-[13px]">{row.id}</TableCell>
                      <TableCell className={monoCell}>{row.state ?? ''}</TableCell>
                      <TableCell className="text-right tabular-nums">{row.resourceCount ?? ''}</TableCell>
                      <TableCell className="text-[13px] whitespace-normal">{row.lastSuccessAt ? formatDateTime(row.lastSuccessAt) : ''}</TableCell>
                      <TableCell className={monoCell} title={row.snapshotId ?? undefined}>
                        {row.snapshotId ? shortHash(row.snapshotId, 12) : ''}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableSheet>
          </div>
        ) : null}
        {coverage.length ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold">{copy.status.coverageHeading}</h3>
            <TableSheet>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="font-mono">categoryId</TableHead>
                    <TableHead className="font-mono">state</TableHead>
                    <TableHead className="text-right font-mono">discovered</TableHead>
                    <TableHead className="text-right font-mono">collected</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {coverage.map((row, index) => (
                    <TableRow key={`${row.categoryId}-${index}`}>
                      <TableCell className={monoCell}>{row.categoryId}</TableCell>
                      <TableCell className={monoCell}>{row.state ?? ''}</TableCell>
                      <TableCell className="text-right tabular-nums">{row.discovered ?? ''}</TableCell>
                      <TableCell className="text-right tabular-nums">{row.collected ?? ''}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableSheet>
          </div>
        ) : null}
      </Section>

      <Section title={copy.status.fieldsHeading}>
        <Definitions
          rows={[
            { name: 'state', note: copy.status.fields.freshness },
            { name: 'resourceCount', type: 'number', note: copy.status.fields.resourceCount },
            { name: 'providers', type: 'object', note: copy.status.fields.providers },
            { name: 'coverage', note: copy.status.fields.coverage },
          ]}
        />
        <Bullets items={[copy.status.note]} />
      </Section>

      <Section id="providers" title={providerList.heading} lede={providerList.lede}>
        <Definitions
          rows={[
            { name: 'items[].id', type: 'string', note: providerList.id },
            { name: 'items[].label', type: 'string', note: providerList.label },
            { name: 'items[].sourceUrl', type: 'string', note: providerList.sourceUrl },
            { name: 'items[].resourcePrefix', type: 'string', note: providerList.resourcePrefix },
            { name: 'items[].kinds', type: 'string[]', note: providerList.kinds },
            { name: 'items[].status', type: 'Status', note: providerList.status },
          ]}
        />
        <CodeBlock label={copy.labels.curl} language="bash" code={curlFor(PROVIDERS_PATH)} />
        <CodeBlock label={copy.labels.shape} language="json" code={PROVIDERS_SHAPE} />
      </Section>
    </article>
  )
}
