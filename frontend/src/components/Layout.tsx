import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import ChatPanel from './ChatPanel'
import { KhushiAvatar } from './Khushi'

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/organize', label: 'Organize' },
  { to: '/files', label: 'Files' },
  { to: '/tasks', label: 'Assignments' },
  { to: '/progress', label: 'Progress' },
  { to: '/chat', label: 'Chat' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
  const [chatOpen, setChatOpen] = useState(false)
  const onChatPage = useLocation().pathname === '/chat'

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-zinc-200 p-4 md:w-56 md:border-r md:border-b-0 dark:border-zinc-800">
        <div className="mb-4 text-lg font-semibold tracking-tight">
          context<span className="text-accent">.os</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto md:flex-col">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm whitespace-nowrap ${
                  isActive
                    ? 'bg-accent-soft text-accent font-medium dark:bg-zinc-800'
                    : 'text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-4 md:p-8">
        <Outlet />
      </main>

      {/* Khushi is one click away on every page. */}
      {!onChatPage && (
        <>
          {chatOpen && (
            <div className="fixed inset-0 z-40 flex flex-col bg-white sm:inset-auto sm:right-5 sm:bottom-24 sm:h-[560px] sm:w-[380px] sm:rounded-2xl sm:border sm:border-zinc-200 sm:shadow-2xl dark:bg-zinc-950 sm:dark:border-zinc-800">
              <div className="flex items-center gap-2 border-b border-zinc-200 px-3 py-2 dark:border-zinc-800">
                <KhushiAvatar size={28} />
                <span className="font-medium">Khushi</span>
                <Link
                  to="/chat"
                  onClick={() => setChatOpen(false)}
                  className="ml-auto text-xs text-zinc-500 hover:underline"
                >
                  Full screen
                </Link>
                <button
                  onClick={() => setChatOpen(false)}
                  aria-label="Close chat"
                  className="rounded px-2 text-lg leading-none text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  ×
                </button>
              </div>
              <div className="min-h-0 flex-1">
                <ChatPanel compact />
              </div>
            </div>
          )}
          <button
            onClick={() => setChatOpen((o) => !o)}
            aria-label={chatOpen ? 'Close Khushi' : 'Talk to Khushi'}
            title="Talk to Khushi"
            className={`fixed right-5 bottom-5 z-50 rounded-full shadow-lg transition hover:scale-105 ${chatOpen ? 'hidden sm:block' : ''}`}
          >
            <KhushiAvatar size={56} />
          </button>
        </>
      )}
    </div>
  )
}
