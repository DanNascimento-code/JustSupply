import type {
  DocumentIngestionJob,
  DocumentIngestionJobListResponse,
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
): Promise<DocumentIngestionJob> {
  const formData = new FormData()
  formData.append('file', input.file)
  formData.append('source_title', input.sourceTitle)
  formData.append('source_provider', input.sourceProvider)
  formData.append('source_url', input.sourceUrl)
  formData.append('source_type', input.sourceType)
  if (input.publishedAt) {
    formData.append('published_at', `${input.publishedAt}T00:00:00Z`)
  }
  return apiRequest<DocumentIngestionJob>(
    `/api/v1/evidence/brands/${brandId}/documents`,
    { method: 'POST', body: formData },
  )
}

export function listDocumentIngestionJobs(
  brandId: string,
): Promise<DocumentIngestionJobListResponse> {
  return apiRequest<DocumentIngestionJobListResponse>(
    `/api/v1/evidence/brands/${brandId}/ingestion-jobs`,
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
