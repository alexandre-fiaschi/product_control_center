import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { toast } from 'sonner'
import './index.css'
import App from './App'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
    mutations: {
      retry: 0,
    },
  },
})

// Global error handler — show toast for any failed query/mutation
queryClient.getQueryCache().subscribe((event) => {
  if (event.type === 'updated' && event.query.state.status === 'error') {
    const err = event.query.state.error as any
    const queryKey = event.query.queryKey as string[]
    const endpoint = queryKey.join(' / ')
    const status = err?.status ? `${err.status}` : 'Network error'
    const detail = err?.detail || err?.message || 'Unknown error'
    const step = err?.step ? ` · Step: ${err.step}` : ''

    toast.error(`${detail}`, {
      description: `${status} — ${endpoint}${step}`,
      duration: Infinity,
      dismissible: true,
      style: {
        backgroundColor: 'rgba(220, 38, 38, 0.15)',
        border: '1px solid rgba(239, 68, 68, 0.4)',
        color: '#fca5a5',
      },
      descriptionClassName: 'text-red-400/70',
    })
  }
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
