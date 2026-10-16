import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { MicIcon, SpeakerIcon, SpeakerOffIcon, StopIcon } from './icons'
import { KhushiAvatar } from './Khushi'
import { Badge, SubjectDot } from './ui'
import { api, type ChatExchange, type ChatMessage } from '../lib/api'
import { dueIn, formatDue, typeLabel } from '../lib/labels'
import { useVoiceSettings } from '../lib/useVoiceSettings'
import {
  canListen,
  canSpeak,
  joinSpeech,
  listen,
  speak,
  spokenText,
  stopSpeaking,
  type Listener,
} from '../lib/voice'

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
  const [listening, setListening] = useState(false)
  const [listenSeconds, setListenSeconds] = useState(0)
  const [speakingId, setSpeakingId] = useState<number | null>(null)
  const [voice, setVoice] = useVoiceSettings()
  const bottom = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const listener = useRef<Listener | null>(null)

  // Closing the panel or leaving the page silences Khushi and the mic.
  useEffect(
    () => () => {
      stopSpeaking()
      listener.current?.cancel()
    },
    [],
  )

  const say = (m: ChatMessage) =>
    speak(spokenText(m), voice, {
      onStart: () => setSpeakingId(m.id),
      onEnd: () => setSpeakingId((id) => (id === m.id ? null : id)),
    })

  const toggleSpeaking = (m: ChatMessage) => {
    if (speakingId === m.id) {
      stopSpeaking()
      setSpeakingId(null)
    } else {
      say(m)
    }
  }

  // The mic stays on through pauses until you tap it again. What you said lands
  // in the message box - nothing is sent until you press Send.
  const toggleMic = () => {
    if (listening) {
      listener.current?.stop()
      return
    }
    setError(null)
    setSpeakingId(null)
    setListening(true)
    const before = text // speech is added after anything already typed
    listener.current = listen({
      lang: voice.listenLang,
      onText: (heard) => setText(joinSpeech(before, heard)),
      onError: setError,
      onEnd: (heard) => {
        setListening(false)
        listener.current = null
        if (heard !== null) {
          setText(joinSpeech(before, heard))
          input.current?.focus()
        }
      },
    })
  }

  useEffect(() => {
    if (!listening) return
    const startedAt = Date.now()
    const tick = window.setInterval(
      () => setListenSeconds(Math.floor((Date.now() - startedAt) / 1000)),
      1000,
    )
    return () => {
      window.clearInterval(tick)
      setListenSeconds(0)
    }
  }, [listening])

  // The box grows with its text (up to a limit, then scrolls). While you
  // dictate it follows the newest words, so nothing you say is out of sight.
  useLayoutEffect(() => {
    const box = input.current
    if (!box) return
    const fit = () => {
      const max = compact ? 120 : 200
      box.style.height = 'auto'
      box.style.height = `${Math.min(box.scrollHeight, max)}px`
      box.style.overflowY = box.scrollHeight > max ? 'auto' : 'hidden'
      if (listening) box.scrollTop = box.scrollHeight
    }
    fit()
    // A new width re-wraps the text (panel opened, window resized). Our own
    // height changes are ignored, so this can't loop.
    let width = box.clientWidth
    const watch = new ResizeObserver(() => {
      if (box.clientWidth !== width) {
        width = box.clientWidth
        fit()
      }
    })
    watch.observe(box)
    return () => watch.disconnect()
  }, [text, listening, compact])

  useEffect(() => {
    api.get<ChatMessage[]>('/chat').then(setMessages, (e) => setError(String(e)))
  }, [])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, sending])

  const send = async (said: string) => {
    const t = said.trim()
    if (!t || sending) return
    // Sending while the mic is on: send what's in the box and stop listening.
    listener.current?.cancel()
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
      if (voice.speak) say(ex.reply)
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
            <KhushiMessage
              key={m.id}
              m={m}
              compact={compact}
              speaking={speakingId === m.id}
              onSpeak={canSpeak() ? () => toggleSpeaking(m) : undefined}
            />
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

      {listening && (
        <p
          role="status"
          className={`flex items-center gap-2 text-xs text-red-600 ${compact ? 'px-3 pb-1' : 'pb-1'}`}
        >
          <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
          Listening {Math.floor(listenSeconds / 60)}:{String(listenSeconds % 60).padStart(2, '0')}
          {' · '}pause as much as you like. Tap stop when you're done, then press Send.
        </p>
      )}

      <form
        className={`flex items-end gap-2 border-t border-zinc-200 dark:border-zinc-800 ${compact ? 'p-3' : 'pt-3'}`}
        onSubmit={(e) => {
          e.preventDefault()
          send(text)
        }}
      >
        {canSpeak() && (
          <button
            type="button"
            onClick={() => {
              if (voice.speak) stopSpeaking()
              setVoice({ speak: !voice.speak })
            }}
            aria-label={voice.speak ? 'Mute Khushi' : 'Let Khushi speak'}
            aria-pressed={voice.speak}
            title={voice.speak ? 'Khushi speaks her replies (click to mute)' : 'Khushi is muted'}
            className={`rounded-full p-2 ${voice.speak ? 'text-accent' : 'text-zinc-400'} hover:bg-zinc-100 dark:hover:bg-zinc-800`}
          >
            {voice.speak ? <SpeakerIcon /> : <SpeakerOffIcon />}
          </button>
        )}
        {/* Grows with what you type or say, so every word stays visible.
            Enter sends; Shift+Enter starts a new line. */}
        <textarea
          ref={input}
          rows={1}
          autoFocus={!compact}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              send(text)
            }
          }}
          placeholder={listening ? 'Listening… tap stop when you are done' : 'Ask Khushi anything…'}
          aria-label="Message Khushi"
          className={`focus:border-accent min-w-0 flex-1 resize-none rounded-2xl border bg-white px-4 py-2 text-sm leading-5 outline-none dark:bg-zinc-950 ${listening ? 'border-red-400' : 'border-zinc-300 dark:border-zinc-700'}`}
        />
        {canListen() && (
          <button
            type="button"
            onClick={toggleMic}
            disabled={sending}
            aria-label={listening ? 'Stop listening' : 'Talk to Khushi'}
            aria-pressed={listening}
            title={listening ? 'Stop listening (your words stay in the box)' : 'Talk to Khushi'}
            className={`rounded-full p-2 disabled:opacity-50 ${listening ? 'bg-red-500 text-white hover:bg-red-600' : 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'}`}
          >
            {listening ? <StopIcon /> : <MicIcon />}
          </button>
        )}
        <button
          type="submit"
          disabled={!text.trim() || sending}
          className="bg-accent h-9 rounded-full px-4 text-sm font-medium text-white disabled:opacity-50"
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

function KhushiMessage({
  m,
  compact,
  speaking,
  onSpeak,
}: {
  m: ChatMessage
  compact: boolean
  speaking: boolean
  onSpeak?: () => void
}) {
  return (
    <div className="flex gap-3">
      <div className={speaking ? 'animate-pulse' : ''}>
        <KhushiAvatar size={compact ? 32 : 40} />
      </div>
      <div className="min-w-0 max-w-[90%] space-y-2">
        <div className="group flex items-start gap-1">
          <div className="rounded-2xl rounded-tl-sm border border-zinc-200 bg-white px-4 py-2 text-sm whitespace-pre-line dark:border-zinc-800 dark:bg-zinc-900">
            {m.text}
          </div>
          {onSpeak && (
            <button
              onClick={onSpeak}
              aria-label={speaking ? 'Stop reading' : 'Read this aloud'}
              title={speaking ? 'Stop' : 'Read aloud'}
              className={`mt-1 shrink-0 rounded-full p-1 ${speaking ? 'text-accent' : 'text-zinc-400 opacity-0 group-hover:opacity-100 focus:opacity-100'} hover:bg-zinc-100 dark:hover:bg-zinc-800`}
            >
              {speaking ? <StopIcon /> : <SpeakerIcon />}
            </button>
          )}
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
