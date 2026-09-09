import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { AppErrorBoundary } from './components/AppErrorBoundary'
import './index.css'

const qc = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

/**
 * A versão anterior registrava um Service Worker que armazenava HTML e bundles
 * da Vite. Em deploys novos isso podia deixar o navegador com um shell antigo
 * referenciando chunks que já não existiam, resultando em tela branca.
 *
 * Por enquanto priorizamos estabilidade: removemos registrations e caches
 * antigos. O manifest continua disponível; PWA offline poderá voltar depois
 * usando uma estratégia de cache versionada/Workbox.
 */
async function clearLegacyAppCache() {
  if ('serviceWorker' in navigator) {
    try {
      const registrations = await navigator.serviceWorker.getRegistrations()
      await Promise.all(registrations.map((registration) => registration.unregister()))
    } catch (error) {
      console.warn('[BeeSys Lead Search] Não foi possível remover Service Worker antigo', error)
    }
  }

  if ('caches' in window) {
    try {
      const keys = await caches.keys()
      await Promise.all(
        keys
          .filter((key) => key.startsWith('beesys-lead-'))
          .map((key) => caches.delete(key)),
      )
    } catch (error) {
      console.warn('[BeeSys Lead Search] Não foi possível limpar cache antigo', error)
    }
  }
}

void clearLegacyAppCache()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <QueryClientProvider client={qc}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </AppErrorBoundary>
  </React.StrictMode>,
)
