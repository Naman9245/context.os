import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { KhushiAvatar } from '../components/Khushi'
import { ArrowCircle, Card, Notice } from '../components/ui'
import {
  api,
  type Briefing,
  type Doc,
  type Health,
  type ScanStatus,
  type Subject,
  type Task,
} from '../lib/api'
import { dueIn, LINE_TONE, longDate, startOfWeek } from '../lib/labels'

// The day as a stack of coloured bands, like the tab dividers in a binder: each band
// tucks under the next one, and the lower ones open the page they describe.
const BAND = {
  coral: 'bg-coral text-stone-900',
  paper:
    'bg-stone-50 text-stone-900 ring-1 ring-stone-200 dark:bg-stone-900 dark:text-stone-100 dark:ring-stone-800',
  sun: 'bg-sun text-stone-900',
  pine: 'bg-pine text-stone-50',
}

function Band({
  tone,
  step,
  last = false,
  to,
  children,
}: {
  tone: keyof typeof BAND
  step: number
  last?: boolean
  to?: string
  children: ReactNode
}) {
  const className = `relative block rounded-[32px] px-6 pt-6 motion-safe:animate-rise ${
    last ? 'pb-6' : 'pb-14'
  } ${step ? '-mt-8' : ''} ${BAND[tone]}`
  const style = { zIndex: step, animationDelay: `${step * 80}ms` }
  if (to) {
    return (
      <Link to={to} className={`group ${className} transition-transform hover:-translate-y-1`} style={style}>
        {children}
      </Link>
    )
  }
  return (
    <section className={className} style={style}>
      {children}
    </section>
  )
}

function BandStat({
  value,
  label,
  note,
  light = false,
}: {
  value: ReactNode
  label: string
  note: string
  light?: boolean
}) {
  return (
    <div className="flex items-center gap-4">
      <span className="font-display text-5xl leading-none font-extrabold tabular-nums">{value}</span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-xl font-bold">{label}</span>
        <span className="block text-sm font-medium">{note}</span>
      </span>
      <ArrowCircle light={light} />
    </div>
  )
}

function Tile({ tone, value, label }: { tone: string; value: number; label: string }) {
  return (
    <div className={`rounded-[20px] px-3 py-3 text-stone-900 ${tone}`}>
      <div className="font-display text-3xl leading-none font-extrabold tabular-nums">{value}</div>
      <div className="mt-1.5 text-xs font-semibold">{label}</div>
    </div>
  )
}

function DateChip({ iso, late }: { iso: string; late: boolean }) {
  const d = new Date(iso)
  return (
    <span
      className={`flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-[16px] leading-none text-stone-900 ${
        late ? 'bg-coral' : 'bg-sun'
      }`}
    >
      <span className="font-display text-lg font-extrabold">{d.getDate()}</span>
      <span className="mt-0.5 text-[10px] font-bold uppercase">
        {d.toLocaleDateString(undefined, { month: 'short' })}
      </span>
    </span>
  )
}

export default function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null)
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [files, setFiles] = useState<Doc[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [briefing, setBriefing] = useState<Briefing | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.get<Health>('/health').then(setHealth),
      api.get<ScanStatus>('/organize/status').then(setStatus),
      api.get<Doc[]>('/files').then(setFiles),
      api.get<Subject[]>('/subjects').then(setSubjects),
      api.get<Task[]>('/tasks').then(setTasks),
      api.get<Briefing>('/khushi/briefing').then(setBriefing),
    ]).catch((e) => setError(String(e)))
  }, [])

  const upcoming = tasks.filter((t) => t.status === 'todo' && t.due_at).slice(0, 5)
  const openCount = tasks.filter((t) => t.status === 'todo').length
  const questions = tasks.filter((t) => t.status === 'suggested').length
  const monday = startOfWeek()
  const doneThisWeek = tasks.filter(
    (t) => t.status === 'done' && t.completed_at && new Date(t.completed_at) >= monday,
  ).length
  const subjectCount = new Set(files.filter((f) => f.subject_id !== null).map((f) => f.subject_id))
    .size

  if (error) {
    return (
      <section className="mx-auto max-w-6xl">
        <h1 className="font-display text-4xl font-extrabold tracking-tight">Dashboard</h1>
        <div className="mt-6">
          <Notice tone="bad">
            Can't reach the ContextOS backend. Start it with{' '}
            <code className="font-mono">contextos serve</code>. ({error})
          </Notice>
        </div>
      </section>
    )
  }

  return (
    <section className="mx-auto max-w-6xl">
      <h1 className="sr-only">Dashboard</h1>
      {subjects.length === 0 && health && (
        <div className="mb-6">
          <Notice tone="info">
            Add your subjects in{' '}
            <Link to="/settings" className="font-semibold text-accent hover:underline">
              Settings
            </Link>{' '}
            first: ContextOS uses them to sort your files.
          </Notice>
        </div>
      )}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <div>
          <Band tone="coral" step={0}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold">{longDate(new Date())}</p>
                <h2 className="mt-2 font-display text-4xl leading-[0.95] font-extrabold tracking-tight sm:text-5xl">
                  {briefing?.greeting ?? 'Hello!'}
                </h2>
              </div>
              <KhushiAvatar size={52} />
            </div>
          </Band>
          <Band tone="paper" step={1}>
            <p className="text-xs font-bold tracking-[0.14em] text-stone-500 uppercase">
              Khushi says
            </p>
            <ul className="mt-3 space-y-2 leading-snug">
              {(briefing?.lines ?? []).map((line, i) => (
                <li key={i} className={`flex gap-2.5 ${LINE_TONE[line.tone]}`}>
                  <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
                  {line.link ? (
                    <Link to={line.link} className="font-semibold underline-offset-2 hover:underline">
                      {line.text}
                    </Link>
                  ) : (
                    <span>{line.text}</span>
                  )}
                </li>
              ))}
            </ul>
          </Band>
          <Band tone="sun" step={2} to="/organize">
            <BandStat
              value={status?.pending ?? '–'}
              label="To organise"
              note={status?.running ? 'Scanning now…' : 'new files waiting'}
            />
          </Band>
          <Band tone="pine" step={3} to="/files" last>
            <BandStat
              value={files.length}
              label="Library"
              note={`files across ${subjectCount} ${subjectCount === 1 ? 'subject' : 'subjects'}`}
              light
            />
          </Band>
        </div>

        <div className="space-y-6">
          <Card>
            <div className="flex items-center justify-between gap-3">
              <h2 className="font-display text-2xl font-extrabold tracking-tight">Assignments</h2>
              <Link to="/tasks" aria-label="Open assignments" className="group rounded-full">
                <ArrowCircle />
              </Link>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <Tile tone="bg-butter" value={openCount} label="To do" />
              <Tile tone="bg-blush" value={questions} label="Need your answer" />
              <Tile tone="bg-mint" value={doneThisWeek} label="Done this week" />
            </div>
          </Card>

          <Card pad={false} className="pb-3">
            <h2 className="px-5 pt-5 pb-3 font-display text-2xl font-extrabold tracking-tight">
              Coming up
            </h2>
            {upcoming.length > 0 ? (
              <ul className="space-y-2 px-3">
                {upcoming.map((t) => {
                  const late = t.days_left !== null && t.days_left < 0
                  return (
                    <li key={t.id}>
                      <Link
                        to="/tasks"
                        className="flex items-center gap-3 rounded-[20px] bg-stone-100 px-3 py-2.5 transition hover:bg-stone-200/70 dark:bg-stone-800/60 dark:hover:bg-stone-800"
                      >
                        <DateChip iso={t.due_at ?? ''} late={late} />
                        <span className="min-w-0 flex-1">
                          <span className="line-clamp-2 leading-snug font-semibold">{t.title}</span>
                          <span className="block truncate text-xs text-stone-500">
                            {t.subject ?? 'No subject'}
                          </span>
                        </span>
                        <span
                          className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-bold ${
                            late
                              ? 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300'
                              : 'bg-stone-50 text-stone-700 dark:bg-stone-900 dark:text-stone-300'
                          }`}
                        >
                          {dueIn(t.days_left)}
                        </span>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            ) : (
              <p className="px-5 pb-2 text-sm text-stone-500">
                Nothing due yet. Deadlines Khushi finds in your files show up here.
              </p>
            )}
          </Card>
        </div>
      </div>

      {health && (
        <ul className="mt-8 flex flex-wrap gap-2 text-xs font-semibold text-stone-600 dark:text-stone-300">
          <li className="rounded-full bg-stone-200/70 px-3 py-1.5 dark:bg-stone-800">
            {health.watching ? 'Watching' : 'Not watching'} {health.watch_dirs.join(', ')}
          </li>
          <li className="rounded-full bg-stone-200/70 px-3 py-1.5 dark:bg-stone-800">
            {health.llm_provider === 'none' ? 'AI off' : `AI: ${health.llm_model}`}
          </li>
          <li className="rounded-full bg-stone-200/70 px-3 py-1.5 dark:bg-stone-800">
            OCR {health.ocr_available ? 'on' : 'not installed'}
          </li>
        </ul>
      )}
    </section>
  )
}
