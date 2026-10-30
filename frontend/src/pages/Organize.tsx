import { useCallback, useEffect, useRef, useState } from 'react'
import Page from '../components/Page'
import { Badge, Button, Card, Notice, SubjectDot, inputClass } from '../components/ui'
import {
  api,
  type Batch,
  type Doc,
  type DocType,
  type Health,
  type MoveResult,
  type ScanStatus,
  type Subject,
} from '../lib/api'
import { DOC_TYPES, formatDue, timeAgo, typeLabel } from '../lib/labels'

export default function Organize() {
  const [status, setStatus] = useState<ScanStatus | null>(null)
  const [plan, setPlan] = useState<Doc[]>([])
  const [skipped, setSkipped] = useState<Doc[] | null>(null)
  const [batches, setBatches] = useState<Batch[]>([])
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [editing, setEditing] = useState<number | null>(null)
  const [message, setMessage] = useState<{ text: string; batch?: string; tone?: 'bad' } | null>(
    null,
  )
  const [busy, setBusy] = useState(false)
  const wasRunning = useRef(false)

  const reload = useCallback(async () => {
    const [p, b, s] = await Promise.all([
      api.get<Doc[]>('/organize/plan'),
      api.get<Batch[]>('/organize/batches'),
      api.get<Subject[]>('/subjects'),
    ])
    setPlan(p)
    setBatches(b)
    setSubjects(s)
    setSelected((prev) => new Set([...prev].filter((id) => p.some((d) => d.id === id))))
  }, [])

  useEffect(() => {
    reload()
    api.get<Health>('/health').then(setHealth)
  }, [reload])

  // Poll fast while a scan runs, slowly otherwise (the folder watcher can start one).
  useEffect(() => {
    let alive = true
    let timer: number
    const tick = async () => {
      try {
        const s = await api.get<ScanStatus>('/organize/status')
        if (!alive) return
        setStatus(s)
        if (wasRunning.current && !s.running) reload()
        wasRunning.current = s.running
        timer = window.setTimeout(tick, s.running ? 800 : 5000)
      } catch {
        timer = window.setTimeout(tick, 5000)
      }
    }
    tick()
    return () => {
      alive = false
      window.clearTimeout(timer)
    }
  }, [reload])

  const scan = async () => {
    setMessage(null)
    const s = await api.post<ScanStatus>('/organize/scan')
    setStatus(s)
    wasRunning.current = true
  }

  const move = async (ids: number[]) => {
    setBusy(true)
    try {
      const r = await api.post<MoveResult>('/organize/apply', { document_ids: ids })
      const failed = Object.keys(r.failed).length
      setMessage({
        text:
          `Moved ${r.moved.length} file${r.moved.length === 1 ? '' : 's'} into your library.` +
          (failed ? ` ${failed} could not be moved.` : ''),
        batch: r.moved.length ? r.batch_id : undefined,
        tone: failed ? 'bad' : undefined,
      })
      setSelected(new Set())
      await reload()
    } finally {
      setBusy(false)
    }
  }

  const undo = async (batchId: string) => {
    setBusy(true)
    try {
      const r = await api.post<MoveResult>(`/organize/undo/${batchId}`)
      setMessage({ text: `Put ${r.moved.length} file${r.moved.length === 1 ? '' : 's'} back.` })
      await reload()
    } finally {
      setBusy(false)
    }
  }

  const skip = async (ids: number[]) => {
    await api.post('/organize/skip', { document_ids: ids })
    setSelected(new Set())
    if (skipped) setSkipped(await api.get<Doc[]>('/organize/plan?status=skipped'))
    await reload()
  }

  const unskip = async (id: number) => {
    await api.post('/organize/unskip', { document_ids: [id] })
    setSkipped(await api.get<Doc[]>('/organize/plan?status=skipped'))
    await reload()
  }

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const allSelected = plan.length > 0 && selected.size === plan.length
  const running = status?.running ?? false
  const unreadable = plan.filter((d) => d.extraction === 'ocr_unavailable').length

  return (
    <Page
      title="Organize"
      subtitle="ContextOS proposes a folder for every new file. Nothing moves until you approve it."
    >
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" onClick={scan} disabled={running}>
            {running ? 'Scanning…' : 'Scan now'}
          </Button>
          {health && (
            <span className="text-xs text-stone-500">
              {health.watching ? 'Watching' : 'Scanning'}{' '}
              <span className="font-mono">{health.watch_dirs.join(', ')}</span>
              {' · '}
              {health.llm_provider === 'none'
                ? 'rules only (no AI)'
                : `AI: ${health.llm_model ?? health.llm_provider}`}
            </span>
          )}
        </div>

        {running && status && <ScanProgress status={status} />}
        {!running && status?.report && status.finished_at && (
          <ScanSummary status={status} />
        )}
        {status?.error && <Notice tone="bad">The last scan failed: {status.error}</Notice>}

        {message && (
          <Notice tone={message.tone === 'bad' ? 'bad' : 'info'}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>{message.text}</span>
              {message.batch && (
                <Button variant="ghost" onClick={() => undo(message.batch!)} disabled={busy}>
                  Undo
                </Button>
              )}
            </div>
          </Notice>
        )}

        {health && !health.ocr_available && unreadable > 0 && (
          <Notice>
            {unreadable} scanned PDF{unreadable === 1 ? '' : 's'} could not be read, so{' '}
            {unreadable === 1 ? 'it was' : 'they were'} sorted by file name only. Install OCR and
            scan again: <code className="font-mono">sudo apt install tesseract-ocr</code>
          </Notice>
        )}

        {plan.length === 0 && !running ? (
          <Card className="py-10 text-center">
            <p className="font-medium">Nothing waiting to be organised.</p>
            <p className="mt-1 text-sm text-stone-500">
              New files in your watched folders show up here automatically.
            </p>
          </Card>
        ) : (
          plan.length > 0 && (
            <Card pad={false}>
              <div className="flex flex-wrap items-center gap-3 border-b border-stone-200 px-4 py-3 dark:border-stone-800">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={allSelected}
                    onChange={() =>
                      setSelected(allSelected ? new Set() : new Set(plan.map((d) => d.id)))
                    }
                  />
                  {plan.length} file{plan.length === 1 ? '' : 's'} to organise
                </label>
                <div className="ml-auto flex gap-2">
                  <Button
                    variant="ghost"
                    disabled={selected.size === 0 || busy}
                    onClick={() => skip([...selected])}
                  >
                    Leave where they are
                  </Button>
                  <Button
                    variant="primary"
                    disabled={selected.size === 0 || busy}
                    onClick={() => move([...selected])}
                  >
                    Move {selected.size || ''} to library
                  </Button>
                </div>
              </div>
              <ul className="divide-y divide-stone-200 dark:divide-stone-800">
                {plan.map((doc) => (
                  <PlanRow
                    key={doc.id}
                    doc={doc}
                    selected={selected.has(doc.id)}
                    onToggle={() => toggle(doc.id)}
                    editing={editing === doc.id}
                    onEdit={() => setEditing(editing === doc.id ? null : doc.id)}
                    subjects={subjects}
                    onSaved={(updated) => {
                      setPlan((p) => p.map((d) => (d.id === updated.id ? updated : d)))
                      setEditing(null)
                      api.get<Subject[]>('/subjects').then(setSubjects)
                    }}
                  />
                ))}
              </ul>
            </Card>
          )
        )}

        {batches.length > 0 && (
          <section>
            <h2 className="mb-2 text-sm font-semibold text-stone-500">Recent moves</h2>
            <Card pad={false}>
              <ul className="divide-y divide-stone-200 text-sm dark:divide-stone-800">
                {batches.map((b) => (
                  <li key={b.batch_id} className="flex items-center gap-3 px-4 py-2">
                    <span>
                      {b.count} file{b.count === 1 ? '' : 's'}
                    </span>
                    <span className="text-stone-500">{timeAgo(b.moved_at)}</span>
                    <span className="ml-auto">
                      {b.undone ? (
                        <span className="text-xs text-stone-500">undone</span>
                      ) : (
                        <Button variant="ghost" onClick={() => undo(b.batch_id)} disabled={busy}>
                          Undo
                        </Button>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        )}

        <section>
          <button
            className="text-sm text-stone-500 hover:underline"
            onClick={async () =>
              setSkipped(skipped ? null : await api.get<Doc[]>('/organize/plan?status=skipped'))
            }
          >
            {skipped ? 'Hide' : 'Show'} files you chose to leave where they are
          </button>
          {skipped && (
            <Card pad={false} className="mt-2">
              {skipped.length === 0 ? (
                <p className="px-4 py-3 text-sm text-stone-500">None.</p>
              ) : (
                <ul className="divide-y divide-stone-200 text-sm dark:divide-stone-800">
                  {skipped.map((d) => (
                    <li key={d.id} className="flex items-center gap-3 px-4 py-2">
                      <span className="truncate">{d.filename}</span>
                      <Button variant="ghost" className="ml-auto" onClick={() => unskip(d.id)}>
                        Bring back
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          )}
        </section>
      </div>
    </Page>
  )
}

function ScanProgress({ status }: { status: ScanStatus }) {
  const pct = status.total ? Math.round((status.done / status.total) * 100) : 0
  return (
    <Card>
      <div className="flex justify-between text-sm">
        <span>
          {status.total
            ? `Reading ${Math.min(status.done + 1, status.total)} of ${status.total}`
            : 'Looking for new files…'}
        </span>
        <span className="truncate pl-4 font-mono text-xs text-stone-500">{status.current}</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded bg-stone-100 dark:bg-stone-800">
        <div className="bg-accent h-full transition-all" style={{ width: `${pct}%` }} />
      </div>
    </Card>
  )
}

function ScanSummary({ status }: { status: ScanStatus }) {
  const r = status.report!
  const parts = [
    `${r.new} new file${r.new === 1 ? '' : 's'}`,
    r.duplicates.length && `${r.duplicates.length} duplicate${r.duplicates.length === 1 ? '' : 's'} skipped`,
    r.deadlines && `${r.deadlines} deadline${r.deadlines === 1 ? '' : 's'} found`,
    r.used_llm && `AI helped with ${r.used_llm}`,
    r.errors.length && `${r.errors.length} could not be read`,
  ].filter(Boolean)
  return (
    <p className="text-sm text-stone-500">
      Last scan {status.finished_at ? timeAgo(status.finished_at) : ''}: {parts.join(' · ')}.
      {r.llm_errors > 0 && ` The AI was unavailable for ${r.llm_errors}, so rules were used.`}
    </p>
  )
}

function PlanRow({
  doc,
  selected,
  onToggle,
  editing,
  onEdit,
  subjects,
  onSaved,
}: {
  doc: Doc
  selected: boolean
  onToggle: () => void
  editing: boolean
  onEdit: () => void
  subjects: Subject[]
  onSaved: (d: Doc) => void
}) {
  const parts = (doc.destination ?? '').split('/')
  const file = parts.pop()
  const sure = doc.classified_by === 'you' || doc.confidence >= 0.6

  return (
    <li className={selected ? 'bg-accent-soft/40 dark:bg-stone-800/40' : ''}>
      <div className="flex gap-3 px-4 py-3">
        <input type="checkbox" className="mt-1" checked={selected} onChange={onToggle} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <SubjectDot color={doc.subject_color} />
            <span className="font-medium">{doc.title ?? doc.filename}</span>
            <Badge>{typeLabel(doc.doc_type)}</Badge>
            {doc.classified_by === 'you' ? (
              <Badge tone="good">set by you</Badge>
            ) : sure ? (
              <Badge tone="good" title={`decided by ${doc.classified_by}`}>
                {doc.classified_by === 'rules' ? 'sure' : 'AI: sure'}
              </Badge>
            ) : (
              <Badge tone="warn" title="Low confidence - please check">
                check this
              </Badge>
            )}
            {doc.extraction === 'ocr_unavailable' && (
              <Badge tone="warn" title="Scanned PDF - install Tesseract to read it">
                scanned, not read
              </Badge>
            )}
            {doc.error && (
              <Badge tone="bad" title={doc.error}>
                problem
              </Badge>
            )}
            {doc.deadlines.map((d) => (
              <Badge key={d.id} tone="accent" title={d.title}>
                due {formatDue(d.due_at)}
              </Badge>
            ))}
          </div>
          <div className="mt-1 text-xs text-stone-500">
            <button
              className="truncate font-mono hover:underline"
              title="Open this file"
              onClick={() => api.post(`/files/${doc.id}/open`)}
            >
              {doc.filename}
            </button>
            <span className="px-1.5">→</span>
            <span className="break-words">
              {parts.map((p, i) => (
                <span key={i}>
                  {p}
                  <span className="px-1 text-stone-400">/</span>
                </span>
              ))}
              <span className="text-stone-800 dark:text-stone-200">{file}</span>
            </span>
          </div>
        </div>
        <Button variant="ghost" onClick={onEdit} className="self-start">
          {editing ? 'Close' : 'Edit'}
        </Button>
      </div>
      {editing && <EditForm doc={doc} subjects={subjects} onSaved={onSaved} />}
    </li>
  )
}

function EditForm({
  doc,
  subjects,
  onSaved,
}: {
  doc: Doc
  subjects: Subject[]
  onSaved: (d: Doc) => void
}) {
  const [subject, setSubject] = useState(doc.subject ?? '')
  const [docType, setDocType] = useState<DocType>(doc.doc_type)
  const [title, setTitle] = useState(doc.title ?? '')
  const [semester, setSemester] = useState(doc.semester ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      onSaved(
        await api.patch<Doc>(`/organize/documents/${doc.id}`, {
          subject,
          doc_type: docType,
          title,
          semester,
        }),
      )
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-3 border-t border-stone-200 bg-stone-100 px-4 py-3 sm:grid-cols-2 lg:grid-cols-4 dark:border-stone-800 dark:bg-stone-950">
      <label className="text-xs text-stone-500">
        Subject
        <input
          className={inputClass}
          list={`subjects-${doc.id}`}
          value={subject}
          placeholder="e.g. DBMS"
          onChange={(e) => setSubject(e.target.value)}
        />
        <datalist id={`subjects-${doc.id}`}>
          {subjects.map((s) => (
            <option key={s.id} value={s.name} />
          ))}
        </datalist>
      </label>
      <label className="text-xs text-stone-500">
        Type
        <select
          className={inputClass}
          value={docType}
          onChange={(e) => setDocType(e.target.value as DocType)}
        >
          {DOC_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-stone-500">
        Title
        <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="text-xs text-stone-500">
        Semester
        <input
          className={inputClass}
          value={semester}
          placeholder="e.g. Sem 5"
          onChange={(e) => setSemester(e.target.value)}
        />
      </label>
      <div className="flex items-center gap-2 sm:col-span-2 lg:col-span-4">
        <Button variant="primary" onClick={save} disabled={saving}>
          Save
        </Button>
        <span className="text-xs text-stone-500">
          A new subject name creates that subject.
        </span>
        {error && <span className="text-xs text-red-600">{error}</span>}
      </div>
    </div>
  )
}
