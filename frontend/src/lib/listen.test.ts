import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RESTART_DELAY_MS, joinSpeech, listen } from './voice'

type Result = { transcript: string; isFinal: boolean }

/** Stands in for Chrome's webkitSpeechRecognition. */
class FakeRecognition {
  static instances: FakeRecognition[] = []
  lang = ''
  continuous = false
  interimResults = false
  maxAlternatives = 1
  started = false
  onresult: ((e: unknown) => void) | null = null
  onerror: ((e: { error: string }) => void) | null = null
  onend: (() => void) | null = null
  private results: Result[] = []

  constructor() {
    FakeRecognition.instances.push(this)
  }
  start() {
    if (FakeRecognition.failStart) throw new Error('InvalidStateError')
    this.started = true
  }
  static failStart = false
  stop() {
    this.onend?.()
  }
  abort() {
    this.onerror?.({ error: 'aborted' })
    this.onend?.()
  }
  /** Chrome hears some words (final = the phrase is settled). */
  hear(transcript: string, isFinal: boolean) {
    const last = this.results[this.results.length - 1]
    if (last && !last.isFinal) this.results.pop()
    this.results.push({ transcript, isFinal })
    const results = this.results.map((r) => Object.assign([{ transcript: r.transcript }], { isFinal: r.isFinal }))
    this.onresult?.({ resultIndex: 0, results })
  }
  /** Chrome gives up on its own, e.g. after a pause. */
  timeout(error?: string) {
    if (error) this.onerror?.({ error })
    this.onend?.()
  }
}

const current = () => FakeRecognition.instances[FakeRecognition.instances.length - 1]

/** Chrome ends the session by itself, and our short restart delay passes. */
function chromePauses(error?: string) {
  current().timeout(error)
  vi.advanceTimersByTime(RESTART_DELAY_MS)
}

function start() {
  const texts: string[] = []
  const errors: string[] = []
  const ended: (string | null)[] = []
  const listener = listen({
    lang: 'en-IN',
    onText: (t) => texts.push(t),
    onError: (m) => errors.push(m),
    onEnd: (t) => ended.push(t),
  })
  return { listener, texts, errors, ended }
}

beforeEach(() => {
  FakeRecognition.instances = []
  FakeRecognition.failStart = false
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-16T10:00:00'))
  ;(globalThis as Record<string, unknown>).window = { webkitSpeechRecognition: FakeRecognition }
})

afterEach(() => {
  vi.useRealTimers()
  delete (globalThis as Record<string, unknown>).window
})

describe('listen', () => {
  it('listens continuously in the chosen language', () => {
    start()
    expect(current().continuous).toBe(true)
    expect(current().lang).toBe('en-IN')
  })

  it('keeps listening when Chrome stops during a pause', () => {
    const { listener, texts, ended } = start()
    current().hear('what is due', true)
    vi.advanceTimersByTime(8000)
    chromePauses('no-speech') // Chrome's silence timeout
    expect(FakeRecognition.instances).toHaveLength(2) // restarted quietly
    expect(ended).toEqual([]) // nothing was "finished", nothing sent

    current().hear('this week', false)
    expect(texts[texts.length - 1]).toBe('what is due this week')

    current().hear('this week', true)
    listener.stop()
    expect(ended).toEqual(['what is due this week'])
  })

  it('only ends when the user stops it', () => {
    const { listener, ended } = start()
    for (let i = 0; i < 4; i++) {
      current().hear(`part ${i}`, true)
      vi.advanceTimersByTime(10_000)
      chromePauses()
    }
    expect(ended).toEqual([])
    listener.stop()
    expect(ended).toEqual(['part 0 part 1 part 2 part 3'])
  })

  it('cancel throws away the result', () => {
    const { listener, ended } = start()
    current().hear('hello', true)
    listener.cancel()
    expect(ended).toEqual([null])
  })

  it('stops for good when the microphone is blocked', () => {
    const { errors, ended } = start()
    current().timeout('not-allowed')
    expect(FakeRecognition.instances).toHaveLength(1)
    expect(errors[0]).toContain('microphone')
    expect(ended).toEqual([''])
  })

  it('gives up if Chrome keeps failing straight away', () => {
    const { errors, ended } = start()
    for (let i = 0; i < 10 && ended.length === 0; i++) chromePauses()
    expect(FakeRecognition.instances.length).toBeLessThanOrEqual(7)
    expect(errors[0]).toContain('stopped unexpectedly')
    expect(ended).toHaveLength(1)
  })

  it("keeps words Chrome hadn't settled when it stopped", () => {
    const { listener, ended } = start()
    current().hear('submit the lab record', false) // still "in progress"
    vi.advanceTimersByTime(5000)
    chromePauses()
    current().hear('tomorrow', true)
    listener.stop()
    expect(ended).toEqual(['submit the lab record tomorrow'])
  })

  it('stopping in the moment between sessions still finishes once', () => {
    const { listener, ended } = start()
    current().hear('hello there', true)
    vi.advanceTimersByTime(5000)
    current().timeout() // Chrome stopped; our restart has not happened yet
    listener.stop()
    vi.advanceTimersByTime(RESTART_DELAY_MS * 4)
    expect(FakeRecognition.instances).toHaveLength(1) // no restart after stop
    expect(ended).toEqual(['hello there'])
  })

  it('reports a microphone that will not start', () => {
    FakeRecognition.failStart = true
    const { errors, ended } = start()
    expect(errors[0]).toContain("couldn't start")
    expect(ended).toEqual([''])
  })

  it('never glues phrases together, with or without Chrome spaces', () => {
    const { listener, ended } = start()
    current().hear('add an assignment for networks', true)
    current().hear('it is due friday', true) // no leading space
    current().hear(' and open youtube', true) // Chrome's usual leading space
    listener.stop()
    expect(ended).toEqual(['add an assignment for networks it is due friday and open youtube'])
  })

  it('says so when the browser cannot listen', () => {
    ;(globalThis as Record<string, unknown>).window = {}
    const { errors, ended } = start()
    expect(errors[0]).toContain('Google Chrome')
    expect(ended).toEqual([null])
  })
})

describe('joinSpeech', () => {
  it('joins with single spaces and skips blanks', () => {
    expect(joinSpeech(' add a task ', '', 'due friday ')).toBe('add a task due friday')
  })
})
