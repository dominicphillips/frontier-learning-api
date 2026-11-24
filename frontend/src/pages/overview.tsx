import { Fragment, useState } from 'react'
import { CodeBlock } from '@/components/code-block'
import { Link } from '@/components/link'
import { Bullets, PageHeader, Section, TableSheet } from '@/components/doc'
import { RequestPanel } from '@/components/request-panel'
import { fieldLabelClass } from '@/components/route-select'
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { copy } from '@/copy'
import { useRequest } from '@/hooks/use-request'
import {
  API_BASE,
  API_EXPLORER_PATH,
  CATEGORIES_PATH,
  DEPLOYEDWORK_URL,
  GITHUB_URL,
  HEALTH_PATH,
  LEARNING_PATHS_PATH,
  OPENAPI_PATH,
  PROVIDERS,
  PROVIDERS_PATH,
  PROVIDER_IDS,
  READY_PATH,
  RESOURCES_PATH,
  STATUS_PATH,
  curlFor,
  listLearningPathsPath,
  listResourcesPath,
} from '@/lib/api'
import { DOCS_ROUTES } from '@/lib/routes'

const QUICK_START_PATH = listResourcesPath('all', { limit: 5 })
const QUICK_LEARNING_PATHS = listLearningPathsPath('all', { limit: 5 })
const AGGREGATE_TRY_PATHS = [QUICK_START_PATH, QUICK_LEARNING_PATHS, PROVIDERS_PATH, CATEGORIES_PATH, STATUS_PATH, HEALTH_PATH]
const PROVIDER_TRY_PATHS = PROVIDER_IDS.map((provider) => listResourcesPath(provider, { limit: 5 }))
const TRY_GROUPS = [AGGREGATE_TRY_PATHS, PROVIDER_TRY_PATHS]

type EndpointKey = keyof typeof copy.endpoints

const ENDPOINTS: { path: string; to: string; key: EndpointKey }[] = [
  { path: RESOURCES_PATH, to: DOCS_ROUTES.resources, key: 'listResources' },
  { path: `${RESOURCES_PATH}/{id}`, to: DOCS_ROUTES.resource, key: 'getResource' },
  { path: LEARNING_PATHS_PATH, to: DOCS_ROUTES.learningPaths, key: 'listLearningPaths' },
  { path: `${LEARNING_PATHS_PATH}/{id}`, to: DOCS_ROUTES.learningPaths, key: 'getLearningPath' },
  { path: CATEGORIES_PATH, to: DOCS_ROUTES.categories, key: 'categories' },
  { path: STATUS_PATH, to: DOCS_ROUTES.status, key: 'status' },
  { path: PROVIDERS_PATH, to: `${DOCS_ROUTES.status}#providers`, key: 'providers' },
]

const PROVIDER_ENDPOINTS: { path: string; to: string; key: EndpointKey }[] = [
  { path: '/v1/providers/{provider}/resources', to: DOCS_ROUTES.resources, key: 'providerResources' },
  { path: '/v1/providers/{provider}/resources/{id}', to: DOCS_ROUTES.resource, key: 'providerResource' },
  { path: '/v1/providers/{provider}/learning-paths', to: DOCS_ROUTES.learningPaths, key: 'providerLearningPaths' },
  { path: '/v1/providers/{provider}/learning-paths/{id}', to: DOCS_ROUTES.learningPaths, key: 'providerLearningPath' },
  { path: '/v1/providers/{provider}/categories', to: DOCS_ROUTES.categories, key: 'providerCategories' },
  { path: '/v1/providers/{provider}/status', to: DOCS_ROUTES.status, key: 'providerStatus' },
]

// Server routes outside the catalog: plain links, each opens as its own document.
const SUPPORT_ENDPOINTS: { path: string; key: EndpointKey }[] = [
  { path: HEALTH_PATH, key: 'health' },
  { path: READY_PATH, key: 'ready' },
  { path: OPENAPI_PATH, key: 'openapi' },
]

const linkClass = 'underline-offset-4 hover:underline'
const routeCellClass = 'font-mono text-[13px] [overflow-wrap:anywhere] whitespace-normal'

function EndpointTable({
  rows,
  support = [],
}: {
  rows: { path: string; to: string; key: EndpointKey }[]
  support?: { path: string; key: EndpointKey }[]
}) {
  return (
    <TableSheet>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[45%]">{copy.overview.endpointColumnPath}</TableHead>
            <TableHead>{copy.overview.endpointColumnDescription}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((endpoint) => (
            <TableRow key={endpoint.path}>
              <TableCell className={routeCellClass}>
                <Link to={endpoint.to} className={linkClass}>
                  <span className="text-muted-foreground">GET </span>
                  {endpoint.path}
                </Link>
              </TableCell>
              <TableCell className="whitespace-normal text-muted-foreground">{copy.endpoints[endpoint.key]}</TableCell>
            </TableRow>
          ))}
          {support.map((endpoint) => (
            <TableRow key={endpoint.path}>
              <TableCell className={routeCellClass}>
                <a href={endpoint.path} className={linkClass}>
                  <span className="text-muted-foreground">GET </span>
                  {endpoint.path}
                </a>
              </TableCell>
              <TableCell className="whitespace-normal text-muted-foreground">{copy.endpoints[endpoint.key]}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableSheet>
  )
}

export function OverviewPage() {
  const { state, run } = useRequest()
  const [path, setPath] = useState<string>(QUICK_START_PATH)
  const conventions = copy.overview.conventions
  const columns = copy.overview.providerColumns

  return (
    <article className="space-y-10">
      <PageHeader title={copy.overview.title} lede={copy.overview.lede} />

      <Section wide title={copy.overview.tryHeading} lede={copy.overview.tryLede}>
        <RequestPanel path={path} state={state} onRun={() => run(path)}>
          <div className="space-y-1.5">
            <label htmlFor="try-endpoint" className={fieldLabelClass}>
              {copy.overview.endpointLabel}
            </label>
            <Select value={path} onValueChange={setPath}>
              <SelectTrigger id="try-endpoint" title={`GET ${path}`} className="w-full font-mono text-[13px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TRY_GROUPS.map((group, index) => (
                  <Fragment key={group[0]}>
                    {index > 0 ? <SelectSeparator /> : null}
                    {group.map((option) => (
                      <SelectItem key={option} value={option} className="font-mono text-[13px]">
                        GET {option}
                      </SelectItem>
                    ))}
                  </Fragment>
                ))}
              </SelectContent>
            </Select>
          </div>
        </RequestPanel>
      </Section>

      <Section title={copy.overview.baseUrlHeading} lede={copy.overview.baseUrlLede}>
        <CodeBlock label={copy.labels.baseUrl} code={API_BASE} wrapToggle={false} />
      </Section>

      <Section title={copy.overview.quickStartHeading} lede={copy.overview.quickStartLede}>
        <CodeBlock label={copy.labels.curl} language="bash" code={curlFor(QUICK_START_PATH)} />
      </Section>

      <Section title={copy.overview.endpointsHeading} lede={copy.overview.endpointsLede}>
        <EndpointTable rows={ENDPOINTS} support={SUPPORT_ENDPOINTS} />
      </Section>

      <Section title={copy.overview.providerEndpointsHeading} lede={copy.overview.providerEndpointsLede}>
        <EndpointTable rows={PROVIDER_ENDPOINTS} />
      </Section>

      <Section title={copy.overview.providersHeading} lede={copy.overview.providersLede}>
        <TableSheet>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{columns.provider}</TableHead>
                <TableHead>{columns.prefix}</TableHead>
                <TableHead>{columns.source}</TableHead>
                <TableHead>{columns.kinds}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {PROVIDER_IDS.map((provider) => {
                const facts = PROVIDERS[provider]
                return (
                  <TableRow key={provider}>
                    <TableCell className="align-top whitespace-normal">
                      <code className="block font-mono text-[13px]">{provider}</code>
                      <span className="text-xs text-muted-foreground">{facts.label}</span>
                    </TableCell>
                    <TableCell className="align-top font-mono text-[13px]">{facts.prefix}</TableCell>
                    <TableCell className="align-top font-mono text-[13px] [overflow-wrap:anywhere] whitespace-normal">
                      <a href={facts.sourceUrl} target="_blank" rel="noreferrer" className={linkClass}>
                        {facts.sourceUrl.replace(/^https:\/\//, '')}
                      </a>
                    </TableCell>
                    <TableCell className="align-top font-mono text-[12px] leading-5 whitespace-normal text-muted-foreground">
                      {facts.kinds.join(', ')}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableSheet>
      </Section>

      <Section title={copy.overview.conventionsHeading}>
        <Bullets
          items={[
            conventions.readOnly,
            conventions.scopes,
            conventions.cursors,
            conventions.nulls,
            conventions.durations,
            conventions.sources,
            conventions.notExposed,
            conventions.availability,
            conventions.caching,
          ]}
        />
      </Section>

      <Section title={copy.overview.linksHeading} lede={copy.overview.linksLede}>
        <ul className="space-y-1.5 text-sm">
          <li>
            <a href={OPENAPI_PATH} className={linkClass}>
              {copy.nav.openapi}
            </a>{' '}
            <code className="font-mono text-xs text-muted-foreground">{OPENAPI_PATH}</code>
          </li>
          <li>
            <a href={API_EXPLORER_PATH} className={linkClass}>
              {copy.nav.apiExplorer}
            </a>{' '}
            <code className="font-mono text-xs text-muted-foreground">{API_EXPLORER_PATH}</code>
          </li>
          <li>
            <a href={HEALTH_PATH} className={linkClass}>
              {copy.nav.health}
            </a>{' '}
            <code className="font-mono text-xs text-muted-foreground">{HEALTH_PATH}</code>
          </li>
          <li>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className={linkClass}>
              {copy.nav.github}
            </a>
          </li>
          <li>
            <a href={DEPLOYEDWORK_URL} target="_blank" rel="noreferrer" className={linkClass}>
              DeployedWork
            </a>
          </li>
        </ul>
      </Section>
    </article>
  )
}
