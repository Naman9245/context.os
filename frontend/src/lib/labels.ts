import type { DocType } from './api'

export const DOC_TYPES: { value: DocType; label: string }[] = [
  { value: 'notes', label: 'Notes' },
  { value: 'slides', label: 'Slides' },
  { value: 'assignment', label: 'Assignment' },
  { value: 'question_paper', label: 'Question paper' },
  { value: 'lab', label: 'Lab' },
  { value: 'syllabus', label: 'Syllabus' },
  { value: 'notice', label: 'Notice' },
  { value: 'other', label: 'Other' },
]

export const typeLabel = (t: DocType) => DOC_TYPES.find((d) => d.value === t)?.label ?? t

export function formatDue(iso: string | null): string {
  if (!iso) return 'no date'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

export function timeAgo(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return new Date(iso).toLocaleDateString()
}

export const basename = (path: string) => path.split(/[\\/]/).pop() ?? path

/** "today", "tomorrow", "in 5 days", "2 days late" */
export function dueIn(daysLeft: number | null): string {
  if (daysLeft === null) return 'no deadline'
  if (daysLeft === 0) return 'today'
  if (daysLeft === 1) return 'tomorrow'
  if (daysLeft === -1) return '1 day late'
  if (daysLeft < 0) return `${-daysLeft} days late`
  return `in ${daysLeft} days`
}
