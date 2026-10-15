import { useEffect, useState } from 'react'
import Page from '../components/Page'
import { Badge, Button, Card, Notice, SubjectDot, inputClass } from '../components/ui'
import { api, type Health, type Subject } from '../lib/api'

const EMPTY = { name: '', code: '', aliases: '', semester: '' }

export default function Settings() {
  const [subjects, setSubjects] = useState<Subject[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [form, setForm] = useState(EMPTY)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<string | null>(null)

  const load = () => api.get<Subject[]>('/subjects').then(setSubjects)

  useEffect(() => {
    load()
    api.get<Health>('/health').then(setHealth)
  }, [])

  const body = () => ({
    name: form.name,
    code: form.code || null,
    aliases: form.aliases.split(','),
    semester: form.semester || null,
  })

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    try {
      if (editingId) await api.put(`/subjects/${editingId}`, body())
      else await api.post('/subjects', body())
      setForm(EMPTY)
      setEditingId(null)
      await load()
    } catch (err) {
      setError(String(err))
    }
  }

  const edit = (s: Subject) => {
    setEditingId(s.id)
    setForm({
      name: s.name,
      code: s.code ?? '',
      aliases: s.aliases.join(', '),
      semester: s.semester ?? '',
    })
  }

  const remove = async (s: Subject) => {
    const files = s.documents ? ` Its ${s.documents} file(s) stay where they are.` : ''
    if (!window.confirm(`Remove the subject "${s.name}"?${files}`)) return
    await api.del(`/subjects/${s.id}`)
    await load()
  }

  return (
    <Page title="Settings" subtitle="Your subjects, and how ContextOS is set up.">
      <div className="space-y-6">
        <section>
          <h2 className="font-semibold">Subjects</h2>
          <p className="mb-3 text-sm text-zinc-500">
            Add the courses you are taking this semester. Include the short names and course
            codes that appear in your file names (like <em>DBMS</em> or <em>BCS403</em>) so files
            get sorted without needing the AI.
          </p>

          <Card>
            <form onSubmit={save} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_2fr_1fr_auto]">
              <label className="text-xs text-zinc-500">
                Name
                <input
                  className={inputClass}
                  required
                  value={form.name}
                  placeholder="Database Management Systems"
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </label>
              <label className="text-xs text-zinc-500">
                Course code
                <input
                  className={inputClass}
                  value={form.code}
                  placeholder="BCS403"
                  onChange={(e) => setForm({ ...form, code: e.target.value })}
                />
              </label>
              <label className="text-xs text-zinc-500">
                Other names (comma-separated)
                <input
                  className={inputClass}
                  value={form.aliases}
                  placeholder="DBMS, Databases"
                  onChange={(e) => setForm({ ...form, aliases: e.target.value })}
                />
              </label>
              <label className="text-xs text-zinc-500">
                Semester
                <input
                  className={inputClass}
                  value={form.semester}
                  placeholder="Sem 4"
                  onChange={(e) => setForm({ ...form, semester: e.target.value })}
                />
              </label>
              <div className="flex items-end gap-2">
                <Button variant="primary" type="submit">
                  {editingId ? 'Save' : 'Add'}
                </Button>
                {editingId && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setEditingId(null)
                      setForm(EMPTY)
                    }}
                  >
                    Cancel
                  </Button>
                )}
              </div>
            </form>
            {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
          </Card>

          {subjects.length > 0 && (
            <Card className="mt-3 p-0">
              <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {subjects.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm">
                    <SubjectDot color={s.color} />
                    <span className="font-medium">{s.name}</span>
                    {s.code && <Badge>{s.code}</Badge>}
                    {s.aliases.map((a) => (
                      <Badge key={a}>{a}</Badge>
                    ))}
                    {s.semester && <span className="text-zinc-500">{s.semester}</span>}
                    <span className="text-zinc-400">
                      · {s.documents} file{s.documents === 1 ? '' : 's'}
                    </span>
                    <span className="ml-auto flex gap-1">
                      <Button variant="ghost" onClick={() => edit(s)}>
                        Edit
                      </Button>
                      <Button variant="danger" onClick={() => remove(s)}>
                        Remove
                      </Button>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </section>

        {health && (
          <section>
            <h2 className="mb-3 font-semibold">Setup</h2>
            <Card>
              <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
                <dt className="text-zinc-500">AI</dt>
                <dd>
                  {health.llm_provider === 'none'
                    ? 'Off - files are sorted by rules only, nothing leaves this computer'
                    : `${health.llm_provider} · ${health.llm_model}`}
                </dd>
                <dt className="text-zinc-500">Scanned PDFs (OCR)</dt>
                <dd>
                  {health.ocr_available ? (
                    'Available'
                  ) : (
                    <>
                      Not installed - run{' '}
                      <code className="font-mono">sudo apt install tesseract-ocr</code>
                    </>
                  )}
                </dd>
                <dt className="text-zinc-500">Reminders</dt>
                <dd>
                  {health.reminder_days.length
                    ? `${health.reminder_days.join(' and ')} days before each deadline`
                    : 'Off'}
                  {!health.notifications_available && ' (desktop notifications unavailable)'}
                  <div className="mt-1 flex items-center gap-2">
                    <Button
                      onClick={async () => {
                        const r = await api.post<{ sent: boolean }>('/tasks/test-notification')
                        setTestResult(
                          r.sent ? 'Sent - check the top of your screen.' : "Couldn't show it.",
                        )
                      }}
                    >
                      Send a test reminder
                    </Button>
                    {testResult && <span className="text-xs text-zinc-500">{testResult}</span>}
                  </div>
                </dd>
                <dt className="text-zinc-500">Watched folders</dt>
                <dd className="font-mono text-xs">
                  {health.watch_dirs.join(', ')}
                  {health.watching ? '' : ' (not watching - scan manually)'}
                </dd>
                <dt className="text-zinc-500">Library</dt>
                <dd className="font-mono text-xs">{health.library_root}</dd>
              </dl>
            </Card>
            <div className="mt-3">
              <Notice tone="info">
                These are set in <code className="font-mono">backend/.env</code>. Restart{' '}
                <code className="font-mono">contextos serve</code> after changing them.
              </Notice>
            </div>
          </section>
        )}
      </div>
    </Page>
  )
}
