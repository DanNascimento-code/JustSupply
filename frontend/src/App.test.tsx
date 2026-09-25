import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { ConsumerProduct, ConsumerSearchResponse } from './types/consumer'

const product: ConsumerProduct = {
  barcode: '7891000100103',
  name: 'Dark chocolate',
  brand: 'Example Foods',
  image_url: 'https://images.openfoodfacts.org/product.jpg',
  source_url: 'https://world.openfoodfacts.org/product/7891000100103',
  source_name: 'Open Food Facts',
  last_updated_at: '2026-09-14T12:00:00Z',
  evidence_coverage_percent: 50,
  research: null,
  assessments: [
    {
      dimension: 'vegan_composition',
      title: 'Vegan composition',
      status: 'supported',
      finding: 'The ingredient analysis supports a vegan formulation.',
      evidence_scope: 'product',
      verification: 'catalog_data',
      verification_note: 'Reported by the product catalog.',
      limitations: 'Catalog data may be incomplete.',
      sources: [
        {
          title: 'Dark chocolate — Open Food Facts',
          provider_name: 'Open Food Facts',
          url: 'https://world.openfoodfacts.org/product/7891000100103',
          published_at: '2026-09-14T12:00:00Z',
          source_location: 'Ingredient analysis',
        },
      ],
    },
    {
      dimension: 'environmental_impact',
      title: 'Environmental impact',
      status: 'mixed',
      finding: 'Open Food Facts reports Green-Score C.',
      evidence_scope: 'product',
      verification: 'catalog_data',
      verification_note: 'Reported by the product catalog.',
      limitations: 'Catalog data may be incomplete.',
      sources: [],
    },
    {
      dimension: 'women_workers',
      title: 'Women workers',
      status: 'not_disclosed',
      finding: 'No research has been run.',
      evidence_scope: 'brand',
      verification: 'unverified',
      verification_note: 'No public-source research has been completed.',
      limitations: 'Run AI-assisted research.',
      sources: [],
    },
    {
      dimension: 'minority_inclusion',
      title: 'Minority inclusion',
      status: 'not_disclosed',
      finding: 'No research has been run.',
      evidence_scope: 'brand',
      verification: 'unverified',
      verification_note: 'No public-source research has been completed.',
      limitations: 'Run AI-assisted research.',
      sources: [],
    },
  ],
}

const searchResult: ConsumerSearchResponse = {
  query: product.barcode,
  query_type: 'barcode',
  total: 1,
  disclaimer: 'Inspect every source.',
  items: [product],
}

const researchedProduct: ConsumerProduct = {
  ...product,
  evidence_coverage_percent: 75,
  research: {
    researched_at: '2026-09-25T12:00:00Z',
    model_name: 'gemini-test',
    source_count: 2,
  },
  assessments: product.assessments.map((assessment) =>
    assessment.dimension === 'women_workers'
      ? {
          ...assessment,
          status: 'supported',
          finding: 'Two public sources describe a leadership program.',
          verification: 'multiple_sources',
          verification_note: 'Backed by two or more public sources.',
          limitations: null,
          sources: [
            {
              title: 'Independent report',
              provider_name: 'example.org',
              url: 'https://example.org/report',
              published_at: null,
              source_location: 'Gemini grounded web research',
            },
          ],
        }
      : assessment,
  ),
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function renderApp() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <App />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  window.localStorage.clear()
  window.history.pushState({}, '', '/')
})

describe('consumer evidence experience', () => {
  it('opens directly on the consumer search without calling the API', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    renderApp()
    expect(screen.getByRole('heading', { name: 'Look beyond the label.' })).toBeInTheDocument()
    expect(screen.queryByText('Suppliers')).not.toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('switches the complete interface to Brazilian Portuguese and Latin American Spanish', async () => {
    vi.stubGlobal('fetch', vi.fn())
    const user = userEvent.setup()
    renderApp()

    await user.click(screen.getByRole('button', { name: 'PT-BR' }))
    expect(screen.getByRole('heading', { name: 'Vá além do rótulo.' })).toBeInTheDocument()
    expect(screen.getByLabelText('Produto, marca ou código de barras')).toBeInTheDocument()
    expect(document.title).toBe('JustSupply | Evidências para consumidores')

    await user.click(screen.getByRole('button', { name: 'ES-LATAM' }))
    expect(screen.getByRole('heading', { name: 'Mira más allá de la etiqueta.' })).toBeInTheDocument()
    expect(screen.getByLabelText('Producto, marca o código de barras')).toBeInTheDocument()
    expect(document.title).toBe('JustSupply | Evidencia para consumidores')
  })

  it('shows product image and transparent evidence labels', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(searchResult)))
    const user = userEvent.setup()
    renderApp()
    await user.type(screen.getByLabelText('Product, brand, or barcode'), product.barcode)
    await user.click(screen.getByRole('button', { name: 'Search evidence' }))
    expect(await screen.findByRole('heading', { name: product.name })).toBeInTheDocument()
    expect(screen.getByAltText(`${product.name} package`)).toBeInTheDocument()
    expect(screen.getAllByText('Catalog data')).not.toHaveLength(0)
    expect(screen.getAllByText('Unverified')).not.toHaveLength(0)
  })

  it('researches public sources and answers a grounded question', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString()
      if (url.includes('/research')) {
        return jsonResponse({ product: researchedProduct, cached: false })
      }
      if (url.endsWith('/ask')) {
        return jsonResponse({
          question: 'What evidence exists about women workers?',
          answer: 'Two sources describe a leadership program. [1]',
          insufficient_evidence: false,
          citations: [
            {
              number: 1,
              evidence_id: '77075032-6088-4b20-9d6d-ff250395518d',
              title: 'Independent report',
              provider_name: 'example.org',
              url: 'https://example.org/report',
              excerpt: 'The report describes a leadership program.',
              similarity: 0.91,
            },
          ],
          retrieval_model: 'gemini-embedding-test',
          generation_model: 'gemini-test',
          prompt_version: 'consumer-evidence-rag-v1',
        })
      }
      return jsonResponse(searchResult)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderApp()
    await user.type(screen.getByLabelText('Product, brand, or barcode'), product.barcode)
    await user.click(screen.getByRole('button', { name: 'Search evidence' }))
    await user.click(await screen.findByRole('button', { name: 'Research with Gemini' }))
    expect(await screen.findByText('2 cited sources researched')).toBeInTheDocument()
    await user.type(
      screen.getByLabelText(`Question about ${product.name}`),
      'What evidence exists about women workers?',
    )
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText(/Two sources describe a leadership program/)).toBeInTheDocument()
    expect(screen.getByText(/91% match/)).toBeInTheDocument()
  })
})
