// Khushi's voice: speaking (speechSynthesis) and listening (SpeechRecognition).
// Both are built into the browser, so nothing is downloaded or installed.
// Listening works in Google Chrome, which sends the audio to Google to transcribe.

import type { ChatMessage } from './api'
import { dueIn } from './labels'

// -- settings (per browser) ----------------------------------------------------

export type VoiceSettings = {
  speak: boolean // read Khushi's replies aloud
  voiceName: string | null // null = pick automatically
  rate: number // 0.7 - 1.4
  listenLang: string // speech recognition language
}

export const DEFAULT_VOICE_SETTINGS: VoiceSettings = {
  speak: true,
  voiceName: null,
  rate: 1,
  listenLang: 'en-IN',
}

const KEY = 'contextos.voice'
const EVENT = 'contextos-voice-settings'

export function loadVoiceSettings(): VoiceSettings {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? { ...DEFAULT_VOICE_SETTINGS, ...JSON.parse(raw) } : DEFAULT_VOICE_SETTINGS
  } catch {
    return DEFAULT_VOICE_SETTINGS // private mode or blocked storage: defaults still work
  }
}

export function saveVoiceSettings(s: VoiceSettings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s))
  } catch {
    // not persisted, but still applied for this page
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: s }))
}

export function onVoiceSettings(fn: (s: VoiceSettings) => void): () => void {
  const handler = (e: Event) => fn((e as CustomEvent<VoiceSettings>).detail)
  window.addEventListener(EVENT, handler)
  return () => window.removeEventListener(EVENT, handler)
}

export const LISTEN_LANGUAGES = [
  { code: 'en-IN', label: 'English (India)' },
  { code: 'en-US', label: 'English (US)' },
  { code: 'en-GB', label: 'English (UK)' },
  { code: 'hi-IN', label: 'Hindi' },
]

// -- speaking -------------------------------------------------------------------

export const canSpeak = () => typeof window !== 'undefined' && 'speechSynthesis' in window

let waitedForVoices = false

/** Voices load asynchronously in Chrome; wait for them once (briefly). */
export function getVoices(): Promise<SpeechSynthesisVoice[]> {
  if (!canSpeak()) return Promise.resolve([])
  const now = speechSynthesis.getVoices()
  if (now.length || waitedForVoices) return Promise.resolve(now)
  return new Promise((resolve) => {
    const done = () => {
      waitedForVoices = true
      resolve(speechSynthesis.getVoices())
    }
    speechSynthesis.addEventListener('voiceschanged', done, { once: true })
    setTimeout(done, 1500)
  })
}

type VoiceLike = { name: string; lang: string; localService?: boolean }

/** Khushi's default voice: Indian English if there is one, else a female English voice. */
export function pickVoice<V extends VoiceLike>(voices: V[], preferred: string | null): V | null {
  if (preferred) {
    const exact = voices.find((v) => v.name === preferred)
    if (exact) return exact
  }
  const english = voices.filter((v) => v.lang.toLowerCase().startsWith('en'))
  const score = (v: V) => {
    const name = v.name.toLowerCase()
    let s = 0
    if (v.lang.toLowerCase() === 'en-in') s += 5
    if (/female|woman|heera|veena|neerja|zira|samantha|serena|karen/.test(name)) s += 3
    if (name.includes('google')) s += 2 // Chrome's online voices sound far better than espeak
    if (/uk english female|en-gb/.test(name + v.lang.toLowerCase())) s += 1
    // Khushi is a she: skip voices known to be male.
    if ((/male\b/.test(name) && !name.includes('female')) || /ravi|prabhat|david|mark|daniel/.test(name)) s -= 4
    return s
  }
  return [...english].sort((a, b) => score(b) - score(a))[0] ?? voices[0] ?? null
}

/** Text that sounds right when read aloud: no emoji, bullets, fancy quotes or links. */
export function forSpeech(text: string): string {
  return text
    .replace(/https?:\/\/\S+/g, '')
    .replace(/\p{Extended_Pictographic}/gu, '')
    .replace(/[“”"]/g, '')
    .replace(/[•→✓✕]/g, ' ')
    .replace(/\s*\n+\s*/g, '. ')
    .replace(/\.\s*\./g, '.')
    .replace(/:\s*\./g, ':')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

/** Chrome cuts long utterances off, so speak in sentence-sized chunks. */
export function chunk(text: string, max = 180): string[] {
  const sentences = text.match(/[^.!?]+[.!?]*/g) ?? [text]
  const out: string[] = []
  let current = ''
  for (const s of sentences.map((x) => x.trim()).filter(Boolean)) {
    if ((current + ' ' + s).trim().length > max && current) {
      out.push(current)
      current = s
    } else {
      current = (current + ' ' + s).trim()
    }
  }
  if (current) out.push(current)
  return out
}

/** What Khushi says for a message: its text, plus the first few task/file cards. */
export function spokenText(m: Pick<ChatMessage, 'text' | 'tasks' | 'files'>): string {
  const parts = [m.text]
  const tasks = m.tasks.slice(0, 3).map((t) => {
    if (t.status === 'done') return `${t.title}, finished`
    if (!t.due_at) return `${t.title}, no deadline`
    const d = new Date(t.due_at)
    const day = d.toLocaleDateString('en-GB', {
      weekday: 'long',
      day: 'numeric',
      month: 'long',
      year: 'numeric',
    })
    return `${t.title}, due ${day}, ${dueIn(t.days_left)}`
  })
  if (tasks.length) parts.push(tasks.join('. '))
  if (m.tasks.length > 3) parts.push(`and ${m.tasks.length - 3} more`)
  const files = m.files.slice(0, 3).map((f) => f.title ?? f.filename)
  if (files.length) parts.push(files.join(', '))
  if (m.files.length > 3) parts.push(`and ${m.files.length - 3} more`)
  return forSpeech(parts.join('. '))
}

let speakingId = 0

/** Say `text` in Khushi's voice. Calling again interrupts what she was saying. */
export async function speak(
  text: string,
  settings: VoiceSettings,
  handlers: { onStart?: () => void; onEnd?: () => void } = {},
): Promise<void> {
  if (!canSpeak()) return
  const id = ++speakingId
  speechSynthesis.cancel()
  const voice = pickVoice(await getVoices(), settings.voiceName)
  const parts = chunk(forSpeech(text))
  if (!parts.length || id !== speakingId) return
  handlers.onStart?.()
  parts.forEach((part, i) => {
    const u = new SpeechSynthesisUtterance(part)
    if (voice) {
      u.voice = voice
      u.lang = voice.lang
    }
    u.rate = settings.rate
    u.pitch = 1.05
    if (i === parts.length - 1) {
      u.onend = () => id === speakingId && handlers.onEnd?.()
      u.onerror = () => id === speakingId && handlers.onEnd?.()
    }
    speechSynthesis.speak(u)
  })
}

export function stopSpeaking(): void {
  speakingId++
  if (canSpeak()) speechSynthesis.cancel()
}

// -- listening --------------------------------------------------------------------

type Recognition = {
  lang: string
  interimResults: boolean
  continuous: boolean
  maxAlternatives: number
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
}

function recognitionClass(): (new () => Recognition) | null {
  const w = window as unknown as Record<string, unknown>
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as (new () => Recognition) | null
}

export const canListen = () => typeof window !== 'undefined' && recognitionClass() !== null

// Errors that mean listening cannot continue. Anything else (Chrome's silence
// timeout, "no-speech" during a long pause) just restarts the recogniser.
const FATAL_ERRORS: Record<string, string> = {
  'not-allowed': "I can't use the microphone. Allow it in the browser's address bar and try again.",
  'service-not-allowed': "I can't use the microphone. Allow it in the browser's address bar and try again.",
  'audio-capture': "I couldn't find a microphone.",
  network: 'Voice typing needs an internet connection (Chrome sends the audio to Google to turn it into text).',
  'language-not-supported': "Chrome can't listen in that language. Pick another one in Settings.",
}

/** Join pieces of speech with single spaces. */
export function joinSpeech(...parts: string[]): string {
  return parts.map((p) => p.trim()).filter(Boolean).join(' ')
}

export type Listener = {
  /** The user is done: stop and deliver everything heard to onEnd. */
  stop: () => void
  /** Throw away what is still being recognised (e.g. the message was just sent). */
  cancel: () => void
}

// Chrome restarting right after a failure would loop forever; give up after this many.
const MAX_QUICK_RESTARTS = 5
// Restarting the instant Chrome lets go of the mic can fail; wait a moment first.
export const RESTART_DELAY_MS = 250

/**
 * Listen until the user says stop - pauses do not end it.
 *
 * Chrome ends a recognition session by itself after a silence (or about a
 * minute). When that happens we keep what was heard - including words Chrome
 * had not finished settling - and quietly start a new session, so the mic
 * stays on until `stop()` is called. `onText` gets the full transcript so far;
 * `onEnd` is called exactly once, with the text, or null after `cancel()`.
 */
export function listen(opts: {
  lang: string
  onText: (text: string) => void
  onError: (message: string) => void
  onEnd: (text: string | null) => void
}): Listener {
  const Rec = recognitionClass()
  if (!Rec) {
    opts.onError('Voice typing works in Google Chrome. This browser does not support it.')
    opts.onEnd(null)
    return { stop: () => {}, cancel: () => {} }
  }

  let committed = '' // text kept from earlier sessions
  let stopped = false // the user (or a fatal error) ended listening
  let cancelled = false
  let finished = false
  let quickRestarts = 0
  let startedAt = 0
  let rec: Recognition | null = null
  let restartTimer: ReturnType<typeof setTimeout> | null = null

  const finish = () => {
    if (finished) return
    finished = true
    opts.onEnd(cancelled ? null : committed)
  }

  const begin = () => {
    restartTimer = null
    if (stopped) return finish()
    const r = new Rec()
    rec = r
    r.lang = opts.lang
    r.interimResults = true
    r.continuous = true
    r.maxAlternatives = 1
    let sessionFinal = ''
    let sessionInterim = ''
    r.onresult = (e) => {
      sessionFinal = ''
      sessionInterim = ''
      for (let i = 0; i < e.results.length; i++) {
        // Chrome usually starts each phrase with a space, but not always: join safely.
        const res = e.results[i]
        if (res.isFinal) sessionFinal = joinSpeech(sessionFinal, res[0].transcript)
        else sessionInterim = joinSpeech(sessionInterim, res[0].transcript)
      }
      quickRestarts = 0 // it is working: reset the failure counter
      opts.onText(joinSpeech(committed, sessionFinal, sessionInterim))
    }
    r.onerror = (e) => {
      const fatal = FATAL_ERRORS[e.error]
      if (fatal && !stopped) {
        stopped = true
        opts.onError(fatal)
      }
    }
    r.onend = () => {
      // Words still "in progress" when the session ended are kept, not lost.
      committed = joinSpeech(committed, sessionFinal, sessionInterim)
      if (rec !== r) return
      rec = null
      if (stopped) return finish()
      quickRestarts = Date.now() - startedAt < 1500 ? quickRestarts + 1 : 0
      if (quickRestarts > MAX_QUICK_RESTARTS) {
        stopped = true
        opts.onError('Listening stopped unexpectedly. Tap the mic to try again.')
        return finish()
      }
      opts.onText(committed)
      restartTimer = setTimeout(begin, RESTART_DELAY_MS) // Chrome paused us: keep listening
    }
    startedAt = Date.now()
    try {
      r.start()
    } catch {
      rec = null
      stopped = true
      opts.onError("I couldn't start the microphone. Tap the mic to try again.")
      finish()
    }
  }

  stopSpeaking() // don't let Khushi talk over you
  begin()

  // Between Chrome stopping and our restart there is no session to stop.
  const end = (how: 'stop' | 'abort') => {
    stopped = true
    if (restartTimer !== null) {
      clearTimeout(restartTimer)
      restartTimer = null
      return finish()
    }
    if (rec) rec[how]() // delivers the last words (stop) or drops them (abort), then onend
    else finish()
  }
  return {
    stop: () => end('stop'),
    cancel: () => {
      cancelled = true
      end('abort')
    },
  }
}
