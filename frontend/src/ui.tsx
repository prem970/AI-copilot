import { Component, type ReactNode } from 'react'
import type { Citation } from './api'

export function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null
  return <p className='notice error' role='alert'>{error instanceof Error ? error.message : 'Something went wrong. Try again.'}</p>
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className='empty'>{children}</div>
}
export function Status({ value }: { value: string }) {
  return <span className={'status status-' + value}>{value.replaceAll('_', ' ')}</span>
}
export function Sources({ citations }: { citations: Citation[] }) {
  return <div className='sources'>{citations.map(c => <details key={c.id}>
    <summary><a href={c.url + (c.page ? '#page=' + c.page : '')} target='_blank' rel='noreferrer'>{c.filename}{c.page ? ` · page ${c.page}` : ''}</a></summary>
    <pre>{c.excerpt}</pre>
  </details>)}</div>
}
export function dateLabel(value: string | null) {
  return value ? new Date(value.slice(0, 10) + 'T00:00:00').toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : 'Date not recorded'
}

export class ErrorBoundary extends Component<{ children: ReactNode; fallback?: ReactNode }, { hasError: boolean }> {
  state = { hasError: false }
  static getDerivedStateFromError() { return { hasError: true } }
  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? <Empty>This section encountered an issue and could not be displayed.</Empty>
    }
    return this.props.children
  }
}
