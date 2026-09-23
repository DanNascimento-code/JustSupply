import type { DocumentIndexResult, RagAnswer } from '../types/rag'
import { apiRequest } from './client'

export function askBrandEvidence(
  brandId: string,
  question: string,
): Promise<RagAnswer> {
  return apiRequest<RagAnswer>(`/api/v1/rag/brands/${brandId}/ask`, {
    method: 'POST',
    body: JSON.stringify({ question, top_k: 3 }),
  })
}

export function indexEvidenceDocument(
  documentId: string,
): Promise<DocumentIndexResult> {
  return apiRequest<DocumentIndexResult>(
    `/api/v1/rag/documents/${documentId}/index`,
    { method: 'POST' },
  )
}
