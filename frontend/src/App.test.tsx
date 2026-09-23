import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { BrandClaim } from './types/brandEvidence'
import type { ConsumerSearchResponse } from './types/consumer'
import type {
  DocumentIngestionJob,
  EvidenceDocument,
} from './types/documentIngestion'
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

const consumerResult: ConsumerSearchResponse = {
  query: '7891000100103',
  query_type: 'barcode',
  total: 1,
  disclaimer:
    'JustSupply summarizes available evidence; it does not certify products or brands.',
  items: [
    {
      barcode: '7891000100103',
      name: 'Dark chocolate',
      brand: 'Example Foods',
      image_url: null,
      source_url: 'https://world.openfoodfacts.org/product/7891000100103',
      source_name: 'Open Food Facts',
      last_updated_at: '2026-09-14T12:00:00Z',
      evidence_coverage_percent: 50,
      assessments: [
        {
          dimension: 'vegan_composition',
          title: 'Vegan composition',
          status: 'supported',
          finding: 'The ingredient analysis supports a vegan formulation.',
          evidence_scope: 'product',
          sources: [],
        },
        {
          dimension: 'environmental_impact',
          title: 'Environmental impact',
          status: 'mixed',
          finding: 'Open Food Facts reports a middle Green-Score grade (C).',
          evidence_scope: 'product',
          sources: [],
        },
        {
          dimension: 'women_workers',
          title: 'Women workers',
          status: 'not_disclosed',
          finding: 'No evidence is available.',
          evidence_scope: 'brand',
          sources: [],
        },
        {
          dimension: 'minority_inclusion',
          title: 'Minority inclusion',
          status: 'not_disclosed',
          finding: 'No evidence is available.',
          evidence_scope: 'brand',
          sources: [],
        },
      ],
    },
  ],
}

const pendingBrandClaim: BrandClaim = {
  id: '854c9a26-89d3-46d5-b0a0-381d08534102',
  brand_id: '9c39497c-d18e-42a1-845e-64cf1f7f52fc',
  brand_name: 'Nutella',
  dimension: 'women_workers',
  status: 'supported',
  statement: 'The report describes a leadership program for women workers.',
  review_status: 'pending',
  reviewed_at: null,
  created_at: '2026-09-15T12:00:00Z',
  updated_at: '2026-09-15T12:00:00Z',
  sources: [
    {
      title: '2025 Impact Report',
      provider_name: 'Example Organization',
      url: 'https://example.org/report',
      published_at: '2025-12-01T00:00:00Z',
      source_location: 'page 18',
    },
  ],
}

const extractedDocument: EvidenceDocument = {
  id: 'ad637cba-4450-4b8f-8798-902a34783bd2',
  brand_id: pendingBrandClaim.brand_id,
  brand_name: 'Nutella',
  filename: 'impact-report.txt',
  media_type: 'text/plain',
  byte_size: 120,
  content_sha256: 'a'.repeat(64),
  character_count: 120,
  source_title: '2025 Impact Report',
  source_provider: 'Example Organization',
  source_url: 'https://example.org/report',
  source_type: 'corporate_report',
  published_at: '2025-12-01T00:00:00Z',
  model_name: 'gpt-5-mini',
  prompt_version: 'social-evidence-v1',
  extraction_status: 'completed',
  chunk_count: 1,
  created_at: '2026-09-16T12:00:00Z',
  findings: [
    {
      id: '355bdf9a-11dc-43bf-b106-a010443a3775',
      dimension: 'women_workers',
      status: 'supported',
      statement: 'The report documents participation by women workers.',
      excerpt: 'Women represented 48 percent of program participants.',
      source_location: 'page 12',
      rationale: 'The passage directly reports participation by women.',
      review_status: 'pending',
      reviewed_at: null,
      published_claim_id: null,
    },
  ],
}

const completedIngestionJob: DocumentIngestionJob = {
  id: 'f9482497-e195-4866-ad3f-3679d83ef7ef',
  brand_id: pendingBrandClaim.brand_id,
  document_id: extractedDocument.id,
  filename: extractedDocument.filename,
  source_title: extractedDocument.source_title,
  status: 'completed',
  error_message: null,
  created_at: '2026-09-16T11:59:00Z',
  started_at: '2026-09-16T11:59:01Z',
  completed_at: '2026-09-16T12:00:00Z',
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
  window.history.pushState({}, '', '/')
})

describe('consumer search', () => {
  it('introduces the evidence search without calling the API', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    renderApp()

    expect(
      screen.getByRole('heading', { name: 'Look beyond the label.' }),
    ).toBeInTheDocument()
    expect(screen.getByLabelText('Product, brand, or barcode')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows the four evidence dimensions returned by the API', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(consumerResult))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    renderApp()
    await user.type(
      screen.getByLabelText('Product, brand, or barcode'),
      '7891000100103',
    )
    await user.click(screen.getByRole('button', { name: 'Search evidence' }))

    expect(
      await screen.findByRole('heading', { name: 'Dark chocolate' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Vegan composition')).toBeInTheDocument()
    expect(screen.getByText('Environmental impact')).toBeInTheDocument()
    expect(screen.getByText('Women workers')).toBeInTheDocument()
    expect(screen.getByText('Minority inclusion')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledOnce()
  })
})

describe('supplier workspace', () => {
  it('shows the empty state returned by the API', async () => {
    window.history.pushState({}, '', '/pro/suppliers')
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse({ items: [], total: 0 })),
    )

    renderApp()

    expect(await screen.findByText('No suppliers yet')).toBeInTheDocument()
    expect(screen.getByText('Evidence API connected')).toBeInTheDocument()
  })

  it('creates a supplier and refreshes the directory', async () => {
    window.history.pushState({}, '', '/pro/suppliers')
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

describe('evidence workspace', () => {
  it('asks indexed evidence and shows a cited RAG answer', async () => {
    window.history.pushState({}, '', '/pro/evidence')
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString()
      if (url.endsWith('/api/v1/evidence/brands')) {
        return jsonResponse({
          items: [{ id: pendingBrandClaim.brand_id, name: 'Nutella' }],
          total: 1,
        })
      }
      if (url.endsWith('/documents')) {
        return jsonResponse({ items: [extractedDocument], total: 1 })
      }
      if (url.endsWith('/ingestion-jobs')) {
        return jsonResponse({ items: [completedIngestionJob], total: 1 })
      }
      if (url.endsWith('/claims')) {
        return jsonResponse({ items: [], total: 0 })
      }
      if (url.endsWith('/ask') && init?.method === 'POST') {
        return jsonResponse({
          question: 'What evidence covers women workers?',
          answer: 'The report documents participation by women. [1]',
          insufficient_evidence: false,
          citations: [
            {
              number: 1,
              chunk_id: '77075032-6088-4b20-9d6d-ff250395518d',
              document_id: extractedDocument.id,
              source_title: extractedDocument.source_title,
              source_provider: extractedDocument.source_provider,
              source_url: extractedDocument.source_url,
              filename: extractedDocument.filename,
              source_location: 'page 12',
              excerpt: 'Women represented 48 percent of program participants.',
              similarity: 0.91,
            },
          ],
          retrieval_model: 'text-embedding-3-small',
          generation_model: 'gpt-5-mini',
          prompt_version: 'grounded-rag-v1',
        })
      }
      return jsonResponse({ detail: 'Unexpected request.' }, 500)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    renderApp()
    await screen.findByText(/1 indexed chunks/)
    await user.type(
      screen.getByLabelText('Question about Nutella'),
      'What evidence covers women workers?',
    )
    await user.click(screen.getByRole('button', { name: 'Ask indexed evidence' }))

    expect(
      await screen.findByText('The report documents participation by women. [1]'),
    ).toBeInTheDocument()
    expect(screen.getByText('[1] 2025 Impact Report')).toBeInTheDocument()
    expect(screen.getByText('91% match')).toBeInTheDocument()
  })

  it('creates and approves a social evidence finding', async () => {
    window.history.pushState({}, '', '/pro/evidence')
    let claims: BrandClaim[] = []
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString()
      if (url.endsWith('/api/v1/evidence/brands')) {
        return jsonResponse({
          items: [{ id: pendingBrandClaim.brand_id, name: 'Nutella' }],
          total: 1,
        })
      }
      if (url.includes('/claims/') && init?.method === 'PATCH') {
        claims = [
          {
            ...pendingBrandClaim,
            review_status: 'approved',
            reviewed_at: '2026-09-15T13:00:00Z',
          },
        ]
        return jsonResponse(claims[0])
      }
      if (url.endsWith('/claims') && init?.method === 'POST') {
        claims = [pendingBrandClaim]
        return jsonResponse(pendingBrandClaim, 201)
      }
      if (url.endsWith('/claims')) {
        return jsonResponse({ items: claims, total: claims.length })
      }
      if (url.endsWith('/documents')) {
        return jsonResponse({ items: [], total: 0 })
      }
      if (url.endsWith('/ingestion-jobs')) {
        return jsonResponse({ items: [], total: 0 })
      }
      return jsonResponse({ detail: 'Unexpected request.' }, 500)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    renderApp()
    expect(
      await screen.findByRole('heading', {
        name: 'Turn sources into reviewable evidence.',
      }),
    ).toBeInTheDocument()
    await screen.findByText('No social evidence yet')

    await user.type(
      screen.getByLabelText('Evidence-based statement'),
      pendingBrandClaim.statement,
    )
    await user.type(screen.getByLabelText('Source title'), '2025 Impact Report')
    await user.type(screen.getByLabelText('Publisher'), 'Example Organization')
    await user.type(screen.getByLabelText('Source URL'), 'https://example.org/report')
    await user.click(screen.getByRole('button', { name: 'Save as pending' }))

    expect(
      await screen.findByRole('button', { name: 'Approve for Consumer' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Approve for Consumer' }))

    expect(await screen.findByText('approved')).toBeInTheDocument()
  })

  it('uploads a document and approves an AI finding', async () => {
    window.history.pushState({}, '', '/pro/evidence')
    let documents: EvidenceDocument[] = []
    let jobs: DocumentIngestionJob[] = []
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString()
      if (url.endsWith('/api/v1/evidence/brands')) {
        return jsonResponse({
          items: [{ id: pendingBrandClaim.brand_id, name: 'Nutella' }],
          total: 1,
        })
      }
      if (url.includes('/findings/') && init?.method === 'PATCH') {
        documents = [
          {
            ...extractedDocument,
            findings: [
              {
                ...extractedDocument.findings[0],
                review_status: 'approved',
                reviewed_at: '2026-09-16T13:00:00Z',
              },
            ],
          },
        ]
        return jsonResponse(documents[0].findings[0])
      }
      if (url.endsWith('/documents') && init?.method === 'POST') {
        documents = [extractedDocument]
        jobs = [completedIngestionJob]
        return jsonResponse({ ...completedIngestionJob, status: 'queued' }, 202)
      }
      if (url.endsWith('/documents')) {
        return jsonResponse({ items: documents, total: documents.length })
      }
      if (url.endsWith('/ingestion-jobs')) {
        return jsonResponse({ items: jobs, total: jobs.length })
      }
      if (url.endsWith('/claims')) {
        return jsonResponse({ items: [], total: 0 })
      }
      return jsonResponse({ detail: 'Unexpected request.' }, 500)
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    renderApp()
    await screen.findByText('No document extractions yet')

    await user.upload(
      screen.getByLabelText('Evidence document'),
      new File(
        ['Women represented 48 percent of program participants.'],
        'impact-report.txt',
        { type: 'text/plain' },
      ),
    )
    await user.type(
      screen.getByLabelText('Document source title'),
      '2025 Impact Report',
    )
    await user.type(
      screen.getByLabelText('Document publisher'),
      'Example Organization',
    )
    await user.type(
      screen.getByLabelText('Public source URL'),
      'https://example.org/report',
    )
    const uploadButton = screen.getByRole('button', {
      name: 'Upload and process with AI',
    })
    expect(uploadButton.closest('form')).toBeValid()
    await user.click(uploadButton)

    await waitFor(() => expect(documents).toHaveLength(1))

    expect(
      await screen.findByRole('button', { name: 'Approve AI finding' }),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Approve AI finding' }))

    expect(await screen.findAllByText('approved')).not.toHaveLength(0)
  })
})
