import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import { AuthProvider } from './auth.tsx'
import { PageContextProvider } from './pageContext.tsx'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <PageContextProvider>
          <App />
        </PageContextProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
