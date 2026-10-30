import { describe, expect, it } from 'vitest'
import { longDate, startOfWeek } from './labels'

const ymd = (d: Date) => [d.getFullYear(), d.getMonth() + 1, d.getDate()]

describe('startOfWeek', () => {
  it('goes back to Monday at midnight', () => {
    const d = startOfWeek(new Date(2026, 9, 30, 15, 45)) // Friday 30 Oct 2026
    expect(ymd(d)).toEqual([2026, 10, 26])
    expect([d.getHours(), d.getMinutes(), d.getSeconds()]).toEqual([0, 0, 0])
  })

  it('counts Sunday as the end of the week, not the start', () => {
    expect(ymd(startOfWeek(new Date(2026, 10, 1, 21)))).toEqual([2026, 10, 26]) // Sunday 1 Nov
  })

  it('keeps a Monday as it is', () => {
    expect(ymd(startOfWeek(new Date(2026, 9, 26, 0, 0)))).toEqual([2026, 10, 26])
  })

  it('crosses the end of a month and a year', () => {
    expect(ymd(startOfWeek(new Date(2027, 0, 1, 12)))).toEqual([2026, 12, 28]) // Friday 1 Jan 2027
  })

  it('does not change the date it was given', () => {
    const now = new Date(2026, 9, 30, 15, 45)
    startOfWeek(now)
    expect(now.getDate()).toBe(30)
  })
})

describe('longDate', () => {
  it('ends with the day, month and year, in that order', () => {
    const text = longDate(new Date(2026, 9, 30))
    expect(text).toMatch(/ 30 \S+ 2026$/)
  })
})
