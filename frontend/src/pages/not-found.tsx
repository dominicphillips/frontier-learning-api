import { PageHeader } from '@/components/doc'
import { Link } from '@/components/link'
import { Button } from '@/components/ui/button'
import { copy } from '@/copy'
import { DOCS_ROUTES } from '@/lib/routes'

export function NotFoundPage() {
  return (
    <article className="space-y-6">
      <PageHeader title={copy.notFound.title} lede={copy.notFound.lede} />
      <Button asChild variant="outline" className="max-w-full">
        <Link to={DOCS_ROUTES.overview} title={copy.actions.backHome}>
          <span className="truncate">{copy.actions.backHome}</span>
        </Link>
      </Button>
    </article>
  )
}
