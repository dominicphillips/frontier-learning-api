import type { ComponentProps, MouseEvent } from 'react'
import { navigate } from '@/lib/router'
import { isAppPath } from '@/lib/routes'

type LinkProps = Omit<ComponentProps<'a'>, 'href'> & { to: string }

// In-app link. Paths outside the documentation app (such as /docs/api) keep native navigation.
export function Link({ to, onClick, target, ...props }: LinkProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event)
    if (event.defaultPrevented) return
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    if (target && target !== '_self') return
    const url = new URL(to, window.location.origin)
    if (url.origin !== window.location.origin || !isAppPath(url.pathname)) return
    event.preventDefault()
    navigate(to)
  }
  return <a href={to} target={target} onClick={handleClick} {...props} />
}
