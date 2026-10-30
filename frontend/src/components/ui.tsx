import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { ArrowIcon } from './icons'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

// Buttons are pills. The main action is ink - sun in dark mode, where ink would vanish.
const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-stone-900 text-stone-50 hover:bg-stone-700 disabled:opacity-40 dark:bg-sun dark:text-stone-900 dark:hover:bg-butter',
  secondary:
    'border border-stone-300 bg-stone-50 hover:border-stone-900 disabled:opacity-50 dark:border-stone-700 dark:bg-stone-900 dark:hover:border-stone-400',
  ghost:
    'text-stone-600 hover:bg-stone-200/70 disabled:opacity-50 dark:text-stone-300 dark:hover:bg-stone-800',
  danger: 'text-red-600 hover:bg-red-50 disabled:opacity-50 dark:text-red-300 dark:hover:bg-red-950',
}

export function Button({
  variant = 'secondary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold transition active:scale-[0.97] disabled:cursor-not-allowed disabled:active:scale-100 ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  )
}

export type Tone =
  | 'paper'
  | 'coral'
  | 'sun'
  | 'pine'
  | 'lilac'
  | 'tangerine'
  | 'ink'
  | 'butter'
  | 'blush'
  | 'mint'
  | 'haze'
  | 'peach'

// Ink text on every colour card; paper text on pine and ink.
const TONES: Record<Tone, string> = {
  paper: 'border border-stone-200 bg-stone-50 dark:border-stone-800 dark:bg-stone-900',
  coral: 'bg-coral text-stone-900',
  sun: 'bg-sun text-stone-900',
  pine: 'bg-pine text-stone-50',
  lilac: 'bg-lilac text-stone-900',
  tangerine: 'bg-tangerine text-stone-900',
  ink: 'bg-stone-900 text-stone-50 dark:ring-1 dark:ring-stone-800',
  butter: 'bg-butter text-stone-900',
  blush: 'bg-blush text-stone-900',
  mint: 'bg-mint text-stone-900',
  haze: 'bg-haze text-stone-900',
  peach: 'bg-peach text-stone-900',
}

/** A rounded card. `pad={false}` for lists that run edge to edge. */
export function Card({
  children,
  className = '',
  tone = 'paper',
  pad = true,
}: {
  children: ReactNode
  className?: string
  tone?: Tone
  pad?: boolean
}) {
  return (
    <div className={`rounded-[28px] ${pad ? 'p-5' : ''} ${TONES[tone]} ${className}`}>
      {children}
    </div>
  )
}

/** The round arrow that marks something you can open. Decorative: the link carries the words. */
export function ArrowCircle({ light = false }: { light?: boolean }) {
  return (
    <span
      aria-hidden
      className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition group-hover:scale-110 ${
        light
          ? 'bg-stone-50 text-stone-900'
          : 'bg-stone-900 text-stone-50 dark:bg-stone-50 dark:text-stone-900'
      }`}
    >
      <ArrowIcon />
    </span>
  )
}

export function Badge({
  children,
  tone = 'neutral',
  title,
}: {
  children: ReactNode
  tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'accent'
  title?: string
}) {
  const tones = {
    neutral: 'bg-stone-200/80 text-stone-700 dark:bg-stone-800 dark:text-stone-300',
    good: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
    warn: 'bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
    bad: 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
    accent: 'bg-haze text-stone-900 dark:bg-stone-800 dark:text-haze',
  }
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ${tones[tone]}`}
    >
      {children}
    </span>
  )
}

export function Notice({
  tone = 'warn',
  children,
}: {
  tone?: 'warn' | 'bad' | 'info'
  children: ReactNode
}) {
  const tones = {
    warn: 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200',
    bad: 'border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200',
    info: 'border-stone-200 bg-stone-50 text-stone-700 dark:border-stone-800 dark:bg-stone-900 dark:text-stone-300',
  }
  return <div className={`rounded-[22px] border px-4 py-3 text-sm ${tones[tone]}`}>{children}</div>
}

export function SubjectDot({ color }: { color: string | null }) {
  return (
    <span
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ background: color ?? '#a1a1aa' }}
    />
  )
}

export const inputClass =
  'w-full rounded-2xl border border-stone-300 bg-stone-50 px-3 py-2 text-sm outline-none placeholder:text-stone-400 focus:border-accent focus:ring-2 focus:ring-accent/20 dark:border-stone-700 dark:bg-stone-950'
