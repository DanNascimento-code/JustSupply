import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { ConsumerProduct, ConsumerSearchResponse } from './types/consumer'

const product: ConsumerProduct = {
  barcode: '7891000100103',
  name: 'Dark chocolate',
  brand: 'Example Foods',
  category: null,
  catalog_product: true,
  image_url: 'https://images.openfoodfacts.org/product.jpg',
  source_url: 'https://world.openfoodfacts.org/product/7891000100103',
  source_name: 'Open Food Facts',
  last_updated_at: '2026-09-14T12:00:00Z',
  evidence_coverage_percent: 50,
  research: null,
  community_reports: { total: 0, pending_review: 0, assessment_counts: {} },
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
  query: product.barcode!,
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
    legal_entity: null,
    parent_company: null,
    jurisdiction: null,
    entity_source_url: null,
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
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (input.toString().includes('/research')) {
        return jsonResponse({ product, cached: true })
      }
      return jsonResponse(searchResult)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderApp()
    await user.type(screen.getByLabelText('Product, brand, or barcode'), product.barcode!)
    await user.click(screen.getByRole('button', { name: 'Search evidence' }))
    expect(await screen.findByRole('heading', { name: product.name })).toBeInTheDocument()
    expect(screen.getByAltText(`${product.name} package`)).toBeInTheDocument()
    expect(screen.getAllByText('Catalog data')).not.toHaveLength(0)
    expect(screen.getAllByText('Unverified')).not.toHaveLength(0)
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([input]) => input.toString().includes('/research'))).toBe(true)
    })
  })

  it('researches public sources and answers a grounded question', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void init
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
          cached: false,
        })
      }
      return jsonResponse(searchResult)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderApp()
    await user.type(screen.getByLabelText('Product, brand, or barcode'), product.barcode!)
    await user.click(screen.getByRole('button', { name: 'Search evidence' }))
    expect(await screen.findByText('2 public sources reviewed')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Research public sources' })).not.toBeInTheDocument()
    await user.type(
      screen.getByLabelText(`Question about ${product.name}`),
      'What evidence exists about women workers?',
    )
    await user.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText(/Two sources describe a leadership program/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Independent report/ })).toBeInTheDocument()
    expect(screen.queryByText(/91% match/)).not.toBeInTheDocument()
  })

  it('keeps Ask available when automatic research needs a retry', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = input.toString()
      if (url.includes('/research')) {
        return jsonResponse({ detail: 'Research temporarily unavailable.' }, 503)
      }
      if (url.endsWith('/ask')) {
        return jsonResponse({
          question: 'What evidence is available?',
          answer: 'The backend retried research before answering.',
          insufficient_evidence: false,
          citations: [],
          retrieval_model: 'gemini-embedding-test',
          generation_model: 'gemini-test',
          prompt_version: 'consumer-evidence-rag-v1',
          cached: false,
        })
      }
      return jsonResponse(searchResult)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderApp()

    await user.type(screen.getByLabelText('Product, brand, or barcode'), product.barcode!)
    await user.click(screen.getByRole('button', { name: 'Search evidence' }))
    const askButton = await screen.findByRole('button', { name: 'Ask' })
    await waitFor(() => expect(askButton).toBeEnabled())
    await user.type(
      screen.getByLabelText(`Question about ${product.name}`),
      'What evidence is available?',
    )
    await user.click(askButton)

    expect(await screen.findByText('The backend retried research before answering.'))
      .toBeInTheDocument()
  })

  it('submits product assessments as an unverified community report', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      void init
      if (input.toString().includes('/consumer/reports')) {
        return jsonResponse({
          id: 'c0f919a1-e9c4-40eb-9aec-43344509833b',
          product_name: 'Example drink',
          barcode: null,
          category: 'beverages',
          assessments: [{ dimension: 'environmental_impact', outcome: 'negative' }],
          status: 'published_unverified',
          has_photo: false,
          document_count: 0,
          submitted_at: '2026-09-28T20:00:00Z',
          notice: 'Your report was published as unverified community content.',
        }, 201)
      }
      return jsonResponse(searchResult)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    renderApp()

    await user.type(screen.getByLabelText(/Product or brand name/), 'Example drink')
    await user.selectOptions(screen.getByLabelText('Food category'), 'beverages')
    await user.click(
      within(screen.getByRole('group', { name: 'Is this product sustainable?' }))
        .getByLabelText('No'),
    )
    await user.type(
      screen.getByLabelText('Observations'),
      'The package makes an environmental claim without identifying a source.',
    )
    await user.type(
      screen.getByLabelText('Supporting source links (optional, recommended) 1'),
      'https://example.org/source-one',
    )
    await user.click(screen.getByRole('button', { name: 'Add another source link' }))
    await user.type(
      screen.getByLabelText('Supporting source links (optional, recommended) 2'),
      'https://example.org/source-two',
    )
    await user.click(screen.getByRole('button', { name: 'Publish unverified report' }))

    expect(
      await screen.findByText('Your report was published as unverified community content.'),
    ).toBeInTheDocument()
    const submitted = fetchMock.mock.calls.find(([input]) => input.toString().includes('/consumer/reports'))
    expect(submitted).toBeDefined()
    const submittedBody = submitted?.[1]?.body
    expect(submittedBody).toBeInstanceOf(FormData)
    if (!(submittedBody instanceof FormData)) throw new Error('Expected multipart form data.')
    expect(submittedBody.get('category')).toBe('beverages')
    expect(submittedBody.getAll('evidence_urls')).toEqual([
      'https://example.org/source-one',
      'https://example.org/source-two',
    ])
  })

  it('shows public unverified reports and their supporting material', async () => {
    window.history.pushState({}, '', '/community-reports')
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({
      total: 1,
      disclaimer: 'These reports are user-submitted and unverified.',
      items: [{
        id: 'f42f350b-a83d-4c43-81bd-b476800a54e8',
        product_name: 'Example drink',
        barcode: '7891000100103',
        category: 'beverages',
        assessments: [{ dimension: 'environmental_impact', outcome: 'negative' }],
        observations: 'The environmental claim does not identify a supporting study.',
        evidence_urls: [
          'https://example.org/source',
          'https://news.example.org/source',
        ],
        photo_url: '/api/v1/consumer/reports/f42f350b-a83d-4c43-81bd-b476800a54e8/photo',
        documents: [{
          id: 'a5c0cdde-3f0d-4979-8233-1b312f4dc1ac',
          file_name: 'evidence.pdf',
          mime_type: 'application/pdf',
          download_url: '/api/v1/consumer/reports/f42f350b-a83d-4c43-81bd-b476800a54e8/documents/a5c0cdde-3f0d-4979-8233-1b312f4dc1ac',
        }],
        status: 'published_unverified',
        published_at: '2026-09-28T20:00:00Z',
      }],
    }))
    vi.stubGlobal('fetch', fetchMock)

    renderApp()
    const user = userEvent.setup()

    expect(await screen.findByRole('heading', { name: 'Example drink' })).toBeInTheDocument()
    expect(screen.getByText(/does not identify a supporting study/)).toBeInTheDocument()
    expect(screen.getByLabelText('Is this product sustainable?: No')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open submitted source 1 ↗' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open submitted source 2 ↗' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Download evidence.pdf' })).toBeInTheDocument()
    expect(screen.getByText('Unverified community content')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Filter reports by category'), 'beverages')
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('category=beverages'),
        expect.anything(),
      )
    })
  })
})
