import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Page, { ComingSoon } from './components/Page'
import Chat from './pages/Chat'
import Dashboard from './pages/Dashboard'
import Files from './pages/Files'
import Organize from './pages/Organize'
import Settings from './pages/Settings'
import Tasks from './pages/Tasks'

// Pages that do not exist yet render a placeholder naming the phase that builds them.
const PLACEHOLDERS = [
  {
    path: 'progress',
    title: 'Progress',
    subtitle: 'How your week went.',
    phase: 'Phase 4',
    about: "A study timer, a chart of where your hours went, and Khushi's take on your week.",
  },
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
          <Route path="tasks" element={<Tasks />} />
          <Route path="chat" element={<Chat />} />
          {PLACEHOLDERS.map((p) => (
            <Route
              key={p.path}
              path={p.path}
              element={
                <Page title={p.title} subtitle={p.subtitle}>
                  <ComingSoon phase={p.phase} about={p.about} />
                </Page>
              }
            />
          ))}
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
