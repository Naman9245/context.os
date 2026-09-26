import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/', label: 'Dashboard' },
  { to: '/organize', label: 'Organize' },
  { to: '/files', label: 'Files' },
  { to: '/tasks', label: 'Tasks' },
  { to: '/progress', label: 'Progress' },
  { to: '/chat', label: 'Chat' },
  { to: '/settings', label: 'Settings' },
]

export default function Layout() {
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
    </div>
  )
}
