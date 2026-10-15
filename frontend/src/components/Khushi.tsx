import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Briefing } from '../lib/api'

export function KhushiAvatar({ size = 40 }: { size?: number }) {
  return (
    <div
      aria-hidden
      className="flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-fuchsia-500 to-indigo-500 font-semibold text-white shadow-sm"
      style={{ width: size, height: size, fontSize: size * 0.42 }}
    >
      K
    </div>
  )
}

const TONE = {
  info: '',
  warn: 'text-amber-700 dark:text-amber-300',
  good: 'text-emerald-700 dark:text-emerald-300',
}

/** Khushi's speech bubble with her briefing. `refreshKey` reloads it after changes. */
export default function KhushiCard({ refreshKey = 0 }: { refreshKey?: number }) {
  const [b, setB] = useState<Briefing | null>(null)

  useEffect(() => {
    api.get<Briefing>('/khushi/briefing').then(setB, () => setB(null))
  }, [refreshKey])

  if (!b) return null
  return (
    <div className="flex gap-3">
      <KhushiAvatar />
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm border border-zinc-200 bg-white px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900">
        <p className="font-medium">{b.greeting}</p>
        <ul className="mt-1 space-y-1 text-sm">
          {b.lines.map((line, i) => (
            <li key={i} className={TONE[line.tone]}>
              {line.link ? (
                <Link to={line.link} className="hover:underline">
                  {line.text}
                </Link>
              ) : (
                line.text
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
