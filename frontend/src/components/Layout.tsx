import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import ChatPanel from './ChatPanel'
import {
  ChartIcon,
  ChatIcon,
  ChecklistIcon,
  FolderIcon,
  GearIcon,
  HomeIcon,
  SortIcon,
} from './icons'
import { KhushiAvatar } from './Khushi'
import UpdateBanner from './UpdateBanner'

const NAV = [
  { to: '/', label: 'Dashboard', icon: HomeIcon },
  { to: '/organize', label: 'Organize', icon: SortIcon },
  { to: '/files', label: 'Files', icon: FolderIcon },
  { to: '/tasks', label: 'Assignments', icon: ChecklistIcon },
  { to: '/progress', label: 'Progress', icon: ChartIcon },
  { to: '/chat', label: 'Chat', icon: ChatIcon },
  { to: '/settings', label: 'Settings', icon: GearIcon },
]

function Wordmark({ dot }: { dot: string }) {
  return (
    <span className="font-display font-extrabold tracking-tight">
      context<span className={dot}>.os</span>
    </span>
  )
}

export default function Layout() {
  const [chatOpen, setChatOpen] = useState(false)
  const onChatPage = useLocation().pathname === '/chat'

  return (
    <div className="min-h-screen md:flex">
      <UpdateBanner />
      {/* Wide screens: a dark rail on the left. Phones: the same links as a bar along the bottom. */}
      <aside className="fixed inset-x-3 bottom-3 z-30 md:sticky md:inset-x-auto md:top-0 md:bottom-auto md:h-screen md:w-64 md:shrink-0 md:p-4">
        <nav
          aria-label="Main"
          className="flex items-center justify-between rounded-full bg-stone-900 p-1.5 text-stone-300 shadow-xl shadow-stone-900/20 md:h-full md:flex-col md:items-stretch md:justify-start md:gap-1 md:rounded-[32px] md:p-4 md:shadow-none dark:ring-1 dark:ring-stone-800"
        >
          <Link to="/" className="mb-8 hidden px-3 pt-2 text-2xl text-stone-50 md:block">
            <Wordmark dot="text-sun" />
          </Link>
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              aria-label={label}
              title={label}
              className={({ isActive }) =>
                `flex h-10 w-10 items-center justify-center gap-3 rounded-full text-sm font-semibold transition sm:h-11 sm:w-11 md:h-auto md:w-auto md:justify-start md:px-4 md:py-3 ${
                  isActive ? 'bg-sun text-stone-900' : 'hover:bg-white/10 hover:text-stone-50'
                }`
              }
            >
              <Icon />
              <span className="hidden md:inline">{label}</span>
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 px-4 pt-6 pb-28 md:px-8 md:pt-10 md:pb-12">
        <Link to="/" className="mb-6 inline-block text-xl md:hidden">
          <Wordmark dot="text-accent" />
        </Link>
        <Outlet />
      </main>

      {/* Khushi is one click away on every page. */}
      {!onChatPage && (
        <>
          {chatOpen && (
            <div className="fixed inset-0 z-40 flex flex-col bg-stone-50 sm:inset-auto sm:right-5 sm:bottom-40 sm:h-[580px] sm:max-h-[calc(100vh-12rem)] sm:w-[400px] sm:overflow-hidden sm:rounded-[28px] sm:border sm:border-stone-200 sm:shadow-2xl sm:shadow-stone-900/15 md:bottom-24 dark:bg-stone-950 sm:dark:border-stone-800">
              <div className="flex items-center gap-2.5 bg-sun px-4 py-3 text-stone-900">
                <KhushiAvatar size={32} />
                <span className="font-display text-lg font-bold">Khushi</span>
                <Link
                  to="/chat"
                  onClick={() => setChatOpen(false)}
                  className="ml-auto rounded-full px-2.5 py-1 text-xs font-semibold hover:bg-stone-900/10"
                >
                  Full screen
                </Link>
                <button
                  onClick={() => setChatOpen(false)}
                  aria-label="Close chat"
                  className="flex h-8 w-8 items-center justify-center rounded-full text-xl leading-none hover:bg-stone-900/10"
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
            className={`fixed right-5 bottom-24 z-50 rounded-full shadow-lg shadow-stone-900/20 transition hover:scale-105 md:bottom-6 ${chatOpen ? 'hidden sm:block' : ''}`}
          >
            <KhushiAvatar size={56} />
          </button>
        </>
      )}
    </div>
  )
}
