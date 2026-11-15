import { Fragment } from 'react'
import { Select, SelectContent, SelectItem, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { copy } from '@/copy'
import { PROVIDER_IDS, SCOPES, isProviderId, parseScope, type ProviderId, type Scope } from '@/lib/api'

export const fieldLabelClass = 'block text-sm font-medium break-words'

interface RouteSelectProps {
  id: string
  value: Scope
  onChange: (scope: Scope) => void
  /** Literal route for each scope, such as /v1/resources or /v1/providers/claude/resources. */
  template: (scope: Scope) => string
}

// Chooses between the aggregate route and one provider's native route; options are the literal paths.
export function RouteSelect({ id, value, onChange, template }: RouteSelectProps) {
  const label = (scope: Scope) => `GET ${template(scope)}`
  return (
    <div className="min-w-0 space-y-1.5">
      <label htmlFor={id} className={fieldLabelClass}>
        {copy.labels.route}
      </label>
      <Select value={value} onValueChange={(next) => onChange(parseScope(next))}>
        <SelectTrigger id={id} title={label(value)} className="w-full font-mono text-[13px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {SCOPES.map((scope) => (
            <Fragment key={scope}>
              <SelectItem value={scope} className="font-mono text-[13px]">
                {label(scope)}
              </SelectItem>
              {scope === 'all' ? <SelectSeparator /> : null}
            </Fragment>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

const ANY_PROVIDER = '__any__'

interface ProviderFilterProps {
  id: string
  value: ProviderId | ''
  onChange: (provider: ProviderId | '') => void
}

// The aggregate routes' provider query parameter; provider routes fix the provider in the path instead.
export function ProviderFilter({ id, value, onChange }: ProviderFilterProps) {
  const current = value || ANY_PROVIDER
  return (
    <div className="min-w-0 space-y-1.5">
      <label htmlFor={id} className={fieldLabelClass}>
        {copy.labels.provider}
      </label>
      <Select value={current} onValueChange={(next) => onChange(isProviderId(next) ? next : '')}>
        <SelectTrigger id={id} title={value || copy.labels.providerAny} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY_PROVIDER}>{copy.labels.providerAny}</SelectItem>
          {PROVIDER_IDS.map((provider) => (
            <SelectItem key={provider} value={provider} className="font-mono text-[13px]">
              {provider}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
