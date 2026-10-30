import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Page from '../components/Page'
import { Badge, Card, Notice, SubjectDot, inputClass } from '../components/ui'
import { api, type Doc, type DocType } from '../lib/api'
import { DOC_TYPES, typeLabel } from '../lib/labels'

export default function Files() {
  const [files, setFiles] = useState<Doc[] | null>(null)
  const [query, setQuery] = useState('')
  const [subject, setSubject] = useState('')
  const [docType, setDocType] = useState<DocType | ''>('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get<Doc[]>('/files').then(setFiles, (e) => setError(String(e)))
  }, [])

  const subjects = useMemo(
    () => [...new Set((files ?? []).map((f) => f.subject ?? 'Unsorted'))].sort(),
    [files],
  )

  // Semester -> Subject -> files, after filtering.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase()
    const out = new Map<string, Map<string, Doc[]>>()
    for (const f of files ?? []) {
      const subj = f.subject ?? 'Unsorted'
      if (subject && subj !== subject) continue
      if (docType && f.doc_type !== docType) continue
      if (q && !`${f.title} ${f.filename} ${subj}`.toLowerCase().includes(q)) continue
      const sem = f.semester ?? 'General'
      if (!out.has(sem)) out.set(sem, new Map())
      const bySubject = out.get(sem)!
      if (!bySubject.has(subj)) bySubject.set(subj, [])
      bySubject.get(subj)!.push(f)
    }
    return [...out.entries()].sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
  }, [files, query, subject, docType])

  const open = async (doc: Doc) => {
    setError(null)
    try {
      await api.post(`/files/${doc.id}/open`)
    } catch (e) {
      setError(String(e))
    }
  }

  return (
    <Page title="Files" subtitle="Your organised library.">
      <div className="space-y-4">
        <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
          <input
            className={inputClass}
            placeholder="Search titles, file names, subjects…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select className={inputClass} value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="">All subjects</option>
            {subjects.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <select
            className={inputClass}
            value={docType}
            onChange={(e) => setDocType(e.target.value as DocType | '')}
          >
            <option value="">All types</option>
            {DOC_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        {error && <Notice tone="bad">{error}</Notice>}

        {files !== null && files.length === 0 && (
          <Card className="py-10 text-center">
            <p className="font-medium">Your library is empty.</p>
            <p className="mt-1 text-sm text-stone-500">
              Approve some moves on the{' '}
              <Link to="/organize" className="text-accent hover:underline">
                Organize
              </Link>{' '}
              page and they will appear here.
            </p>
          </Card>
        )}

        {groups.map(([sem, bySubject]) => (
          <section key={sem}>
            <h2 className="mb-3 font-display text-xl font-extrabold tracking-tight">{sem}</h2>
            <div className="space-y-3">
              {[...bySubject.entries()].map(([subj, docs]) => (
                <Card key={subj} pad={false}>
                  {/* Each subject's header is tinted in its colour, like a binder divider. */}
                  <div
                    className="flex items-center gap-2.5 rounded-t-[27px] px-5 pt-4 pb-3"
                    style={{ background: `${docs[0].subject_color ?? '#a1a1aa'}26` }}
                  >
                    <SubjectDot color={docs[0].subject_color} />
                    <span className="font-display text-lg font-bold">{subj}</span>
                    <span className="text-sm text-stone-500">
                      {docs.length} {docs.length === 1 ? 'file' : 'files'}
                    </span>
                  </div>
                  <ul className="divide-y divide-stone-100 dark:divide-stone-800">
                    {docs.map((d) => (
                      <li key={d.id}>
                        <button
                          onClick={() => open(d)}
                          className="flex w-full items-center gap-3 px-5 py-2.5 text-left text-sm hover:bg-stone-100 dark:hover:bg-stone-800/50"
                          title={d.current_path}
                        >
                          <Badge>{typeLabel(d.doc_type)}</Badge>
                          <span className="min-w-0 flex-1 truncate">{d.title ?? d.filename}</span>
                          <span className="hidden truncate font-mono text-xs text-stone-400 sm:block">
                            {d.filename}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </Card>
              ))}
            </div>
          </section>
        ))}
      </div>
    </Page>
  )
}
