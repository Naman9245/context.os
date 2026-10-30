import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Bundled with the app, so the fonts work offline and nothing is fetched from Google.
import '@fontsource-variable/figtree'
import '@fontsource-variable/gabarito'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
