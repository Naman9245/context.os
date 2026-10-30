import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Briefing } from '../lib/api'
import { LINE_TONE } from '../lib/labels'

export function KhushiAvatar({ size = 40 }: { size?: number }) {
  return (
    <div
      aria-hidden
      className="flex shrink-0 items-center justify-center rounded-full bg-sun font-display font-extrabold text-stone-900 ring-2 ring-stone-900"
      style={{ width: size, height: size, fontSize: size * 0.46 }}
    >
      K
    </div>
  )
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
      <KhushiAvatar size={44} />
      <div className="min-w-0 flex-1 rounded-[24px] rounded-tl-md bg-haze px-5 py-4 text-stone-900 dark:bg-stone-900 dark:text-stone-100 dark:ring-1 dark:ring-stone-800">
        <p className="font-display text-lg font-bold">{b.greeting}</p>
        <ul className="mt-1.5 space-y-1 text-sm">
          {b.lines.map((line, i) => (
            <li key={i} className={LINE_TONE[line.tone]}>
              {line.link ? (
                <Link to={line.link} className="font-semibold underline-offset-2 hover:underline">
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
