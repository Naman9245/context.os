import { useEffect, useState } from 'react'
import { api, type Health } from '../lib/api'

const CHECK_EVERY_MS = 30_000

/**
 * "ContextOS was updated - Reload". A page keeps running the code it loaded,
 * so after a rebuild it must be reloaded to get the new version; this says so
 * instead of leaving you testing yesterday's code.
 */
export default function UpdateBanner() {
  const [updated, setUpdated] = useState(false)

  useEffect(() => {
    if (!import.meta.env.PROD) return // the dev server reloads by itself
    let loadedBuild: string | null | undefined
    let timer: number | undefined
    const check = async () => {
      window.clearTimeout(timer)
      try {
        const { build } = await api.get<Health>('/health')
        if (loadedBuild === undefined) loadedBuild = build
        else if (build && build !== loadedBuild) return setUpdated(true)
      } catch {
        // the server is restarting - try again later
      }
      timer = window.setTimeout(check, CHECK_EVERY_MS)
    }
    // Coming back to the tab is exactly when an update matters.
    const onVisible = () => document.visibilityState === 'visible' && check()
    check()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  if (!updated) return null
  return (
    <div
      role="status"
      className="fixed top-3 left-1/2 z-[60] flex -translate-x-1/2 items-center gap-3 rounded-full bg-stone-900 px-4 py-2 text-sm text-white shadow-lg dark:bg-stone-50 dark:text-stone-900"
    >
      ContextOS was updated.
      <button
        onClick={() => window.location.reload()}
        className="bg-accent rounded-full px-3 py-1 font-medium text-white"
      >
        Reload
      </button>
    </div>
  )
}
