import { useId, type FormEvent, type ReactNode } from 'react'
import { LoaderCircleIcon, PlayIcon, RotateCcwIcon } from 'lucide-react'
import { CodeBlock } from '@/components/code-block'
import { CopyButton } from '@/components/copy-button'
import { Button } from '@/components/ui/button'
import { copy, fmt } from '@/copy'
import type { RequestState } from '@/hooks/use-request'
import { API_BASE, curlFor } from '@/lib/api'
import { prettyJson } from '@/lib/format'
import { statusNote } from '@/lib/status-note'
import { cn } from '@/lib/utils'

interface RequestPanelProps {
  /** Draft request: the path the Run action sends next. */
  path: string
  state: RequestState
  onRun?: () => void
  showRun?: boolean
  /** Request parameters, rendered inside the request form so Enter runs the request. */
  children?: ReactNode
}

function GetChip() {
  return <span className="shrink-0 rounded-sm bg-signal-soft px-1.5 py-0.5 font-mono text-[11px] text-signal-deep">GET</span>
}

// Request on the left, result on the right. The result always describes its own completed request
// (path, status, timing and body come from the same state), so editing the draft never relabels it.
export function RequestPanel({ path, state, onRun, showRun = true, children }: RequestPanelProps) {
  const responseId = useId()
  const url = `${API_BASE}${path}`
  const loading = state.phase === 'loading'
  const sameDraft = state.phase !== 'idle' && state.path === path
  const buttonLabel = loading
    ? copy.actions.running
    : state.phase === 'failed' && sameDraft
      ? copy.actions.retry
      : state.phase === 'done' && sameDraft
        ? copy.actions.runAgain
        : copy.actions.run
  const ButtonIcon = loading ? LoaderCircleIcon : state.phase !== 'idle' && sameDraft ? RotateCcwIcon : PlayIcon
  const note = state.phase === 'done' ? statusNote(state.result.status) : null
  const statusLine =
    state.phase === 'done'
      ? fmt(copy.request.statusLine, {
          status: state.result.statusText ? `${state.result.status} ${state.result.statusText}` : state.result.status,
          ms: state.result.ms,
        })
      : ''

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!loading) onRun?.()
  }

  return (
    <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <form onSubmit={submit} className="panel-raised flex min-w-0 flex-col">
        <div className="flex min-h-12 flex-wrap items-center gap-2 border-b px-3 py-2">
          <GetChip />
          <span className="min-w-0 truncate text-xs font-medium text-muted-foreground" title={copy.labels.requestUrl}>
            {copy.labels.requestUrl}
          </span>
          <div className="ml-auto flex max-w-full min-w-0 flex-wrap items-center justify-end gap-2">
            <CopyButton text={url} />
            {showRun ? (
              <Button type="submit" size="sm" aria-disabled={loading} title={buttonLabel} className="max-w-[11rem]">
                <ButtonIcon data-icon="inline-start" aria-hidden="true" className={loading ? 'motion-safe:animate-spin' : undefined} />
                <span className="truncate">{buttonLabel}</span>
              </Button>
            ) : null}
          </div>
        </div>
        <p className="px-3 py-2.5 font-mono text-[13px] leading-6 break-all">{url}</p>
        {children ? <div className="border-t px-3 py-3">{children}</div> : null}
        <div className="mt-auto border-t">
          <CodeBlock label={copy.labels.curl} language="bash" code={curlFor(path)} className="rounded-none rounded-b-[11px] border-0" />
        </div>
      </form>

      <section aria-labelledby={responseId} className="panel-raised flex min-w-0 flex-col">
        <div className="flex min-h-12 flex-wrap items-center gap-x-3 gap-y-1 border-b px-3 py-2">
          <h3 id={responseId} className="text-xs font-medium text-muted-foreground">
            {copy.labels.response}
          </h3>
          {state.phase !== 'idle' ? (
            <span className="min-w-0 font-mono text-[11px] leading-5 text-muted-foreground break-all">
              <span className="text-signal-deep">GET</span> {state.path}
            </span>
          ) : null}
          {state.phase === 'done' ? (
            <span
              title={statusLine}
              className={cn(
                'ml-auto max-w-full truncate rounded-sm border px-1.5 py-0.5 font-mono text-[11px] font-medium',
                state.result.ok ? 'border-edge text-foreground' : 'border-destructive text-destructive',
              )}
            >
              {statusLine}
            </span>
          ) : null}
        </div>
        <div role="status" aria-live="polite" className={cn('px-3 py-2.5 text-sm', state.phase === 'done' && !note && 'sr-only')}>
          {state.phase === 'idle' ? <p className="text-muted-foreground">{copy.request.idle}</p> : null}
          {state.phase === 'loading' ? (
            <p className="flex items-center gap-2 text-muted-foreground">
              <LoaderCircleIcon className="size-4 shrink-0 motion-safe:animate-spin" aria-hidden="true" />
              {copy.request.loading}
            </p>
          ) : null}
          {state.phase === 'failed' ? (
            <div className="space-y-1">
              <p className="text-destructive">{copy.request.failed}</p>
              <pre className="overflow-x-auto font-mono text-xs text-muted-foreground">{state.message}</pre>
            </div>
          ) : null}
          {state.phase === 'done' ? (
            <p className={note ? 'text-muted-foreground' : undefined}>
              {statusLine}
              {note ? ` ${note}` : null}
            </p>
          ) : null}
        </div>
        {state.phase === 'done' ? (
          <CodeBlock
            label={copy.labels.response}
            language={state.result.isJson ? 'json' : 'text'}
            code={state.result.isJson ? prettyJson(state.result.json) : state.result.text || copy.request.emptyBody}
            tall
            className="mt-auto rounded-none rounded-b-[11px] border-0"
          />
        ) : (
          <div className="min-h-[9rem] flex-1" aria-hidden="true" />
        )}
      </section>
    </div>
  )
}
