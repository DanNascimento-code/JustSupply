import type {
  AssessmentDimension,
  AssessmentSource,
  AssessmentStatus,
} from './consumer'

export type SocialDimension = Extract<
  AssessmentDimension,
  'women_workers' | 'minority_inclusion'
>

export type EvidenceFindingStatus = Extract<
  AssessmentStatus,
  'supported' | 'mixed' | 'concern'
>

export type EvidenceSourceType =
  | 'corporate_report'
  | 'certification'
  | 'ngo_report'
  | 'news'
  | 'academic_research'
  | 'public_database'
  | 'other'

export type ReviewStatus = 'pending' | 'approved' | 'rejected'
export type ReviewDecision = 'approved' | 'rejected'

export interface BrandSummary {
  id: string
  name: string
}

export interface BrandListResponse {
  items: BrandSummary[]
  total: number
}

export interface BrandEvidenceInput {
  dimension: SocialDimension
  status: EvidenceFindingStatus
  statement: string
  source_title: string
  source_provider: string
  source_url: string
  source_type: EvidenceSourceType
  excerpt: string | null
  source_location: string | null
  published_at: string | null
}

export interface BrandClaim {
  id: string
  brand_id: string
  brand_name: string
  dimension: SocialDimension
  status: EvidenceFindingStatus
  statement: string
  review_status: ReviewStatus
  reviewed_at: string | null
  created_at: string
  updated_at: string
  sources: AssessmentSource[]
}

export interface BrandClaimListResponse {
  items: BrandClaim[]
  total: number
}
