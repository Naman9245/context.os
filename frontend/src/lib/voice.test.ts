import { describe, expect, it } from 'vitest'
import type { Doc, Task } from './api'
import { chunk, forSpeech, pickVoice, spokenText } from './voice'

const v = (name: string, lang: string) => ({ name, lang, localService: false })

describe('pickVoice', () => {
  const voices = [
    v('espeak English', 'en'),
    v('Google US English', 'en-US'),
    v('Google UK English Male', 'en-GB'),
    v('Google UK English Female', 'en-GB'),
    v('Google हिन्दी', 'hi-IN'),
  ]

  it('prefers a female Google English voice', () => {
    expect(pickVoice(voices, null)?.name).toBe('Google UK English Female')
  })

  it('prefers Indian English when available', () => {
    expect(pickVoice([...voices, v('Google English India', 'en-IN')], null)?.name).toBe(
      'Google English India',
    )
  })

  it('but not a male Indian voice', () => {
    expect(pickVoice([...voices, v('Microsoft Ravi', 'en-IN')], null)?.name).toBe(
      'Google UK English Female',
    )
  })

  it("honours the user's choice", () => {
    expect(pickVoice(voices, 'Google US English')?.name).toBe('Google US English')
  })

  it('falls back when the chosen voice is gone', () => {
    expect(pickVoice(voices, 'Removed Voice')?.name).toBe('Google UK English Female')
  })

  it('copes with no voices', () => {
    expect(pickVoice([], null)).toBeNull()
  })
})

describe('forSpeech', () => {
  it('drops quotes, bullets, emoji and links', () => {
    expect(forSpeech('Added “DBMS report” 🎉 https://x.com/a')).toBe('Added DBMS report')
  })

  it('turns lines into sentences', () => {
    expect(forSpeech("I can:\n• organise files\n• track assignments")).toBe(
      'I can: organise files. track assignments',
    )
  })
})

describe('chunk', () => {
  it('keeps short text whole', () => {
    expect(chunk('Hi there. How are you?')).toEqual(['Hi there. How are you?'])
  })

  it('splits long text at sentence ends', () => {
    const s = 'This sentence is about forty characters. '
    const parts = chunk(s.repeat(10), 100)
    expect(parts.length).toBeGreaterThan(3)
    expect(parts.every((p) => p.length <= 100 && p.endsWith('.'))).toBe(true)
  })
})

describe('spokenText', () => {
  const task = (title: string, due: string | null, days: number | null): Task => ({
    id: 1, title, notes: null, subject_id: null, subject: null, subject_color: null,
    due_at: due, days_left: days, status: 'todo', source: 'manual', document_id: null,
    document_name: null, steps: [], completed_at: null,
  })

  it('reads out the task cards', () => {
    const text = spokenText({
      text: 'You have 1 thing due this week:',
      tasks: [task('DBMS Assignment 2', '2026-10-24T23:59:00', 3)],
      files: [],
    })
    expect(text).toBe(
      'You have 1 thing due this week: DBMS Assignment 2, due Saturday, 24 October 2026, in 3 days',
    )
  })

  it('only reads the first three cards', () => {
    const tasks = [1, 2, 3, 4, 5].map((i) => task(`Task ${i}`, null, null))
    const text = spokenText({ text: 'Here:', tasks, files: [] })
    expect(text).toContain('Task 3, no deadline')
    expect(text).not.toContain('Task 4')
    expect(text).toContain('and 2 more')
  })

  it('names files', () => {
    const doc = { title: 'Module 3', filename: 'm3.pdf' } as Doc
    expect(spokenText({ text: 'I found 1 file:', tasks: [], files: [doc] })).toBe(
      'I found 1 file: Module 3',
    )
  })
})
