import { useEffect } from 'react'
import { Shell, type PageKey } from '@/components/layout'
import { copy, fmt } from '@/copy'
import { useLocation } from '@/lib/router'
import { DOCS_ROUTES } from '@/lib/routes'
import { CategoriesPage } from '@/pages/categories'
import { NotFoundPage } from '@/pages/not-found'
import { OverviewPage } from '@/pages/overview'
import { ResourceDetailPage } from '@/pages/resource-detail'
import { ResourcesPage } from '@/pages/resources'
import { StatusPage } from '@/pages/status'

interface Route {
  page: PageKey
  id?: string
}

// The documentation app lives under /docs; the server owns /docs/api (Swagger UI) and /openapi.json.
function resolve(pathname: string): Route {
  if (pathname === DOCS_ROUTES.overview) return { page: 'overview' }
  if (pathname === DOCS_ROUTES.resources) return { page: 'resources' }
  if (pathname === DOCS_ROUTES.resource) return { page: 'resourceDetail' }
  const detail = pathname.match(/^\/docs\/resources\/([^/]+)$/)
  if (detail) return { page: 'resourceDetail', id: decodeURIComponent(detail[1]) }
  if (pathname === DOCS_ROUTES.categories) return { page: 'categories' }
  if (pathname === DOCS_ROUTES.status) return { page: 'status' }
  return { page: 'notFound' }
}

const TITLES: Record<PageKey, () => string> = {
  overview: () => copy.overview.title,
  resources: () => copy.resources.title,
  resourceDetail: () => copy.resource.title,
  categories: () => copy.categories.title,
  status: () => copy.status.title,
  notFound: () => copy.notFound.title,
}

export default function App() {
  const { pathname, search } = useLocation()
  const route = resolve(pathname)
  const title = TITLES[route.page]()

  useEffect(() => {
    document.title = fmt(copy.app.documentTitle, { page: title, site: copy.app.name })
  }, [title])

  let page
  switch (route.page) {
    case 'overview':
      page = <OverviewPage />
      break
    case 'resources':
      page = <ResourcesPage search={search} />
      break
    case 'resourceDetail':
      page = <ResourceDetailPage id={route.id} search={search} />
      break
    case 'categories':
      page = <CategoriesPage search={search} />
      break
    case 'status':
      page = <StatusPage search={search} />
      break
    default:
      page = <NotFoundPage />
  }

  return <Shell active={route.page}>{page}</Shell>
}
