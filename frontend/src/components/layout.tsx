import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'
import { MenuIcon, XIcon } from 'lucide-react'
import { Link } from '@/components/link'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { copy } from '@/copy'
import {
  API_EXPLORER_PATH,
  CATALOG_URL,
  CATEGORIES_PATH,
  DEPLOYEDWORK_URL,
  GITHUB_URL,
  HEALTH_PATH,
  OPENAPI_PATH,
  RESOURCES_PATH,
  STATUS_PATH,
} from '@/lib/api'
import { useLocation } from '@/lib/router'
import { DOCS_ROUTES } from '@/lib/routes'
import { cn } from '@/lib/utils'

export type PageKey = 'overview' | 'resources' | 'resourceDetail' | 'categories' | 'status' | 'notFound'

type ReferenceKey = Exclude<PageKey, 'notFound'>

// Endpoint rail entries pair the existing section labels with the literal route they document.
const REFERENCE_SECTIONS: { key: ReferenceKey; to: string; path?: string }[] = [
  { key: 'overview', to: DOCS_ROUTES.overview },
  { key: 'resources', to: DOCS_ROUTES.resources, path: RESOURCES_PATH },
  { key: 'resourceDetail', to: DOCS_ROUTES.resource, path: `${RESOURCES_PATH}/{id}` },
  { key: 'categories', to: DOCS_ROUTES.categories, path: CATEGORIES_PATH },
  { key: 'status', to: DOCS_ROUTES.status, path: STATUS_PATH },
]

// Server documents listed under the rail: each loads as its own page.
const SUPPORT_LINKS: { key: 'health' | 'openapi' | 'apiExplorer'; href: string }[] = [
  { key: 'health', href: HEALTH_PATH },
  { key: 'openapi', href: OPENAPI_PATH },
  { key: 'apiExplorer', href: API_EXPLORER_PATH },
]

const primaryLinkClass =
  'relative block rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground aria-[current=page]:font-medium aria-[current=page]:text-foreground'
const primaryBarClass =
  'md:after:absolute md:after:inset-x-2.5 md:after:-bottom-[13px] md:after:h-0.5 md:after:rounded-full md:after:bg-signal md:after:opacity-0 md:aria-[current=page]:after:opacity-100'
const externalLinkClass = 'block rounded-md px-2 py-1 text-sm text-muted-foreground transition-colors hover:text-foreground'
// Header labels sit in a fixed-height bar: one line, truncated, with the full text as a tooltip.
const barLabelClass = 'block max-w-[11rem] truncate'

function PrimaryLinks({ active, inHeader }: { active: PageKey; inHeader: boolean }) {
  return (
    <ul className={cn('flex', inHeader ? 'items-center gap-1' : 'flex-col gap-0.5')}>
      <li className="min-w-0">
        <a href={CATALOG_URL} title={copy.nav.courses} className={cn(primaryLinkClass, inHeader && primaryBarClass)}>
          <span className={inHeader ? barLabelClass : undefined}>{copy.nav.courses}</span>
        </a>
      </li>
      <li className="min-w-0">
        <Link
          to={DOCS_ROUTES.overview}
          title={copy.nav.reference}
          aria-current={active !== 'notFound' ? 'page' : undefined}
          className={cn(primaryLinkClass, inHeader && primaryBarClass)}
        >
          <span className={inHeader ? barLabelClass : undefined}>{copy.nav.reference}</span>
        </Link>
      </li>
    </ul>
  )
}

function RailLinks({ active }: { active: PageKey }) {
  return (
    <ul className="flex flex-col">
      {REFERENCE_SECTIONS.map((item) => (
        <li key={item.key}>
          <Link to={item.to} aria-current={active === item.key ? 'page' : undefined} className="rail-link rounded-r-md text-sm">
            <span className="block font-medium">{copy.nav[item.key]}</span>
            {item.path ? <span className="rail-path">GET {item.path}</span> : null}
          </Link>
        </li>
      ))}
    </ul>
  )
}

function SupportLinks({ className }: { className?: string }) {
  return (
    <ul className={className}>
      {SUPPORT_LINKS.map((item) => (
        <li key={item.key}>
          <a href={item.href} className="rail-link rounded-r-md text-sm">
            <span className="block font-medium">{copy.nav[item.key]}</span>
            <span className="rail-path">GET {item.href}</span>
          </a>
        </li>
      ))}
    </ul>
  )
}

function ExternalLinks({ className }: { className?: string }) {
  return (
    <ul className={className}>
      <li className="min-w-0">
        <a href={GITHUB_URL} target="_blank" rel="noreferrer" title={copy.nav.github} className={externalLinkClass}>
          <span className={barLabelClass}>{copy.nav.github}</span>
        </a>
      </li>
      <li className="min-w-0">
        <a href={OPENAPI_PATH} title={copy.nav.openapi} className={externalLinkClass}>
          <span className={barLabelClass}>{copy.nav.openapi}</span>
        </a>
      </li>
    </ul>
  )
}

export function Shell({ active, children }: { active: PageKey; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  const navId = useId()
  const toggleRef = useRef<HTMLButtonElement>(null)
  const [openedAt, setOpenedAt] = useState(pathname)
  const menuLabel = open ? copy.nav.closeMenu : copy.nav.menu

  // Close the disclosure when the route changes (state adjusted during render, no effect needed).
  if (openedAt !== pathname) {
    setOpenedAt(pathname)
    setOpen(false)
  }

  function closeOnEscape(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'Escape') {
      setOpen(false)
      toggleRef.current?.focus()
    }
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded-lg focus:border focus:border-edge focus:bg-card focus:px-3 focus:py-2 focus:text-sm"
      >
        {copy.nav.skipToContent}
      </a>
      <header className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-13 w-full max-w-[90rem] items-center gap-2 px-4 sm:px-6">
          <Link
            to={DOCS_ROUTES.overview}
            title={copy.app.name}
            className="flex min-w-0 items-center gap-2 text-sm font-semibold tracking-tight"
          >
            <span className="truncate">{copy.app.name}</span>
          </Link>
          <nav aria-label={copy.nav.primaryLabel} className="ml-4 hidden min-w-0 md:block">
            <PrimaryLinks active={active} inHeader />
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-1">
            <nav aria-label={copy.nav.externalLabel} className="hidden sm:block">
              <ExternalLinks className="flex items-center gap-1" />
            </nav>
            <ThemeToggle />
            <Button
              ref={toggleRef}
              type="button"
              variant="outline"
              size="sm"
              className="max-w-[9rem] lg:hidden"
              aria-expanded={open}
              aria-controls={navId}
              title={menuLabel}
              onClick={() => setOpen((value) => !value)}
              onKeyDown={closeOnEscape}
            >
              {open ? <XIcon data-icon="inline-start" aria-hidden="true" /> : <MenuIcon data-icon="inline-start" aria-hidden="true" />}
              <span className="truncate">{menuLabel}</span>
            </Button>
          </div>
        </div>
        {/* Inline disclosure: it pushes the page down instead of covering it, and never traps focus. */}
        <div id={navId} hidden={!open} onKeyDown={closeOnEscape} className="border-t px-4 py-3 sm:px-6 lg:hidden">
          <nav aria-label={copy.nav.primaryLabel} className="md:hidden">
            <PrimaryLinks active={active} inHeader={false} />
          </nav>
          <nav aria-label={copy.nav.sectionsLabel} className="mt-2 border-t pt-2 md:mt-0 md:border-t-0 md:pt-0">
            <RailLinks active={active} />
            <SupportLinks className="mt-2 border-t pt-2" />
          </nav>
          <ul className="mt-2 flex flex-wrap gap-1 border-t pt-2 sm:hidden">
            <li className="min-w-0">
              <a href={GITHUB_URL} target="_blank" rel="noreferrer" className={externalLinkClass}>
                {copy.nav.github}
              </a>
            </li>
          </ul>
        </div>
      </header>
      <div className="mx-auto flex w-full max-w-[90rem] flex-1 px-4 sm:px-6">
        <aside className="sticky top-13 hidden h-[calc(100dvh-3.25rem)] w-56 shrink-0 overflow-y-auto border-r py-6 pr-5 lg:block">
          <nav aria-label={copy.nav.sectionsLabel}>
            <RailLinks active={active} />
            <SupportLinks className="mt-5 border-t pt-4" />
          </nav>
        </aside>
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 py-8 outline-none lg:pl-10">
          <div className="min-w-0 max-w-6xl">{children}</div>
        </main>
      </div>
      <footer className="border-t">
        <div className="mx-auto flex w-full max-w-[90rem] flex-col gap-2 px-4 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p className="max-w-prose">{copy.footer.independence}</p>
          <p className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1">
            <span>
              {copy.footer.madeBy}{' '}
              <a href={DEPLOYEDWORK_URL} target="_blank" rel="noreferrer" className="font-medium text-foreground underline-offset-4 hover:underline">
                DeployedWork
              </a>
            </span>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">
              {copy.nav.github}
            </a>
          </p>
        </div>
      </footer>
    </div>
  )
}
