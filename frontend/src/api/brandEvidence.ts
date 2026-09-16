import type {
  BrandClaim,
  BrandClaimListResponse,
  BrandEvidenceInput,
  BrandListResponse,
  ReviewDecision,
} from '../types/brandEvidence'
import { apiRequest } from './client'

export function listEvidenceBrands(): Promise<BrandListResponse> {
  return apiRequest<BrandListResponse>('/api/v1/evidence/brands')
}

export function listBrandClaims(brandId: string): Promise<BrandClaimListResponse> {
  return apiRequest<BrandClaimListResponse>(
    `/api/v1/evidence/brands/${brandId}/claims`,
  )
}

export function createBrandClaim(
  brandId: string,
  payload: BrandEvidenceInput,
): Promise<BrandClaim> {
  return apiRequest<BrandClaim>(`/api/v1/evidence/brands/${brandId}/claims`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function reviewBrandClaim(
  claimId: string,
  decision: ReviewDecision,
): Promise<BrandClaim> {
  return apiRequest<BrandClaim>(`/api/v1/evidence/claims/${claimId}/review`, {
    method: 'PATCH',
    body: JSON.stringify({ decision }),
  })
}
