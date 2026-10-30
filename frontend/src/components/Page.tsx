import type { ReactNode } from 'react'

export default function Page({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children?: ReactNode
}) {
  return (
    <section className="mx-auto max-w-6xl">
      <header className="mb-7">
        <h1 className="font-display text-4xl leading-none font-extrabold tracking-tight sm:text-5xl">
          {title}
        </h1>
        {subtitle && <p className="mt-3 text-stone-500">{subtitle}</p>}
      </header>
      {children}
    </section>
  )
}

// Decorative capsule bars, shaped like the weekly chart the page will show.
const PREVIEW_BARS = [45, 70, 55, 90, 62, 30, 78]

/** A page a later phase builds: what it will do, with a preview of its chart. */
export function ComingSoon({ phase, about }: { phase: string; about: string }) {
  return (
    <div className="overflow-hidden rounded-[32px] bg-lilac p-6 text-stone-900 sm:p-8">
      <p className="text-sm font-bold">Coming in {phase}</p>
      <p className="mt-2 max-w-xl font-display text-2xl leading-tight font-bold sm:text-3xl">
        {about}
      </p>
      <div aria-hidden className="mt-8 flex h-40 items-end gap-2 sm:gap-3">
        {PREVIEW_BARS.map((height, i) => (
          <div
            key={i}
            className={`flex-1 rounded-full ${i === 3 ? 'bg-stone-900' : 'bg-stone-50/70'}`}
            style={{ height: `${height}%` }}
          />
        ))}
      </div>
    </div>
  )
}
