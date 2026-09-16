import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createBrandClaim,
  listBrandClaims,
  listEvidenceBrands,
  reviewBrandClaim,
} from '../api/brandEvidence'
import {
  ingestEvidenceDocument,
  listEvidenceDocuments,
  reviewExtractedFinding,
} from '../api/documentIngestion'
import { askBrandEvidence, indexEvidenceDocument } from '../api/rag'
import { BrandClaimList } from '../components/BrandClaimList'
import { BrandEvidenceForm } from '../components/BrandEvidenceForm'
import { DocumentIngestionWorkspace } from '../components/DocumentIngestionWorkspace'
import { RagAssistant } from '../components/RagAssistant'
import type {
  BrandEvidenceInput,
  ReviewDecision,
} from '../types/brandEvidence'
import type {
  EvidenceDocumentInput,
  FindingReviewDecision,
} from '../types/documentIngestion'

const brandsQueryKey = ['evidence-brands'] as const

export function EvidenceWorkspacePage() {
  const queryClient = useQueryClient()
  const [chosenBrandId, setChosenBrandId] = useState('')
  const brandsQuery = useQuery({
    queryKey: brandsQueryKey,
    queryFn: listEvidenceBrands,
  })
  const brands = brandsQuery.data?.items ?? []
  const selectedBrandId = brands.some((brand) => brand.id === chosenBrandId)
    ? chosenBrandId
    : (brands[0]?.id ?? '')
  const claimsQueryKey = ['brand-claims', selectedBrandId] as const
  const claimsQuery = useQuery({
    queryKey: claimsQueryKey,
    queryFn: () => listBrandClaims(selectedBrandId),
    enabled: selectedBrandId.length > 0,
  })
  const documentsQueryKey = ['evidence-documents', selectedBrandId] as const
  const documentsQuery = useQuery({
    queryKey: documentsQueryKey,
    queryFn: () => listEvidenceDocuments(selectedBrandId),
    enabled: selectedBrandId.length > 0,
  })
  const createMutation = useMutation({
    mutationFn: ({
      brandId,
      payload,
    }: {
      brandId: string
      payload: BrandEvidenceInput
    }) => createBrandClaim(brandId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: claimsQueryKey })
    },
  })
  const reviewMutation = useMutation({
    mutationFn: ({
      claimId,
      decision,
    }: {
      claimId: string
      decision: ReviewDecision
    }) => reviewBrandClaim(claimId, decision),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: claimsQueryKey })
    },
  })
  const documentMutation = useMutation({
    mutationFn: (input: EvidenceDocumentInput) =>
      ingestEvidenceDocument(selectedBrandId, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: documentsQueryKey })
    },
  })
  const ragMutation = useMutation({
    mutationFn: (question: string) => askBrandEvidence(selectedBrandId, question),
  })
  const indexMutation = useMutation({
    mutationFn: indexEvidenceDocument,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: documentsQueryKey })
    },
  })
  const findingReviewMutation = useMutation({
    mutationFn: ({
      findingId,
      decision,
    }: {
      findingId: string
      decision: FindingReviewDecision
    }) => reviewExtractedFinding(findingId, decision),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: documentsQueryKey }),
        queryClient.invalidateQueries({ queryKey: claimsQueryKey }),
      ])
    },
  })

  async function handleCreate(payload: BrandEvidenceInput) {
    await createMutation.mutateAsync({ brandId: selectedBrandId, payload })
  }

  function handleReview(claimId: string, decision: ReviewDecision) {
    reviewMutation.mutate({ claimId, decision })
  }

  async function handleDocumentUpload(input: EvidenceDocumentInput) {
    await documentMutation.mutateAsync(input)
  }

  function handleFindingReview(
    findingId: string,
    decision: FindingReviewDecision,
  ) {
    findingReviewMutation.mutate({ findingId, decision })
  }

  async function handleRagQuestion(question: string) {
    await ragMutation.mutateAsync(question)
  }

  function handleBrandChange(brandId: string) {
    ragMutation.reset()
    setChosenBrandId(brandId)
  }

  return (
    <main id="top">
      <section className="evidence-workspace-hero">
        <div>
          <p className="eyebrow">JustSupply Pro · Human in the loop</p>
          <h1>Turn sources into reviewable evidence.</h1>
          <p className="hero-description">
            Upload a source, let AI propose narrow social findings, and decide
            whether the evidence is strong enough to publish for consumers.
          </p>
        </div>
        <div className="workflow-summary" aria-label="Evidence workflow">
          <span>Document</span><i aria-hidden="true">→</i>
          <span>AI extraction</span><i aria-hidden="true">→</i>
          <span>Human review</span><i aria-hidden="true">→</i>
          <span>Consumer</span>
        </div>
      </section>

      {brandsQuery.isError ? (
        <p className="inline-error" role="alert">{brandsQuery.error.message}</p>
      ) : null}

      {!brandsQuery.isPending && brands.length === 0 ? (
        <div className="evidence-onboarding panel">
          <span className="empty-icon" aria-hidden="true">01</span>
          <h2>Search a product in Consumer first</h2>
          <p>
            A Consumer search creates the product and its primary brand. Return
            here afterwards to attach social evidence to that known identity.
          </p>
        </div>
      ) : (
        <>
          <DocumentIngestionWorkspace
            brands={brands}
            selectedBrandId={selectedBrandId}
            documents={documentsQuery.data?.items ?? []}
            isLoading={documentsQuery.isPending}
            isUploading={documentMutation.isPending}
            reviewingFindingId={
              findingReviewMutation.isPending
                ? findingReviewMutation.variables.findingId
                : undefined
            }
            indexingDocumentId={
              indexMutation.isPending ? indexMutation.variables : undefined
            }
            uploadError={documentMutation.error}
            reviewError={findingReviewMutation.error ?? documentsQuery.error}
            onBrandChange={handleBrandChange}
            onUpload={handleDocumentUpload}
            onReview={handleFindingReview}
            onIndex={(documentId) => indexMutation.mutate(documentId)}
          />
          <RagAssistant
            brandName={brands.find((brand) => brand.id === selectedBrandId)?.name}
            answer={ragMutation.data}
            indexedChunkCount={(documentsQuery.data?.items ?? []).reduce(
              (total, document) => total + document.chunk_count,
              0,
            )}
            isAsking={ragMutation.isPending}
            error={ragMutation.error ?? indexMutation.error}
            onAsk={handleRagQuestion}
          />
          <div className="manual-evidence-divider">
            <span>Manual fallback</span>
            <p>Use this when a source is not suitable for document extraction.</p>
          </div>
          <section className="evidence-workspace-grid">
            <BrandEvidenceForm
              brands={brands}
              selectedBrandId={selectedBrandId}
              isSubmitting={createMutation.isPending}
              onBrandChange={handleBrandChange}
              onSubmit={handleCreate}
            />
            <BrandClaimList
              claims={claimsQuery.data?.items ?? []}
              isLoading={brandsQuery.isPending || claimsQuery.isPending}
              reviewError={reviewMutation.error}
              reviewingId={
                reviewMutation.isPending ? reviewMutation.variables.claimId : undefined
              }
              onReview={handleReview}
            />
          </section>
        </>
      )}
    </main>
  )
}
