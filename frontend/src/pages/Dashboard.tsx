import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Page from '../components/Page'
import { Card, Notice } from '../components/ui'
import { api, type Doc, type Health, type ScanStatus, type Subject } from '../lib/api'
import { formatDue } from '../lib/labels'

export default function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [files, setFiles] = useState<Doc[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [plan, setPlan] = useState<Doc[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.get<Health>('/health').then(setHealth),
      api.get<ScanStatus>('/organize/status').then(setStatus),
      api.get<Doc[]>('/files').then(setFiles),
      api.get<Subject[]>('/subjects').then(setSubjects),
      api.get<Doc[]>('/organize/plan').then(setPlan),
    ]).catch((e) => setError(String(e)))
  }, [])

  // Deadlines found in files, soonest first, until the Tasks page exists (Phase 3).
  const deadlines = [...plan, ...files]
    .flatMap((d) => d.deadlines.map((dl) => ({ ...dl, doc: d })))
    .filter((d) => d.status !== 'done' && d.due_at)
    .sort((a, b) => a.due_at!.localeCompare(b.due_at!))
    .slice(0, 5)

  if (error) {
    return (
      <Page title="Dashboard">
        <Notice tone="bad">
          Can't reach the ContextOS backend. Start it with{' '}
          <code className="font-mono">contextos serve</code>. ({error})
        </Notice>
      </Page>
    )
  }

  return (
    <Page title="Dashboard" subtitle="Your files, deadlines and week at a glance.">
      <div className="space-y-4">
        {subjects.length === 0 && health && (
          <Notice tone="info">
            Start by adding your subjects in{' '}
            <Link to="/settings" className="text-accent font-medium hover:underline">
              Settings
            </Link>
            . ContextOS uses them to sort your files.
          </Notice>
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          <Link to="/organize">
            <Card className="h-full hover:border-accent">
              <div className="text-xs font-medium tracking-wide text-zinc-500 uppercase">
                To organise
              </div>
              <div className="mt-1 text-3xl font-semibold">{status?.pending ?? '–'}</div>
              <div className="text-sm text-zinc-500">
                {status?.running ? 'scanning now…' : 'new files waiting'}
              </div>
            </Card>
          </Link>
          <Link to="/files">
            <Card className="h-full hover:border-accent">
              <div className="text-xs font-medium tracking-wide text-zinc-500 uppercase">
                Library
              </div>
              <div className="mt-1 text-3xl font-semibold">{files.length}</div>
              <div className="text-sm text-zinc-500">
                files across {new Set(files.map((f) => f.subject_id)).size} subjects
              </div>
            </Card>
          </Link>
          <Card className="h-full">
            <div className="text-xs font-medium tracking-wide text-zinc-500 uppercase">
              Deadlines found
            </div>
            <div className="mt-1 text-3xl font-semibold">{deadlines.length}</div>
            <div className="text-sm text-zinc-500">upcoming, from your files</div>
          </Card>
        </div>

        {deadlines.length > 0 && (
          <Card className="p-0">
            <div className="border-b border-zinc-200 px-4 py-2 text-sm font-semibold dark:border-zinc-800">
              Coming up
            </div>
            <ul className="divide-y divide-zinc-100 text-sm dark:divide-zinc-800">
              {deadlines.map((d) => (
                <li key={d.id} className="flex gap-3 px-4 py-2">
                  <span className="w-28 shrink-0 text-zinc-500">{formatDue(d.due_at)}</span>
                  <span className="truncate">{d.title}</span>
                  <span className="ml-auto truncate text-xs text-zinc-400">{d.doc.subject}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        {health && (
          <p className="text-xs text-zinc-500">
            {health.watching ? 'Watching' : 'Not watching'}{' '}
            <span className="font-mono">{health.watch_dirs.join(', ')}</span> ·{' '}
            {health.llm_provider === 'none' ? 'AI off' : `AI: ${health.llm_model}`} · OCR{' '}
            {health.ocr_available ? 'on' : 'not installed'}
          </p>
        )}
      </div>
    </Page>
  )
}
