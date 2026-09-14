import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Supplier } from './types/supplier'

const createdSupplier: Supplier = {
  id: 'f7f79cf1-11fb-4f50-a5ad-67541760ff07',
  legal_name: 'Cooperativa Cacau Justo',
  country_code: 'BR',
  website: 'https://example.org/',
  commodities: ['cocoa'],
  created_at: '2026-09-14T12:00:00Z',
  updated_at: '2026-09-14T12:00:00Z',
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderApp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('supplier workspace', () => {
  it('shows the empty state returned by the API', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ items: [], total: 0 })),
    )

    renderApp()

    expect(await screen.findByText('No suppliers yet')).toBeInTheDocument()
    expect(screen.getByText('Evidence API connected')).toBeInTheDocument()
  })

  it('creates a supplier and refreshes the directory', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [], total: 0 }))
      .mockResolvedValueOnce(jsonResponse(createdSupplier, 201))
      .mockResolvedValueOnce(
        jsonResponse({ items: [createdSupplier], total: 1 }),
      )
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    renderApp()
    await screen.findByText('No suppliers yet')

    await user.type(
      screen.getByLabelText('Legal name'),
      'Cooperativa Cacau Justo',
    )
    await user.type(screen.getByLabelText('Country code'), 'br')
    await user.type(screen.getByLabelText('Website'), 'https://example.org')
    await user.click(screen.getByLabelText('cocoa'))
    await user.click(screen.getByRole('button', { name: 'Add supplier' }))

    expect(
      await screen.findByRole('heading', { name: 'Cooperativa Cacau Justo' }),
    ).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })
})
