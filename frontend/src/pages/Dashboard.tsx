import { useEffect, useState } from 'react'
import Page from '../components/Page'
import { api, type Health } from '../lib/api'

export default function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<Health>('/health').then(setHealth, (e) => setError(String(e)))
  }, [])

  return (
    <Page title="Dashboard" subtitle="Your files, deadlines and week at a glance.">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
          <div className="text-xs font-medium tracking-wide text-zinc-500 uppercase">Backend</div>
          {error && <p className="mt-2 text-sm text-red-600">Not reachable: {error}</p>}
          {!health && !error && <p className="mt-2 text-sm text-zinc-500">Connecting…</p>}
          {health && (
            <dl className="mt-2 space-y-1 text-sm">
              <div>
                <dt className="inline text-zinc-500">Status: </dt>
                <dd className="inline text-green-600">{health.status}</dd>
              </div>
              <div>
                <dt className="inline text-zinc-500">LLM: </dt>
                <dd className="inline">
                  {health.llm_provider === 'none' ? 'off (heuristics only)' : health.llm_provider}
                </dd>
              </div>
              <div>
                <dt className="inline text-zinc-500">Library: </dt>
                <dd className="inline font-mono text-xs">{health.library_root}</dd>
              </div>
              <div>
                <dt className="inline text-zinc-500">Watching: </dt>
                <dd className="inline font-mono text-xs">{health.watch_dirs.join(', ')}</dd>
              </div>
            </dl>
          )}
        </div>
      </div>
    </Page>
  )
}
