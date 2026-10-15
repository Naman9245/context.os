import { useCallback, useEffect, useState } from 'react'
import KhushiCard, { KhushiAvatar } from '../components/Khushi'
import Page from '../components/Page'
import { Button, Card, Notice, SubjectDot, inputClass } from '../components/ui'
import { api, type Subject, type Task } from '../lib/api'
import { dueIn, formatDue } from '../lib/labels'

const GROUPS: { key: string; label: string; test: (d: number | null) => boolean }[] = [
  { key: 'overdue', label: 'Overdue', test: (d) => d !== null && d < 0 },
  { key: 'today', label: 'Today', test: (d) => d === 0 },
  { key: 'tomorrow', label: 'Tomorrow', test: (d) => d === 1 },
  { key: 'week', label: 'This week', test: (d) => d !== null && d >= 2 && d <= 7 },
  { key: 'next', label: 'Next week', test: (d) => d !== null && d >= 8 && d <= 14 },
  { key: 'later', label: 'Later', test: (d) => d !== null && d > 14 },
  { key: 'none', label: 'No deadline', test: (d) => d === null },
]

export default function Tasks() {
  const [tasks, setTasks] = useState<Task[] | null>(null)
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [adding, setAdding] = useState(false)
  const [showDone, setShowDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [briefingKey, setBriefingKey] = useState(0)

  const load = useCallback(async () => {
    try {
      setTasks(await api.get<Task[]>('/tasks'))
      setBriefingKey((k) => k + 1)
    } catch (e) {
      setError(String(e))
    }
  }, [])

  useEffect(() => {
    load()
    api.get<Subject[]>('/subjects').then(setSubjects)
  }, [load])

  // Replace one task in place after an edit, then refresh Khushi's summary.
  const update = (t: Task) => {
    setTasks((prev) => prev?.map((x) => (x.id === t.id ? t : x)) ?? null)
    setBriefingKey((k) => k + 1)
  }

  const act = async (fn: () => Promise<unknown>) => {
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError(String(e))
    }
  }

  const questions = (tasks ?? []).filter((t) => t.status === 'suggested')
  const todo = (tasks ?? []).filter((t) => t.status === 'todo')
  const done = (tasks ?? [])
    .filter((t) => t.status === 'done')
    .sort((a, b) => (b.completed_at ?? '').localeCompare(a.completed_at ?? ''))

  return (
    <Page title="Assignments" subtitle="Everything you need to hand in, soonest first.">
      <div className="space-y-6">
        <KhushiCard refreshKey={briefingKey} />
        {error && <Notice tone="bad">{error}</Notice>}

        {questions.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-zinc-500">Khushi has a few questions</h2>
            {questions.map((t) => (
              <QuestionCard
                key={t.id}
                task={t}
                onAnswered={load}
                act={act}
              />
            ))}
          </section>
        )}

        <div className="flex items-center gap-3">
          <Button variant="primary" onClick={() => setAdding((a) => !a)}>
            {adding ? 'Close' : '+ Add assignment'}
          </Button>
          {tasks && (
            <span className="text-sm text-zinc-500">
              {todo.length} to do · {done.length} finished
            </span>
          )}
        </div>
        {adding && (
          <AddForm
            subjects={subjects}
            onAdded={() => {
              setAdding(false)
              load()
            }}
            act={act}
          />
        )}

        {tasks && todo.length === 0 && questions.length === 0 && (
          <Card className="py-10 text-center">
            <p className="font-medium">No assignments yet.</p>
            <p className="mt-1 text-sm text-zinc-500">
              When you scan your files, Khushi adds every assignment she finds here.
            </p>
          </Card>
        )}

        {GROUPS.map((g) => {
          const items = todo.filter((t) => g.test(t.days_left))
          if (!items.length) return null
          return (
            <section key={g.key} className="space-y-2">
              <h2
                className={`text-sm font-semibold ${g.key === 'overdue' ? 'text-red-600' : 'text-zinc-500'}`}
              >
                {g.label}
              </h2>
              {items.map((t) => (
                <TaskCard key={t.id} task={t} onChange={update} onRemoved={load} act={act} />
              ))}
            </section>
          )
        })}

        {done.length > 0 && (
          <section>
            <button
              className="text-sm text-zinc-500 hover:underline"
              onClick={() => setShowDone((s) => !s)}
            >
              {showDone ? 'Hide' : 'Show'} finished ({done.length})
            </button>
            {showDone && (
              <Card className="mt-2 p-0">
                <ul className="divide-y divide-zinc-100 text-sm dark:divide-zinc-800">
                  {done.map((t) => (
                    <li key={t.id} className="flex items-center gap-3 px-4 py-2">
                      <span className="text-emerald-600">✓</span>
                      <span className="min-w-0 flex-1 truncate text-zinc-500 line-through">
                        {t.title}
                      </span>
                      <Button
                        variant="ghost"
                        onClick={() =>
                          act(async () => {
                            await api.patch(`/tasks/${t.id}`, { status: 'todo' })
                            load()
                          })
                        }
                      >
                        Undo
                      </Button>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </section>
        )}
      </div>
    </Page>
  )
}

type Act = (fn: () => Promise<unknown>) => Promise<void>

function QuestionCard({
  task,
  onAnswered,
  act,
}: {
  task: Task
  onAnswered: () => void
  act: Act
}) {
  const [date, setDate] = useState(task.due_at?.slice(0, 10) ?? '')
  const [changing, setChanging] = useState(false)
  const answer = (body: object) =>
    act(async () => {
      await api.patch(`/tasks/${task.id}`, body)
      onAnswered()
    })
  const dismiss = () =>
    act(async () => {
      await api.del(`/tasks/${task.id}`)
      onAnswered()
    })
  const from = task.document_name ? (
    <span className="font-mono text-xs text-zinc-500">{task.document_name}</span>
  ) : null

  return (
    <div className="flex gap-3">
      <KhushiAvatar size={28} />
      <Card className="min-w-0 flex-1 py-3">
        {task.due_at && !changing ? (
          <>
            <p className="text-sm">
              I found a deadline for <strong>{task.title}</strong>: due{' '}
              <strong>{formatDue(task.due_at)}</strong> ({dueIn(task.days_left)}). Is that right?
            </p>
            <div className="mt-1">{from}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button variant="primary" onClick={() => answer({ status: 'todo' })}>
                Yes, add it
              </Button>
              <Button onClick={() => setChanging(true)}>Change date</Button>
              <Button variant="ghost" onClick={dismiss}>
                Not a deadline
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm">
              {task.due_at ? (
                <>
                  When is <strong>{task.title}</strong> due?
                </>
              ) : (
                <>
                  I couldn't find a deadline in <strong>{task.title}</strong>. When is it due?
                </>
              )}
            </p>
            <div className="mt-1">{from}</div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input
                type="date"
                className={`${inputClass} w-auto`}
                value={date}
                onChange={(e) => setDate(e.target.value)}
              />
              <Button
                variant="primary"
                disabled={!date}
                onClick={() => answer({ due_date: date })}
              >
                Save
              </Button>
              <Button onClick={() => answer({ status: 'todo', due_date: null })}>
                It has no deadline
              </Button>
              <Button variant="ghost" onClick={dismiss}>
                Not an assignment
              </Button>
            </div>
          </>
        )}
      </Card>
    </div>
  )
}

function TaskCard({
  task,
  onChange,
  onRemoved,
  act,
}: {
  task: Task
  onChange: (t: Task) => void
  onRemoved: () => void
  act: Act
}) {
  const [open, setOpen] = useState(false)
  const [writing, setWriting] = useState(false)
  const [newStep, setNewStep] = useState('')
  const [editingDate, setEditingDate] = useState(false)
  const [date, setDate] = useState(task.due_at?.slice(0, 10) ?? '')

  const doneSteps = task.steps.filter((s) => s.done).length
  const total = task.steps.length
  const allDone = total > 0 && doneSteps === total
  const late = task.days_left !== null && task.days_left < 0

  const patch = (body: object) =>
    act(async () => onChange(await api.patch<Task>(`/tasks/${task.id}`, body)))

  const finish = () =>
    act(async () => {
      await api.patch(`/tasks/${task.id}`, { status: 'done' })
      onRemoved()
    })

  const writeSteps = (replace = false) => {
    setWriting(true)
    setOpen(true)
    act(async () =>
      onChange(await api.post<Task>(`/tasks/${task.id}/steps/generate?replace=${replace}`)),
    ).finally(() => setWriting(false))
  }

  return (
    <Card className="p-0">
      <div className="flex items-start gap-3 px-4 py-3">
        <button
          title="Mark as finished"
          aria-label={`Mark ${task.title} as finished`}
          onClick={finish}
          className="mt-0.5 h-5 w-5 shrink-0 rounded-full border-2 border-zinc-300 hover:border-emerald-500 hover:bg-emerald-50 dark:border-zinc-600 dark:hover:bg-emerald-950"
        />
        <button className="min-w-0 flex-1 text-left" onClick={() => setOpen((o) => !o)}>
          <div className="flex flex-wrap items-center gap-x-2">
            <SubjectDot color={task.subject_color} />
            <span className="font-medium">{task.title}</span>
            {task.subject && <span className="text-xs text-zinc-500">{task.subject}</span>}
          </div>
          <div className={`mt-0.5 text-xs ${late ? 'text-red-600' : 'text-zinc-500'}`}>
            {task.due_at ? `${formatDue(task.due_at)} · ${dueIn(task.days_left)}` : 'No deadline'}
            {total > 0 && ` · ${doneSteps}/${total} steps`}
          </div>
          {total > 0 && (
            <div className="mt-2 h-1 overflow-hidden rounded bg-zinc-100 dark:bg-zinc-800">
              <div
                className="h-full bg-emerald-500 transition-all"
                style={{ width: `${(doneSteps / total) * 100}%` }}
              />
            </div>
          )}
        </button>
        <span className="text-zinc-400">{open ? '▾' : '▸'}</span>
      </div>

      {allDone && (
        <div className="flex items-center gap-3 border-t border-zinc-100 bg-emerald-50 px-4 py-2 text-sm dark:border-zinc-800 dark:bg-emerald-950">
          <span>All steps done. Ready to mark it finished?</span>
          <Button variant="primary" onClick={finish}>
            Finished!
          </Button>
        </div>
      )}

      {open && (
        <div className="space-y-3 border-t border-zinc-100 px-4 py-3 dark:border-zinc-800">
          {total === 0 ? (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Button onClick={() => writeSteps()} disabled={writing}>
                {writing ? 'Khushi is writing…' : 'Let Khushi write a to-do list'}
              </Button>
              <span className="text-zinc-500">or add your own steps below.</span>
            </div>
          ) : (
            <ul className="space-y-1">
              {task.steps.map((s) => (
                <li key={s.id} className="group flex items-center gap-2 text-sm">
                  <label className="flex flex-1 cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={s.done}
                      onChange={() =>
                        act(async () =>
                          onChange(
                            await api.patch<Task>(`/tasks/steps/${s.id}`, { done: !s.done }),
                          ),
                        )
                      }
                    />
                    <span className={s.done ? 'text-zinc-400 line-through' : ''}>{s.text}</span>
                  </label>
                  <button
                    className="text-xs text-zinc-400 opacity-0 group-hover:opacity-100 hover:text-red-600"
                    onClick={() =>
                      act(async () => onChange(await api.del<Task>(`/tasks/steps/${s.id}`)))
                    }
                  >
                    remove
                  </button>
                </li>
              ))}
            </ul>
          )}

          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault()
              if (!newStep.trim()) return
              act(async () => {
                onChange(await api.post<Task>(`/tasks/${task.id}/steps`, { text: newStep }))
                setNewStep('')
              })
            }}
          >
            <input
              className={inputClass}
              placeholder="Add a step…"
              value={newStep}
              onChange={(e) => setNewStep(e.target.value)}
            />
            <Button type="submit">Add</Button>
          </form>

          <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
            {editingDate ? (
              <>
                <input
                  type="date"
                  className={`${inputClass} w-auto`}
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
                <Button
                  onClick={() => {
                    patch({ due_date: date || null })
                    setEditingDate(false)
                  }}
                >
                  Save date
                </Button>
              </>
            ) : (
              <Button variant="ghost" onClick={() => setEditingDate(true)}>
                {task.due_at ? 'Change deadline' : 'Set deadline'}
              </Button>
            )}
            {total > 0 && (
              <Button variant="ghost" onClick={() => writeSteps(true)} disabled={writing}>
                {writing ? 'Rewriting…' : 'Rewrite to-do list'}
              </Button>
            )}
            {task.document_id && (
              <Button variant="ghost" onClick={() => api.post(`/files/${task.document_id}/open`)}>
                Open {task.document_name}
              </Button>
            )}
            <Button
              variant="danger"
              className="ml-auto"
              onClick={() =>
                act(async () => {
                  await api.del(`/tasks/${task.id}`)
                  onRemoved()
                })
              }
            >
              Remove
            </Button>
          </div>
        </div>
      )}
    </Card>
  )
}

function AddForm({
  subjects,
  onAdded,
  act,
}: {
  subjects: Subject[]
  onAdded: () => void
  act: Act
}) {
  const [title, setTitle] = useState('')
  const [subject, setSubject] = useState('')
  const [date, setDate] = useState('')

  return (
    <Card>
      <form
        className="grid gap-3 sm:grid-cols-[2fr_1fr_auto_auto]"
        onSubmit={(e) => {
          e.preventDefault()
          act(async () => {
            await api.post('/tasks', { title, subject: subject || null, due_date: date || null })
            onAdded()
          })
        }}
      >
        <label className="text-xs text-zinc-500">
          What do you need to do?
          <input
            className={inputClass}
            required
            value={title}
            placeholder="DBMS mini project report"
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>
        <label className="text-xs text-zinc-500">
          Subject
          <input
            className={inputClass}
            list="task-subjects"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
          <datalist id="task-subjects">
            {subjects.map((s) => (
              <option key={s.id} value={s.name} />
            ))}
          </datalist>
        </label>
        <label className="text-xs text-zinc-500">
          Due
          <input
            type="date"
            className={inputClass}
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
        <div className="flex items-end">
          <Button variant="primary" type="submit">
            Add
          </Button>
        </div>
      </form>
    </Card>
  )
}
