import type {
  EvidenceDocument,
  EvidenceDocumentInput,
  EvidenceDocumentListResponse,
  ExtractedFinding,
  FindingReviewDecision,
} from '../types/documentIngestion'
import { apiRequest } from './client'

export function listEvidenceDocuments(
  brandId: string,
): Promise<EvidenceDocumentListResponse> {
  return apiRequest<EvidenceDocumentListResponse>(
    `/api/v1/evidence/brands/${brandId}/documents`,
  )
}

export function ingestEvidenceDocument(
  brandId: string,
  input: EvidenceDocumentInput,
): Promise<EvidenceDocument> {
  const formData = new FormData()
  formData.append('file', input.file)
  formData.append('source_title', input.sourceTitle)
  formData.append('source_provider', input.sourceProvider)
  formData.append('source_url', input.sourceUrl)
  formData.append('source_type', input.sourceType)
  if (input.publishedAt) {
    formData.append('published_at', `${input.publishedAt}T00:00:00Z`)
  }
  return apiRequest<EvidenceDocument>(
    `/api/v1/evidence/brands/${brandId}/documents`,
    { method: 'POST', body: formData },
  )
}

export function reviewExtractedFinding(
  findingId: string,
  decision: FindingReviewDecision,
): Promise<ExtractedFinding> {
  return apiRequest<ExtractedFinding>(
    `/api/v1/evidence/findings/${findingId}/review`,
    { method: 'PATCH', body: JSON.stringify({ decision }) },
  )
}
