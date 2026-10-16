import { useEffect, useState } from 'react'
import { Badge, Card } from './ui'
import { api, type Health } from '../lib/api'

/** Status and install steps for the "Khushi for Chrome" extension. */
export default function ExtensionSettings({ initial }: { initial: Health }) {
  const [health, setHealth] = useState(initial)

  // The extension connects within a minute of being loaded: watch for it.
  useEffect(() => {
    if (health.browser_extension) return
    const t = window.setInterval(() => api.get<Health>('/health').then(setHealth), 5000)
    return () => window.clearInterval(t)
  }, [health.browser_extension])

  return (
    <section>
      <h2 className="font-semibold">Khushi for Chrome</h2>
      <p className="mb-3 text-sm text-zinc-500">
        Khushi can't see inside Chrome on her own. With this extension she keeps one tab per
        site and reuses it ("open YouTube", then "search carryminati", stays in the same tab),
        and she can open the first result when you say "open it" or "play the first video".
        She never touches tabs you opened yourself.
      </p>
      <Card>
        <div className="flex items-center gap-2 text-sm">
          Status:{' '}
          {health.browser_extension ? (
            <Badge tone="good">connected</Badge>
          ) : (
            <Badge>not installed</Badge>
          )}
        </div>
        {!health.browser_extension && (
          <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm">
            <li>
              In Chrome, open <code className="font-mono">chrome://extensions</code>
            </li>
            <li>Turn on <strong>Developer mode</strong> (top right)</li>
            <li>
              Click <strong>Load unpacked</strong> and choose{' '}
              <code className="font-mono break-all">{health.extension_folder}</code>
            </li>
            <li>This page shows "connected" within a minute.</li>
          </ol>
        )}
      </Card>
    </section>
  )
}
