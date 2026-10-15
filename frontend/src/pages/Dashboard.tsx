import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import KhushiCard from '../components/Khushi'
import Page from '../components/Page'
import { Card, Notice } from '../components/ui'
import { api, type Doc, type Health, type ScanStatus, type Subject, type Task } from '../lib/api'
import { dueIn, formatDue } from '../lib/labels'

export default function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [files, setFiles] = useState<Doc[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.get<Health>('/health').then(setHealth),
      api.get<ScanStatus>('/organize/status').then(setStatus),
      api.get<Doc[]>('/files').then(setFiles),
      api.get<Subject[]>('/subjects').then(setSubjects),
      api.get<Task[]>('/tasks').then(setTasks),
    ]).catch((e) => setError(String(e)))
  }, [])

  const upcoming = tasks.filter((t) => t.status === 'todo' && t.due_at).slice(0, 5)
  const openCount = tasks.filter((t) => t.status === 'todo').length
  const questions = tasks.filter((t) => t.status === 'suggested').length

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
        <KhushiCard />
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
          <Link to="/tasks">
            <Card className="h-full hover:border-accent">
              <div className="text-xs font-medium tracking-wide text-zinc-500 uppercase">
                Assignments
              </div>
              <div className="mt-1 text-3xl font-semibold">{openCount}</div>
              <div className="text-sm text-zinc-500">
                to do{questions ? ` · ${questions} need your answer` : ''}
              </div>
            </Card>
          </Link>
        </div>

        {upcoming.length > 0 && (
          <Card className="p-0">
            <div className="border-b border-zinc-200 px-4 py-2 text-sm font-semibold dark:border-zinc-800">
              Coming up
            </div>
            <ul className="divide-y divide-zinc-100 text-sm dark:divide-zinc-800">
              {upcoming.map((t) => (
                <li key={t.id}>
                  <Link to="/tasks" className="flex gap-3 px-4 py-2 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
                    <span
                      className={`w-32 shrink-0 ${t.days_left !== null && t.days_left < 0 ? 'text-red-600' : 'text-zinc-500'}`}
                    >
                      {formatDue(t.due_at)} · {dueIn(t.days_left)}
                    </span>
                    <span className="truncate">{t.title}</span>
                    <span className="ml-auto truncate text-xs text-zinc-400">{t.subject}</span>
                  </Link>
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
