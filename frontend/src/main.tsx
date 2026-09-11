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
 * PWA conservadora: o SW atual usa network-first para navegação e cacheia
 * somente bundles Vite versionados. Antes de registrar, removemos apenas
 * registrations legados cujo script não é o /sw.js atual.
 */
async function registerStablePwa(){
  if(!('serviceWorker' in navigator))return
  try{
    const registrations=await navigator.serviceWorker.getRegistrations()
    for(const r of registrations){
      if(!r.active?.scriptURL.endsWith('/sw.js'))await r.unregister()
    }
    if(import.meta.env.PROD)await navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'})
  }catch(error){console.warn('[BeeSys Lead Search] PWA indisponível',error)}
}
void registerStablePwa()

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
