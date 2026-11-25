import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { installAuthenticatedFetch } from './utils/apiAuth'
import '@fontsource/geist-sans/400.css'
import '@fontsource/geist-sans/500.css'
import '@fontsource/geist-sans/600.css'
import '@fontsource/geist-sans/700.css'
import '@fontsource/geist-sans/800.css'
import './index.css'
import App from './App.tsx'

installAuthenticatedFetch()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
