import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { KhushiAvatar } from './Khushi'
import { Badge, SubjectDot } from './ui'
import { api, type ChatExchange, type ChatMessage } from '../lib/api'
import { dueIn, formatDue, typeLabel } from '../lib/labels'

const STARTERS = [
  "What's due this week?",
  'Open Spotify',
  'Play lofi on YouTube',
  'Search black holes on Wikipedia',
  'Organise my files',
  'What can you do?',
]

/** The conversation with Khushi. Used full-page (/chat) and in the floating panel. */
export default function ChatPanel({ compact = false }: { compact?: boolean }) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null)
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.get<ChatMessage[]>('/chat').then(setMessages, (e) => setError(String(e)))
  }, [])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, sending])

  const send = async (said: string) => {
    const t = said.trim()
    if (!t || sending) return
    setText('')
    setError(null)
    setSending(true)
    // Show the user's message straight away; replace it with the saved one after.
    const pending: ChatMessage = {
      id: -Date.now(), role: 'user', text: t, created_at: new Date().toISOString(),
      actions: [], suggestions: [], by: null, tasks: [], files: [],
    }
    setMessages((m) => [...(m ?? []), pending])
    try {
      const ex = await api.post<ChatExchange>('/chat', { text: t })
      setMessages((m) => [...(m ?? []).filter((x) => x.id !== pending.id), ex.user, ex.reply])
    } catch (e) {
      setError(String(e))
    } finally {
      setSending(false)
      input.current?.focus()
    }
  }

  const clear = async () => {
    await api.del('/chat')
    setMessages([])
  }

  const last = messages?.[messages.length - 1]

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className={`min-h-0 flex-1 space-y-4 overflow-y-auto ${compact ? 'p-3' : 'pb-4'}`}>
        {messages?.length === 0 && (
          <div className="flex gap-3">
            <KhushiAvatar size={compact ? 32 : 40} />
            <div className="rounded-2xl rounded-tl-sm border border-zinc-200 bg-white px-4 py-3 text-sm dark:border-zinc-800 dark:bg-zinc-900">
              <p className="font-medium">Hi! I'm Khushi.</p>
              <p className="mt-1 text-zinc-600 dark:text-zinc-400">
                I can sort your files, keep track of assignments, open apps, search the web and
                play music. Try one of these, or just ask me something.
              </p>
            </div>
          </div>
        )}
        {messages?.map((m) =>
          m.role === 'user' ? (
            <div key={m.id} className="flex justify-end">
              <div className="bg-accent max-w-[85%] rounded-2xl rounded-tr-sm px-4 py-2 text-sm whitespace-pre-line text-white">
                {m.text}
              </div>
            </div>
          ) : (
            <KhushiMessage key={m.id} m={m} compact={compact} />
          ),
        )}
        {sending && (
          <div className="flex items-center gap-3">
            <KhushiAvatar size={compact ? 32 : 40} />
            <span className="text-sm text-zinc-500">
              Khushi is thinking<span className="animate-pulse">…</span>
            </span>
          </div>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div ref={bottom} />
      </div>

      {/* Quick replies: the latest suggestions, or starters on an empty chat. */}
      {!sending && (messages?.length === 0 || (last?.role === 'khushi' && last.suggestions.length > 0)) && (
        <div className={`flex flex-wrap gap-2 ${compact ? 'px-3 pb-2' : 'pb-3'}`}>
          {(messages?.length === 0 ? STARTERS : last!.suggestions).map((s) => (
            <button
              key={s}
              onClick={() => send(s)}
              className="hover:border-accent hover:text-accent rounded-full border border-zinc-300 px-3 py-1 text-xs dark:border-zinc-700"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className={`flex gap-2 border-t border-zinc-200 dark:border-zinc-800 ${compact ? 'p-3' : 'pt-3'}`}
        onSubmit={(e) => {
          e.preventDefault()
          send(text)
        }}
      >
        <input
          ref={input}
          autoFocus={!compact}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Ask Khushi anything…"
          aria-label="Message Khushi"
          className="focus:border-accent min-w-0 flex-1 rounded-full border border-zinc-300 bg-white px-4 py-2 text-sm outline-none dark:border-zinc-700 dark:bg-zinc-950"
        />
        <button
          type="submit"
          disabled={!text.trim() || sending}
          className="bg-accent rounded-full px-4 text-sm font-medium text-white disabled:opacity-50"
        >
          Send
        </button>
        {!compact && messages && messages.length > 0 && (
          <button
            type="button"
            onClick={clear}
            className="text-xs text-zinc-500 hover:underline"
            title="Clear the conversation"
          >
            Clear
          </button>
        )}
      </form>
    </div>
  )
}

function KhushiMessage({ m, compact }: { m: ChatMessage; compact: boolean }) {
  return (
    <div className="flex gap-3">
      <KhushiAvatar size={compact ? 32 : 40} />
      <div className="min-w-0 max-w-[90%] space-y-2">
        <div className="rounded-2xl rounded-tl-sm border border-zinc-200 bg-white px-4 py-2 text-sm whitespace-pre-line dark:border-zinc-800 dark:bg-zinc-900">
          {m.text}
        </div>

        {m.actions.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {m.actions.map((a, i) => (
              <Badge key={i} tone={a.ok ? 'good' : 'bad'}>
                {a.ok ? '✓' : '✕'}{' '}
                {a.url ? (
                  <a href={a.url} target="_blank" rel="noreferrer" className="hover:underline">
                    {a.label}
                  </a>
                ) : (
                  a.label
                )}
              </Badge>
            ))}
          </div>
        )}

        {m.tasks.length > 0 && (
          <ul className="divide-y divide-zinc-100 overflow-hidden rounded-lg border border-zinc-200 bg-white text-sm dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
            {m.tasks.map((t) => (
              <li key={t.id}>
                <Link to="/tasks" className="flex items-center gap-2 px-3 py-2 hover:bg-zinc-50 dark:hover:bg-zinc-800/50">
                  <SubjectDot color={t.subject_color} />
                  <span className={`min-w-0 flex-1 truncate ${t.status === 'done' ? 'text-zinc-400 line-through' : ''}`}>
                    {t.title}
                  </span>
                  <span
                    className={`shrink-0 text-xs ${t.days_left !== null && t.days_left < 0 ? 'text-red-600' : 'text-zinc-500'}`}
                  >
                    {t.status === 'done'
                      ? 'finished'
                      : t.due_at
                        ? `${formatDue(t.due_at)} · ${dueIn(t.days_left)}`
                        : 'no deadline'}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {m.files.length > 0 && (
          <ul className="divide-y divide-zinc-100 overflow-hidden rounded-lg border border-zinc-200 bg-white text-sm dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
            {m.files.map((f) => (
              <li key={f.id}>
                <button
                  onClick={() => api.post(`/files/${f.id}/open`)}
                  title={`Open ${f.filename}`}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                >
                  <Badge>{typeLabel(f.doc_type)}</Badge>
                  <span className="min-w-0 flex-1 truncate">{f.title ?? f.filename}</span>
                  <span className="shrink-0 text-xs text-zinc-500">{f.subject}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
