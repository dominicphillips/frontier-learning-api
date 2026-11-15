import { Link } from '@/components/link'
import { Badge } from '@/components/ui/badge'
import type { Resource, Scope } from '@/lib/api'
import { durationEntries } from '@/lib/duration'
import { resourceRoute } from '@/lib/routes'

export function ResourceRow({ resource, scope }: { resource: Resource; scope: Scope }) {
  const durations = durationEntries(resource.duration)
  const meta = [
    ...durations.map((entry) => `${entry.label} ${entry.value}`),
    ...(resource.audiences.length ? [resource.audiences.join(', ')] : []),
  ]
  return (
    <li className="min-w-0 space-y-1 px-4 py-3">
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <Link
          to={resourceRoute(resource.id, scope)}
          className="min-w-0 font-medium [overflow-wrap:anywhere] underline-offset-4 hover:underline"
        >
          {resource.title}
        </Link>
        {resource.provider ? (
          <Badge variant="default" className="font-mono">
            {resource.provider}
          </Badge>
        ) : null}
        {resource.kind ? <Badge variant="secondary">{resource.kind}</Badge> : null}
        {resource.level ? <Badge variant="outline">{resource.level}</Badge> : null}
      </div>
      {resource.summary ? <p className="line-clamp-2 text-sm text-muted-foreground [overflow-wrap:anywhere]">{resource.summary}</p> : null}
      {meta.length ? <p className="text-xs text-muted-foreground [overflow-wrap:anywhere]">{meta.join(' · ')}</p> : null}
    </li>
  )
}
