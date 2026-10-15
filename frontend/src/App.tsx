import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Page, { ComingSoon } from './components/Page'
import Dashboard from './pages/Dashboard'
import Files from './pages/Files'
import Organize from './pages/Organize'
import Settings from './pages/Settings'

// Pages that do not exist yet render a placeholder naming the phase that builds them.
const PLACEHOLDERS = [
  { path: 'tasks', title: 'Tasks', subtitle: 'Deadlines and assignments.', phase: 'Phase 3' },
  { path: 'progress', title: 'Progress', subtitle: 'How your week went.', phase: 'Phase 4' },
  { path: 'chat', title: 'Chat', subtitle: 'Ask ContextOS to do things.', phase: 'Phase 5' },
]

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="organize" element={<Organize />} />
          <Route path="files" element={<Files />} />
          <Route path="settings" element={<Settings />} />
          {PLACEHOLDERS.map((p) => (
            <Route
              key={p.path}
              path={p.path}
              element={
                <Page title={p.title} subtitle={p.subtitle}>
                  <ComingSoon phase={p.phase} />
                </Page>
              }
            />
          ))}
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
